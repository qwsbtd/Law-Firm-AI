import enum
from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, Text
from sqlalchemy.sql import func
from core.database import Base


class DocumentStatus(str, enum.Enum):
    processing = "processing"
    ready = "ready"
    failed = "failed"


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)           # stored filename (uuid-prefixed)
    original_filename = Column(String, nullable=False)  # original upload name
    file_size = Column(Integer, default=0)
    mime_type = Column(String, default="")
    status = Column(Enum(DocumentStatus), default=DocumentStatus.processing, nullable=False)
    summary = Column(Text, nullable=True)
    uploader_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    matter_id = Column(Integer, ForeignKey("matters.id"), nullable=True, index=True)
    page_count = Column(Integer, default=0)
    chunk_count = Column(Integer, default=0)
    upload_time = Column(DateTime(timezone=True), server_default=func.now())
    processed_time = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
