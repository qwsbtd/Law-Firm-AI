import time
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from core.database import get_db
from core.security import get_current_user
from models.audit_log import AuditLog

router = APIRouter(prefix="/research", tags=["research"])


class ResearchRequest(BaseModel):
    question: str
    matter_id: Optional[int] = None
    confidence_threshold: float = 0.85
    max_retries: int = 3


@router.post("/query")
async def research_query(
    payload: ResearchRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    if not (0.0 < payload.confidence_threshold <= 1.0):
        raise HTTPException(status_code=400, detail="confidence_threshold must be between 0 and 1")
    if not (1 <= payload.max_retries <= 5):
        raise HTTPException(status_code=400, detail="max_retries must be between 1 and 5")

    from services.research_service import research_query as _research_query

    start = time.perf_counter()
    result = await _research_query(
        question=payload.question,
        matter_id=payload.matter_id,
        confidence_threshold=payload.confidence_threshold,
        max_retries=payload.max_retries,
    )
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    db.add(
        AuditLog(
            action="RESEARCH_QUERY",
            user_id=current_user.id,
            user_email=current_user.email,
            resource_type="research",
            detail=payload.question[:500],
            ip_address=request.client.host if request.client else "",
        )
    )
    db.commit()

    return {**result, "response_ms": elapsed_ms}
