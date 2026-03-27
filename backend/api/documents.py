import os
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Request
from sqlalchemy.orm import Session
from core.database import get_db, SessionLocal
from core.security import get_current_user, require_role
from core.config import settings
from models.document import Document, DocumentStatus
from models.matter import Matter
from models.audit_log import AuditLog

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile = File(...),
    matter_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Validate matter exists
    matter = db.query(Matter).filter(Matter.id == matter_id).first()
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")

    # Validate extension
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type '{ext}' not supported. Use PDF, DOCX, or TXT.")

    # Save to disk
    os.makedirs(settings.uploads_path, exist_ok=True)
    stored_filename = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(settings.uploads_path, stored_filename)

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds 500 MB limit")

    with open(file_path, "wb") as f:
        f.write(content)

    mime_type = file.content_type or ""

    doc = Document(
        filename=stored_filename,
        original_filename=file.filename or stored_filename,
        file_size=len(content),
        mime_type=mime_type,
        status=DocumentStatus.processing,
        uploader_id=current_user.id,
        matter_id=matter_id,
    )
    db.add(doc)
    db.flush()

    db.add(
        AuditLog(
            action="UPLOAD",
            user_id=current_user.id,
            user_email=current_user.email,
            resource_type="document",
            resource_id=str(doc.id),
            detail=file.filename,
            ip_address=request.client.host if request.client else "",
        )
    )
    db.commit()
    doc_id = doc.id

    background_tasks.add_task(
        _process_document,
        doc_id=doc_id,
        file_path=file_path,
        mime_type=mime_type,
        original_filename=file.filename or stored_filename,
        uploader_id=current_user.id,
        matter_id=matter_id,
        matter_number=matter.matter_number,
    )

    return {
        "id": doc_id,
        "original_filename": file.filename,
        "status": "processing",
        "matter_id": matter_id,
    }


def _process_document(
    doc_id: int,
    file_path: str,
    mime_type: str,
    original_filename: str,
    uploader_id: int,
    matter_id: int,
    matter_number: str,
):
    """Background task — must create its own DB session."""
    from services.document_service import extract_text, chunk_text
    from services.chroma_service import add_chunks
    from services.rag_service import embed_text, invalidate_index, summarize_document
    from services.notification_service import send_slack
    import asyncio

    db = SessionLocal()
    try:
        text, page_count = extract_text(file_path, mime_type)
        chunks = chunk_text(text, doc_id, original_filename, uploader_id, matter_id, matter_number)

        # Embed each chunk (sentence-transformers, fully local)
        for chunk in chunks:
            chunk["embedding"] = embed_text(chunk["text"])

        add_chunks(doc_id, chunks)

        # Summarize — run async function in a new event loop for the background thread
        summary = asyncio.run(summarize_document(text))

        db.query(Document).filter(Document.id == doc_id).update(
            {
                "status": DocumentStatus.ready,
                "summary": summary,
                "page_count": page_count,
                "chunk_count": len(chunks),
                "processed_time": datetime.now(timezone.utc),
                "error_message": None,
            }
        )
        invalidate_index()
        db.commit()

        asyncio.run(
            send_slack(
                f"✅ *{original_filename}* processed successfully ({page_count} pages, {len(chunks)} chunks) "
                f"for matter *{matter_number}*."
            )
        )
    except Exception as exc:
        db.query(Document).filter(Document.id == doc_id).update(
            {
                "status": DocumentStatus.failed,
                "error_message": str(exc)[:1000],
            }
        )
        db.commit()
    finally:
        db.close()


@router.get("/")
async def list_documents(
    matter_id: int | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    query = db.query(Document)
    if matter_id is not None:
        query = query.filter(Document.matter_id == matter_id)
    docs = query.order_by(Document.upload_time.desc()).all()
    return [_doc_dict(d) for d in docs]


@router.get("/{doc_id}")
async def get_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return _doc_dict(doc, include_summary=True)


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin")),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    from services.chroma_service import delete_document_chunks
    from services.rag_service import invalidate_index

    delete_document_chunks(doc_id)
    file_path = os.path.join(settings.uploads_path, doc.filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    db.add(
        AuditLog(
            action="DELETE",
            user_id=current_user.id,
            user_email=current_user.email,
            resource_type="document",
            resource_id=str(doc_id),
            detail=doc.original_filename,
            ip_address=request.client.host if request.client else "",
        )
    )
    db.delete(doc)
    db.commit()
    invalidate_index()
    return {"detail": f"Document '{doc.original_filename}' deleted"}


@router.post("/{doc_id}/summarize")
async def summarize_document_endpoint(
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
        return {"summary": doc.summary}

    from services.document_service import extract_text
    from services.rag_service import summarize_document
    from core.config import settings as cfg

    file_path = os.path.join(cfg.uploads_path, doc.filename)
    text, _ = extract_text(file_path, doc.mime_type)
    summary = await summarize_document(text)
    doc.summary = summary
    db.commit()
    return {"summary": summary}


def _doc_dict(doc: Document, include_summary: bool = False) -> dict:
    result = {
        "id": doc.id,
        "original_filename": doc.original_filename,
        "file_size": doc.file_size,
        "status": doc.status,
        "matter_id": doc.matter_id,
        "page_count": doc.page_count,
        "chunk_count": doc.chunk_count,
        "upload_time": doc.upload_time.isoformat() if doc.upload_time else None,
        "processed_time": doc.processed_time.isoformat() if doc.processed_time else None,
        "error_message": doc.error_message,
    }
    if include_summary:
        result["summary"] = doc.summary
    else:
        result["summary_preview"] = (doc.summary[:200] + "…") if doc.summary else None
    return result
