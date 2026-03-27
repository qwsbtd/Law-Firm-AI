from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from core.database import get_db
from core.security import get_current_user, require_role
from models.query_stat import QueryStat
from models.document import Document
from models.audit_log import AuditLog
from models.matter import Matter

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/stats")
async def get_stats(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    # Queries per day (last 30 days)
    queries_by_day = (
        db.query(
            func.date(QueryStat.timestamp).label("date"),
            func.count(QueryStat.id).label("count"),
        )
        .filter(QueryStat.timestamp >= cutoff)
        .group_by(func.date(QueryStat.timestamp))
        .order_by(func.date(QueryStat.timestamp))
        .all()
    )

    # Document status counts
    doc_counts = (
        db.query(Document.status, func.count(Document.id).label("count"))
        .group_by(Document.status)
        .all()
    )

    # Top 10 queried documents
    top_docs = (
        db.query(
            Document.original_filename,
            func.count(QueryStat.id).label("query_count"),
        )
        .join(QueryStat, QueryStat.doc_id == Document.id)
        .group_by(Document.id)
        .order_by(func.count(QueryStat.id).desc())
        .limit(10)
        .all()
    )

    # Matters with most activity
    top_matters = (
        db.query(
            Matter.matter_number,
            Matter.matter_name,
            func.count(QueryStat.id).label("query_count"),
        )
        .join(QueryStat, QueryStat.matter_id == Matter.id)
        .group_by(Matter.id)
        .order_by(func.count(QueryStat.id).desc())
        .limit(10)
        .all()
    )

    # Response time percentiles
    all_ms = [
        r.response_ms
        for r in db.query(QueryStat.response_ms)
        .filter(QueryStat.timestamp >= cutoff)
        .all()
    ]
    sorted_ms = sorted(all_ms)
    p50 = sorted_ms[len(sorted_ms) // 2] if sorted_ms else 0
    p95 = sorted_ms[int(len(sorted_ms) * 0.95)] if sorted_ms else 0

    # Total counts
    total_docs = db.query(func.count(Document.id)).scalar()
    total_queries = db.query(func.count(QueryStat.id)).scalar()
    total_matters = db.query(func.count(Matter.id)).scalar()

    return {
        "totals": {
            "documents": total_docs,
            "queries": total_queries,
            "matters": total_matters,
        },
        "queries_by_day": [
            {"date": str(d), "count": c} for d, c in queries_by_day
        ],
        "doc_status": [
            {"status": str(s), "count": c} for s, c in doc_counts
        ],
        "top_docs": [
            {"filename": f, "query_count": c} for f, c in top_docs
        ],
        "top_matters": [
            {"matter_number": mn, "matter_name": mname, "query_count": c}
            for mn, mname, c in top_matters
        ],
        "response_time": {"p50_ms": p50, "p95_ms": p95},
    }


@router.get("/audit-log")
async def get_audit_log(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(require_role("admin")),
):
    offset = (page - 1) * limit
    total = db.query(func.count(AuditLog.id)).scalar()
    logs = (
        db.query(AuditLog)
        .order_by(AuditLog.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "logs": [
            {
                "id": log.id,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                "user_email": log.user_email,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "detail": log.detail,
                "ip_address": log.ip_address,
                "success": log.success,
            }
            for log in logs
        ],
    }
