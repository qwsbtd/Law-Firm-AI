import time
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from core.database import get_db
from core.security import get_current_user
from models.audit_log import AuditLog
from models.query_stat import QueryStat
from models.document import Document, DocumentStatus

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str
    matter_id: int | None = None
    doc_id: int | None = None


@router.post("/query")
async def chat_query(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # Validate doc_id if provided
    if payload.doc_id is not None:
        doc = db.query(Document).filter(Document.id == payload.doc_id).first()
        if not doc or doc.status != DocumentStatus.ready:
            raise HTTPException(status_code=400, detail="Document not found or not ready")

    from services.rag_service import query_rag

    start = time.perf_counter()
    result = await query_rag(
        question=payload.question,
        matter_id=payload.matter_id,
        doc_id=payload.doc_id,
    )
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    db.add(
        AuditLog(
            action="QUERY",
            user_id=current_user.id,
            user_email=current_user.email,
            resource_type="chat",
            detail=payload.question[:500],
        )
    )
    db.add(
        QueryStat(
            user_id=current_user.id,
            doc_id=payload.doc_id,
            matter_id=payload.matter_id,
            response_ms=elapsed_ms,
        )
    )
    db.commit()

    return {**result, "response_ms": elapsed_ms}


@router.post("/summarize/{doc_id}")
async def get_summary(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.status != DocumentStatus.ready:
        raise HTTPException(status_code=400, detail="Document is not ready yet")
    if doc.summary:
        return {"summary": doc.summary, "cached": True}

    import os
    from services.document_service import extract_text
    from services.rag_service import summarize_document
    from core.config import settings

    file_path = os.path.join(settings.uploads_path, doc.filename)
    text, _ = extract_text(file_path, doc.mime_type)
    summary = await summarize_document(text)
    doc.summary = summary
    db.commit()
    return {"summary": summary, "cached": False}
