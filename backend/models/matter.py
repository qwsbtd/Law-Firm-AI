import enum
from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey
from sqlalchemy.sql import func
from core.database import Base


class MatterStatus(str, enum.Enum):
    open = "open"
    closed = "closed"


class Matter(Base):
    __tablename__ = "matters"

    id = Column(Integer, primary_key=True, index=True)
    matter_number = Column(String, unique=True, index=True, nullable=False)
    matter_name = Column(String, nullable=False)
    client_name = Column(String, default="")
    status = Column(Enum(MatterStatus), default=MatterStatus.open, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
