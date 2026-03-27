from sqlalchemy import Column, Integer, DateTime, ForeignKey
from sqlalchemy.sql import func
from core.database import Base


class QueryStat(Base):
    __tablename__ = "query_stats"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    doc_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    matter_id = Column(Integer, ForeignKey("matters.id"), nullable=True)
    response_ms = Column(Integer, default=0)
