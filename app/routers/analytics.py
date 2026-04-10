from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date
from datetime import datetime, timedelta, timezone
from collections import Counter
import re

from ..database import get_db
from ..models import Survey, Response, SurveyDistribution
from ..schemas import DashboardAnalytics, SurveyAnalytics, CsatPoint, ThemeCount, TrendPoint
from ..security import require_any

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

STOPWORDS = {
    "that", "this", "with", "have", "your", "from", "they", "were", "been",
    "their", "what", "when", "will", "just", "more", "also", "very", "really",
    "would", "could", "should", "about", "there",
}


def _compute_nps(rating_values: list[float]) -> float:
    """NPS: promoters (>=4) minus detractors (<=2), as % of total."""
    if not rating_values:
        return 0.0
    promoters = sum(1 for v in rating_values if v >= 4)
    detractors = sum(1 for v in rating_values if v <= 2)
    return round(((promoters - detractors) / len(rating_values)) * 100, 1)


def _extract_ratings(responses: list) -> list[float]:
    scores = []
    for r in responses:
        for val in r.answers.values():
            if isinstance(val, (int, float)) and 1 <= val <= 5:
                scores.append(float(val))
    return scores


@router.get("", response_model=DashboardAnalytics)
def dashboard_analytics(
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(require_any),
):
    survey_q = db.query(Survey)
    if status:
        survey_q = survey_q.filter(Survey.status == status)
    surveys = survey_q.all()
    survey_ids = [s.id for s in surveys]

    survey_count = len(surveys)
    active_surveys = sum(1 for s in surveys if s.status == "published")

    resp_q = db.query(Response)
    if survey_ids:
        resp_q = resp_q.filter(Response.survey_id.in_(survey_ids))
    if start_date:
        resp_q = resp_q.filter(Response.submitted_at >= start_date)
    if end_date:
        resp_q = resp_q.filter(Response.submitted_at <= end_date)

    responses = resp_q.all()
    total_responses = len(responses)
    complete_responses = sum(1 for r in responses if r.is_complete)
    completion_rate = round((complete_responses / total_responses * 100), 1) if total_responses else 0.0

    rating_scores = _extract_ratings(responses)
    csat = round(sum(rating_scores) / len(rating_scores), 1) if rating_scores else 0.0
    nps = _compute_nps(rating_scores)

    # 7-day response trend
    now = datetime.now(timezone.utc)
    trend = []
    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        day_str = day.strftime("%a")
        count = sum(
            1 for r in responses
            if r.submitted_at and r.submitted_at.date() == day.date()
        )
        trend.append(TrendPoint(name=day_str, responses=count))

    # Survey performance (responses per survey, top 7)
    survey_response_counts = Counter(r.survey_id for r in responses)
    survey_performance = []
    for s in surveys[:7]:
        survey_performance.append(TrendPoint(name=s.title[:20], responses=survey_response_counts.get(s.id, 0)))

    return DashboardAnalytics(
        totalResponses=total_responses,
        surveyCount=survey_count,
        activeSurveys=active_surveys,
        completionRate=completion_rate,
        csat=f"{csat:.1f}",
        nps=nps,
        responseTrend=trend,
        surveyPerformance=survey_performance,
    )


@router.get("/{survey_id}", response_model=SurveyAnalytics)
def survey_analytics(
    survey_id: str,
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(require_any),
):
    survey = db.query(Survey).filter(Survey.id == survey_id).first()
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")

    resp_q = db.query(Response).filter(Response.survey_id == survey_id)
    if start_date:
        resp_q = resp_q.filter(Response.submitted_at >= start_date)
    if end_date:
        resp_q = resp_q.filter(Response.submitted_at <= end_date)
    responses = resp_q.all()

    total_responses = len(responses)
    complete_responses = sum(1 for r in responses if r.is_complete)
    completion_rate = round((complete_responses / total_responses * 100), 1) if total_responses else 0.0

    # Distribution tracking for response rate
    total_distributed = db.query(func.count(SurveyDistribution.id)).filter(
        SurveyDistribution.survey_id == survey_id
    ).scalar() or 0
    response_rate = (
        f"{round(total_responses / total_distributed * 100)}%"
        if total_distributed > 0
        else "N/A"
    )

    # CSAT and NPS over time (monthly)
    monthly_scores: dict[str, list[float]] = {}
    open_ended: list[str] = []

    for r in responses:
        month_key = r.submitted_at.strftime("%Y-%m") if r.submitted_at else "unknown"
        for val in r.answers.values():
            if isinstance(val, (int, float)) and 1 <= val <= 5:
                monthly_scores.setdefault(month_key, []).append(float(val))
            elif isinstance(val, str) and len(val) > 20:
                open_ended.append(val)

    csat_over_time = [
        CsatPoint(date=month, score=round(sum(scores) / len(scores), 2))
        for month, scores in sorted(monthly_scores.items())
    ]
    if not csat_over_time:
        now = datetime.now(timezone.utc)
        csat_over_time = [
            CsatPoint(date=(now - timedelta(days=30 * i)).strftime("%Y-%m"), score=0.0)
            for i in range(3, -1, -1)
        ]

    rating_scores = _extract_ratings(responses)
    nps = _compute_nps(rating_scores)
    csat_avg = round(sum(rating_scores) / len(rating_scores), 1) if rating_scores else 0.0

    # Common themes from text answers
    word_counts: Counter = Counter()
    for r in responses:
        for val in r.answers.values():
            if isinstance(val, str):
                words = re.findall(r"\b[a-zA-Z]{4,}\b", val.lower())
                word_counts.update(w for w in words if w not in STOPWORDS)

    common_themes = [
        ThemeCount(theme=word.title(), count=count)
        for word, count in word_counts.most_common(10)
    ]

    return SurveyAnalytics(
        surveyTitle=survey.title,
        totalResponses=total_responses,
        completionRate=f"{completion_rate}%",
        responseRate=response_rate,
        csat=f"{csat_avg:.1f}",
        nps=nps,
        csatOverTime=csat_over_time,
        commonThemes=common_themes,
        openEndedResponses=open_ended[:20],
    )
