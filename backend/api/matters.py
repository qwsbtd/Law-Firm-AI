from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from core.database import get_db
from core.security import get_current_user, require_role
from models.matter import Matter, MatterStatus
from models.document import Document
from models.audit_log import AuditLog

router = APIRouter(prefix="/matters", tags=["matters"])


class MatterCreate(BaseModel):
    matter_number: str
    matter_name: str
    client_name: str = ""


class MatterUpdate(BaseModel):
    matter_name: str | None = None
    client_name: str | None = None
    status: MatterStatus | None = None


@router.post("/")
async def create_matter(
    payload: MatterCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin", "attorney")),
):
    existing = db.query(Matter).filter(Matter.matter_number == payload.matter_number).first()
    if existing:
        raise HTTPException(status_code=400, detail="Matter number already exists")
    matter = Matter(
        matter_number=payload.matter_number,
        matter_name=payload.matter_name,
        client_name=payload.client_name,
        created_by=current_user.id,
    )
    db.add(matter)
    db.flush()
    db.add(
        AuditLog(
            user_id=current_user.id,
            user_email=current_user.email,
            action="CREATE_MATTER",
            resource_type="matter",
            resource_id=str(matter.id),
            detail=f"{payload.matter_number} — {payload.matter_name}",
            ip_address=request.client.host if request.client else "",
        )
    )
    db.commit()
    db.refresh(matter)
    return _matter_dict(matter, doc_count=0)


@router.get("/")
async def list_matters(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    rows = (
        db.query(Matter, func.count(Document.id).label("doc_count"))
        .outerjoin(Document, Document.matter_id == Matter.id)
        .group_by(Matter.id)
        .order_by(Matter.created_at.desc())
        .all()
    )
    return [_matter_dict(m, doc_count=c) for m, c in rows]


@router.get("/{matter_id}")
async def get_matter(
    matter_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    matter = db.query(Matter).filter(Matter.id == matter_id).first()
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")
    docs = db.query(Document).filter(Document.matter_id == matter_id).all()
    result = _matter_dict(matter, doc_count=len(docs))
    result["documents"] = [
        {
            "id": d.id,
            "original_filename": d.original_filename,
            "status": d.status,
            "upload_time": d.upload_time.isoformat() if d.upload_time else None,
        }
        for d in docs
    ]
    return result


@router.put("/{matter_id}")
async def update_matter(
    matter_id: int,
    payload: MatterUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin", "attorney")),
):
    matter = db.query(Matter).filter(Matter.id == matter_id).first()
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")
    if payload.matter_name is not None:
        matter.matter_name = payload.matter_name
    if payload.client_name is not None:
        matter.client_name = payload.client_name
    if payload.status is not None:
        matter.status = payload.status
    db.add(
        AuditLog(
            user_id=current_user.id,
            user_email=current_user.email,
            action="UPDATE_MATTER",
            resource_type="matter",
            resource_id=str(matter_id),
            ip_address=request.client.host if request.client else "",
        )
    )
    db.commit()
    db.refresh(matter)
    return _matter_dict(matter, doc_count=0)


@router.delete("/{matter_id}")
async def delete_matter(
    matter_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin")),
):
    matter = db.query(Matter).filter(Matter.id == matter_id).first()
    if not matter:
        raise HTTPException(status_code=404, detail="Matter not found")

    # Delete all associated documents and their vectors
    docs = db.query(Document).filter(Document.matter_id == matter_id).all()
    if docs:
        from services.chroma_service import delete_document_chunks
        from services.rag_service import invalidate_index
        import os

        for doc in docs:
            delete_document_chunks(doc.id)
            file_path = os.path.join("/app/data/uploads", doc.filename)
            if os.path.exists(file_path):
                os.remove(file_path)
            db.delete(doc)
        invalidate_index()

    db.add(
        AuditLog(
            user_id=current_user.id,
            user_email=current_user.email,
            action="DELETE_MATTER",
            resource_type="matter",
            resource_id=str(matter_id),
            detail=f"{matter.matter_number} — {matter.matter_name}",
            ip_address=request.client.host if request.client else "",
        )
    )
    db.delete(matter)
    db.commit()
    return {"detail": "Matter and all associated documents deleted"}


def _matter_dict(matter: Matter, doc_count: int) -> dict:
    return {
        "id": matter.id,
        "matter_number": matter.matter_number,
        "matter_name": matter.matter_name,
        "client_name": matter.client_name,
        "status": matter.status,
        "doc_count": doc_count,
        "created_at": matter.created_at.isoformat() if matter.created_at else None,
    }
