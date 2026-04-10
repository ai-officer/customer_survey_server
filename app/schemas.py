from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime
from enum import Enum


class SurveyStatus(str, Enum):
    draft = "draft"
    published = "published"
    archived = "archived"


class QuestionType(str, Enum):
    text = "text"
    rating = "rating"
    multiple_choice = "multiple-choice"
    boolean = "boolean"


# ── Question ──────────────────────────────────────────────────────────────────

class QuestionBase(BaseModel):
    id: Optional[str] = None
    type: QuestionType
    text: str = ""
    required: bool = False
    options: Optional[list[str]] = None


class QuestionCreate(QuestionBase):
    pass


class QuestionOut(QuestionBase):
    id: str
    model_config = {"from_attributes": True}


# ── Survey ────────────────────────────────────────────────────────────────────

class SurveyCreate(BaseModel):
    title: str
    description: str = ""
    status: SurveyStatus = SurveyStatus.draft
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    questions: list[QuestionCreate] = []


class SurveyUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[SurveyStatus] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    questions: Optional[list[QuestionCreate]] = None


class SurveyOut(BaseModel):
    id: str
    title: str
    description: str
    status: SurveyStatus
    createdAt: datetime
    startDate: Optional[datetime] = None
    endDate: Optional[datetime] = None
    questions: list[QuestionOut] = []

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_survey(cls, survey) -> "SurveyOut":
        return cls(
            id=survey.id,
            title=survey.title,
            description=survey.description,
            status=survey.status,
            createdAt=survey.created_at,
            startDate=survey.start_date,
            endDate=survey.end_date,
            questions=[QuestionOut.model_validate(q) for q in survey.questions],
        )


# ── Response ──────────────────────────────────────────────────────────────────

class ResponseCreate(BaseModel):
    surveyId: str
    answers: dict[str, Any] = {}
    is_complete: bool = True
    respondent_email: Optional[str] = None


class ResponseOut(BaseModel):
    id: str
    surveyId: str
    answers: dict[str, Any]
    submittedAt: datetime
    is_complete: bool

    @classmethod
    def from_orm_response(cls, r) -> "ResponseOut":
        return cls(
            id=r.id,
            surveyId=r.survey_id,
            answers=r.answers,
            submittedAt=r.submitted_at,
            is_complete=r.is_complete,
        )


# ── Analytics ─────────────────────────────────────────────────────────────────

class TrendPoint(BaseModel):
    name: str
    responses: int


class CsatPoint(BaseModel):
    date: str
    score: float


class ThemeCount(BaseModel):
    theme: str
    count: int


class DashboardAnalytics(BaseModel):
    totalResponses: int
    surveyCount: int
    activeSurveys: int
    completionRate: float
    csat: str
    nps: float
    responseTrend: list[TrendPoint]
    surveyPerformance: list[TrendPoint]


class SurveyAnalytics(BaseModel):
    surveyTitle: str
    totalResponses: int
    completionRate: str
    responseRate: str
    csat: str
    nps: float
    csatOverTime: list[CsatPoint]
    commonThemes: list[ThemeCount]
    openEndedResponses: list[str]
