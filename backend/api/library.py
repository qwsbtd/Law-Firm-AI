import os
from datetime import date as date_type
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import httpx

from core.database import get_db
from core.security import get_current_user, require_role
from core.config import settings
from models.library_document import LibraryDocument, LibraryDocStatus, DocumentType, LegalCategory
from models.audit_log import AuditLog
import uuid

router = APIRouter(prefix="/library", tags=["library"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB

VALID_DOCUMENT_TYPES = {e.value for e in DocumentType}
VALID_CATEGORIES = {e.value for e in LegalCategory}
VALID_JURISDICTIONS = {"federal", "state", "local"}


class LibrarySearchRequest(BaseModel):
    question: str
    document_type: Optional[str] = None
    category: Optional[str] = None
    jurisdiction: Optional[str] = None


class CourtSearchRequest(BaseModel):
    query: str
    jurisdiction: str = "all"


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_library_document(
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    document_type: str = Form(...),
    category: str = Form(...),
    jurisdiction: str = Form(...),
    jurisdiction_detail: str = Form(default=""),
    citation: str = Form(default=""),
    court_name: str = Form(default=""),
    case_date: str = Form(default=""),
    notes: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type '{ext}' not supported. Use PDF, DOCX, or TXT.")

    if document_type not in VALID_DOCUMENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid document_type '{document_type}'")
    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category '{category}'")
    if jurisdiction not in VALID_JURISDICTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid jurisdiction '{jurisdiction}'. Use federal, state, or local.")

    # Parse optional date
    parsed_date = None
    if case_date:
        try:
            parsed_date = date_type.fromisoformat(case_date)
        except ValueError:
            pass

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds 500 MB limit")

    os.makedirs(settings.library_path, exist_ok=True)
    stored_filename = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(settings.library_path, stored_filename)
    with open(file_path, "wb") as f:
        f.write(content)

    doc = LibraryDocument(
        title=title,
        original_filename=file.filename or stored_filename,
        filename=stored_filename,
        file_size=len(content),
        mime_type=file.content_type or "",
        status=LibraryDocStatus.processing,
        uploader_id=current_user.id,
        document_type=document_type,
        category=category,
        jurisdiction=jurisdiction,
        jurisdiction_detail=jurisdiction_detail,
        citation=citation,
        court_name=court_name,
        case_date=parsed_date,
        notes=notes,
    )
    db.add(doc)
    db.flush()

    db.add(
        AuditLog(
            action="LIBRARY_UPLOAD",
            user_id=current_user.id,
            user_email=current_user.email,
            resource_type="library_document",
            resource_id=str(doc.id),
            detail=title,
            ip_address=request.client.host if request.client else "",
        )
    )
    db.commit()
    lib_doc_id = doc.id

    from services.library_service import process_library_document
    background_tasks.add_task(
        process_library_document,
        lib_doc_id=lib_doc_id,
        file_path=file_path,
        mime_type=file.content_type or "",
        original_filename=file.filename or stored_filename,
        uploader_id=current_user.id,
        title=title,
        document_type=document_type,
        category=category,
        jurisdiction=jurisdiction,
        jurisdiction_detail=jurisdiction_detail,
        citation=citation,
        court_name=court_name,
    )

    return {"id": lib_doc_id, "title": title, "status": "processing"}


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("/")
async def list_library_documents(
    document_type: Optional[str] = None,
    category: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    query = db.query(LibraryDocument)
    if document_type:
        query = query.filter(LibraryDocument.document_type == document_type)
    if category:
        query = query.filter(LibraryDocument.category == category)
    if jurisdiction:
        query = query.filter(LibraryDocument.jurisdiction == jurisdiction)
    if status:
        query = query.filter(LibraryDocument.status == status)
    docs = query.order_by(LibraryDocument.upload_time.desc()).all()
    return [_lib_doc_dict(d) for d in docs]


# ── Get One ───────────────────────────────────────────────────────────────────

@router.get("/{lib_doc_id}")
async def get_library_document(
    lib_doc_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    doc = db.query(LibraryDocument).filter(LibraryDocument.id == lib_doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Library document not found")
    return _lib_doc_dict(doc, include_summary=True)


# ── Delete (admin only) ───────────────────────────────────────────────────────

@router.delete("/{lib_doc_id}")
async def delete_library_document(
    lib_doc_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin")),
):
    doc = db.query(LibraryDocument).filter(LibraryDocument.id == lib_doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Library document not found")

    from services.chroma_service import delete_library_chunks
    delete_library_chunks(lib_doc_id)

    file_path = os.path.join(settings.library_path, doc.filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    db.add(
        AuditLog(
            action="LIBRARY_DELETE",
            user_id=current_user.id,
            user_email=current_user.email,
            resource_type="library_document",
            resource_id=str(lib_doc_id),
            detail=doc.title,
            ip_address=request.client.host if request.client else "",
        )
    )
    db.delete(doc)
    db.commit()
    return {"detail": f"Library document '{doc.title}' deleted"}


# ── Semantic Search ───────────────────────────────────────────────────────────

@router.post("/search")
async def search_library(
    payload: LibrarySearchRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    from services.library_service import query_library
    import time

    start = time.perf_counter()
    result = await query_library(
        payload.question,
        document_type=payload.document_type,
        category=payload.category,
        jurisdiction=payload.jurisdiction,
    )
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    db.add(
        AuditLog(
            action="LIBRARY_SEARCH",
            user_id=current_user.id,
            user_email=current_user.email,
            resource_type="library",
            detail=payload.question[:500],
        )
    )
    db.commit()
    return {**result, "response_ms": elapsed_ms}


# ── Summarize ─────────────────────────────────────────────────────────────────

@router.post("/{lib_doc_id}/summarize")
async def summarize_library_document(
    lib_doc_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    doc = db.query(LibraryDocument).filter(LibraryDocument.id == lib_doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Library document not found")
    if doc.status != LibraryDocStatus.ready:
        raise HTTPException(status_code=400, detail="Document is not ready yet")
    if doc.summary:
        return {"summary": doc.summary, "cached": True}

    from services.document_service import extract_text
    from services.rag_service import summarize_document

    file_path = os.path.join(settings.library_path, doc.filename)
    text, _ = extract_text(file_path, doc.mime_type)
    summary = await summarize_document(text)
    doc.summary = summary
    db.commit()
    return {"summary": summary, "cached": False}


# ── CourtListener Search ──────────────────────────────────────────────────────

@router.post("/court-search")
async def court_search(
    payload: CourtSearchRequest,
    current_user=Depends(get_current_user),
):
    from services.library_service import search_courtlistener
    try:
        results = await search_courtlistener(payload.query, payload.jurisdiction)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"CourtListener API error: {exc}")
    return {"results": results, "count": len(results)}


# ── CourtListener Import ──────────────────────────────────────────────────────

@router.post("/court-import/{opinion_id}")
async def court_import(
    opinion_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Duplicate-import guard
    existing = db.query(LibraryDocument).filter(
        LibraryDocument.courtlistener_id == opinion_id
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Opinion {opinion_id} already imported (library doc ID {existing.id})",
        )

    from services.library_service import import_courtlistener_opinion, process_library_document
    try:
        lib_doc_id, file_path, case_name, court_name, citation_str = (
            await import_courtlistener_opinion(opinion_id, current_user.id)
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"CourtListener API error: {exc}")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    db.add(
        AuditLog(
            action="COURT_IMPORT",
            user_id=current_user.id,
            user_email=current_user.email,
            resource_type="library_document",
            resource_id=str(lib_doc_id),
            detail=f"CourtListener {opinion_id}: {case_name}",
            ip_address=request.client.host if request.client else "",
        )
    )
    db.commit()

    background_tasks.add_task(
        process_library_document,
        lib_doc_id=lib_doc_id,
        file_path=file_path,
        mime_type="text/plain",
        original_filename=f"{case_name[:100]}.txt",
        uploader_id=current_user.id,
        title=case_name,
        document_type="court_record",
        category="other",
        jurisdiction="federal",
        jurisdiction_detail=court_name,
        citation=citation_str,
        court_name=court_name,
    )

    return {
        "lib_doc_id": lib_doc_id,
        "title": case_name,
        "status": "processing",
        "opinion_id": opinion_id,
    }


# ── Serialization helper ──────────────────────────────────────────────────────

def _lib_doc_dict(doc: LibraryDocument, include_summary: bool = False) -> dict:
    result = {
        "id":                   doc.id,
        "title":                doc.title,
        "original_filename":    doc.original_filename,
        "file_size":            doc.file_size,
        "status":               doc.status,
        "document_type":        doc.document_type,
        "category":             doc.category,
        "jurisdiction":         doc.jurisdiction,
        "jurisdiction_detail":  doc.jurisdiction_detail,
        "citation":             doc.citation,
        "court_name":           doc.court_name,
        "case_date":            doc.case_date.isoformat() if doc.case_date else None,
        "notes":                doc.notes,
        "page_count":           doc.page_count,
        "chunk_count":          doc.chunk_count,
        "upload_time":          doc.upload_time.isoformat() if doc.upload_time else None,
        "processed_time":       doc.processed_time.isoformat() if doc.processed_time else None,
        "error_message":        doc.error_message,
        "courtlistener_id":     doc.courtlistener_id,
    }
    if include_summary:
        result["summary"] = doc.summary
    else:
        result["summary_preview"] = (doc.summary[:200] + "…") if doc.summary else None
    return result
