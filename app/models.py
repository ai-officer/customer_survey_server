from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, JSON, Enum, Integer, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import uuid

from .database import Base


def generate_uuid():
    return str(uuid.uuid4())


# ── Enums ────────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    admin = "admin"
    manager = "manager"


class SurveyStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    archived = "archived"


class QuestionType(str, enum.Enum):
    text = "text"
    rating = "rating"
    multiple_choice = "multiple-choice"
    boolean = "boolean"


# ── Models ───────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    full_name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.manager)
    is_active = Column(Boolean, default=True)
    is_approved = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    audit_logs = relationship("AuditLog", back_populates="user")


class Survey(Base):
    __tablename__ = "surveys"

    id = Column(String, primary_key=True, default=generate_uuid)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False, default="")
    status = Column(Enum(SurveyStatus), nullable=False, default=SurveyStatus.draft)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    questions = relationship(
        "Question", back_populates="survey",
        cascade="all, delete-orphan", order_by="Question.order"
    )
    responses = relationship("Response", back_populates="survey", cascade="all, delete-orphan")
    distributions = relationship("SurveyDistribution", back_populates="survey", cascade="all, delete-orphan")
    creator = relationship("User", foreign_keys=[created_by], lazy="joined")


class Question(Base):
    __tablename__ = "questions"

    id = Column(String, primary_key=True, default=generate_uuid)
    survey_id = Column(String, ForeignKey("surveys.id", ondelete="CASCADE"), nullable=False)
    type = Column(Enum(QuestionType), nullable=False)
    text = Column(Text, nullable=False, default="")
    required = Column(Boolean, default=False)
    options = Column(JSON, nullable=True)
    order = Column(Integer, default=0)

    survey = relationship("Survey", back_populates="questions")


class Response(Base):
    __tablename__ = "responses"

    id = Column(String, primary_key=True, default=generate_uuid)
    survey_id = Column(String, ForeignKey("surveys.id", ondelete="CASCADE"), nullable=False)
    answers = Column(JSON, nullable=False, default=dict)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    # Duplicate prevention fingerprint (hash of IP + user-agent)
    submission_fingerprint = Column(String, nullable=True, index=True)
    is_complete = Column(Boolean, default=True)

    survey = relationship("Survey", back_populates="responses")


class SurveyDistribution(Base):
    """Tracks which emails a survey was distributed to."""
    __tablename__ = "survey_distributions"

    id = Column(String, primary_key=True, default=generate_uuid)
    survey_id = Column(String, ForeignKey("surveys.id", ondelete="CASCADE"), nullable=False)
    email = Column(String, nullable=False)
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    reminder_sent_at = Column(DateTime(timezone=True), nullable=True)
    has_responded = Column(Boolean, default=False)

    survey = relationship("Survey", back_populates="distributions")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String, nullable=False)       # e.g. CREATE_SURVEY, DELETE_SURVEY
    resource = Column(String, nullable=False)     # e.g. survey, response, user
    resource_id = Column(String, nullable=True)
    detail = Column(Text, nullable=True)
    ip_address = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="audit_logs")
