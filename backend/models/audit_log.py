from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.sql import func
from core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user_email = Column(String, default="")   # denormalized — readable after account deletion
    action = Column(String, nullable=False, index=True)  # LOGIN, UPLOAD, QUERY, DELETE, REGISTER
    resource_type = Column(String, default="")
    resource_id = Column(String, default="")
    detail = Column(Text, default="")
    ip_address = Column(String, default="")
    success = Column(Boolean, default=True)
