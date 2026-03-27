import enum
from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, Text, Date
from sqlalchemy.sql import func
from core.database import Base


class LibraryDocStatus(str, enum.Enum):
    processing = "processing"
    ready = "ready"
    failed = "failed"


class DocumentType(str, enum.Enum):
    case_file = "case_file"
    statute = "statute"
    case_law = "case_law"
    template = "template"
    court_record = "court_record"


class LegalCategory(str, enum.Enum):
    contract = "contract"
    tort = "tort"
    ip = "ip"
    criminal = "criminal"
    family = "family"
    corporate = "corporate"
    real_estate = "real_estate"
    other = "other"


class LibraryDocument(Base):
    __tablename__ = "library_documents"

    id                  = Column(Integer, primary_key=True, index=True)
    title               = Column(String, nullable=False, index=True)
    original_filename   = Column(String, nullable=False)
    filename            = Column(String, nullable=False)          # uuid-prefixed stored name
    file_size           = Column(Integer, default=0)
    mime_type           = Column(String, default="")
    status              = Column(Enum(LibraryDocStatus), default=LibraryDocStatus.processing, nullable=False)
    summary             = Column(Text, nullable=True)
    uploader_id         = Column(Integer, ForeignKey("users.id"), nullable=True)
    document_type       = Column(Enum(DocumentType), nullable=False)
    category            = Column(Enum(LegalCategory), nullable=False)
    jurisdiction        = Column(String, nullable=False)           # federal / state / local
    jurisdiction_detail = Column(String, default="")               # e.g. "Texas", "9th Circuit"
    citation            = Column(String, default="")
    court_name          = Column(String, default="")
    case_date           = Column(Date, nullable=True)
    notes               = Column(Text, default="")
    chunk_count         = Column(Integer, default=0)
    page_count          = Column(Integer, default=0)
    upload_time         = Column(DateTime(timezone=True), server_default=func.now())
    processed_time      = Column(DateTime(timezone=True), nullable=True)
    error_message       = Column(Text, nullable=True)
    courtlistener_id    = Column(String, default="", index=True)   # for duplicate-import guard
