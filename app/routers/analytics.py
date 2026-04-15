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
    "would", "could", "should", "about", "there", "which", "these", "those",
    "then", "than", "some", "such", "even", "well", "good", "great", "nice",
    "make", "made", "like", "know", "think", "feel", "felt", "need", "want",
    "much", "many", "time", "thing", "things", "people", "every", "other",
    "into", "over", "after", "before", "through", "during", "while", "still",
    "always", "never", "often", "again", "though", "because", "however",
}


def _extract_themes(text_responses: list[str]) -> list[tuple[str, int]]:
    """
    Extract meaningful themes from open-ended responses using bigram + unigram
    frequency, weighted so multi-word phrases rank higher than single words.
    Returns list of (theme_label, count) sorted by score descending.
    """
    import math

    word_re = re.compile(r"\b[a-zA-Z]{3,}\b")

    # Tokenize each response into words
    doc_tokens: list[list[str]] = []
    for text in text_responses:
        tokens = [w.lower() for w in word_re.findall(text) if w.lower() not in STOPWORDS]
        doc_tokens.append(tokens)

    n_docs = len(doc_tokens)
    if n_docs == 0:
        return []

    # Count bigrams and unigrams across all docs; track doc frequency for IDF
    bigram_counts: Counter = Counter()
    unigram_counts: Counter = Counter()
    bigram_doc_freq: Counter = Counter()
    unigram_doc_freq: Counter = Counter()

    for tokens in doc_tokens:
        seen_bigrams: set = set()
        seen_unigrams: set = set()
        for i, tok in enumerate(tokens):
            unigram_counts[tok] += 1
            if tok not in seen_unigrams:
                unigram_doc_freq[tok] += 1
                seen_unigrams.add(tok)
            if i < len(tokens) - 1:
                bg = f"{tok} {tokens[i + 1]}"
                bigram_counts[bg] += 1
                if bg not in seen_bigrams:
                    bigram_doc_freq[bg] += 1
                    seen_bigrams.add(bg)

    def tfidf_score(term: str, tf: int, df: int) -> float:
        idf = math.log((n_docs + 1) / (df + 1)) + 1
        # Bigrams get a 2x boost since they're more meaningful
        boost = 2.0 if " " in term else 1.0
        return tf * idf * boost

    # Build combined candidate scores
    scored: dict[str, tuple[float, int]] = {}
    for bg, count in bigram_counts.items():
        if count >= 1:  # include all bigrams that appear
            score = tfidf_score(bg, count, bigram_doc_freq[bg])
            scored[bg] = (score, count)
    for uni, count in unigram_counts.items():
        # Only include unigrams not already covered by a top bigram
        already_covered = any(uni in bg for bg in bigram_counts if bigram_counts[bg] >= 2)
        if not already_covered and count >= 1:
            score = tfidf_score(uni, count, unigram_doc_freq[uni])
            scored[uni] = (score, count)

    # Sort by score, return top 10 as (label, raw_count)
    top = sorted(scored.items(), key=lambda x: x[1][0], reverse=True)[:10]
    return [(label.title(), count) for label, (_, count) in top]


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
    survey_id: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(require_any),
):
    survey_q = db.query(Survey)
    if status:
        survey_q = survey_q.filter(Survey.status == status)
    if survey_id:
        survey_q = survey_q.filter(Survey.id == survey_id)
    surveys = survey_q.all()
    survey_ids = [s.id for s in surveys]

    survey_count = len(surveys)
    active_surveys = sum(1 for s in surveys if s.status == "published")

    resp_q = db.query(Response)
    # Always filter by survey_ids when a status filter is applied — even if empty list
    # (empty list = no matching surveys = no responses)
    if status or survey_ids:
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

    # Common themes from text answers using bigram + TF-IDF extraction
    text_responses: list[str] = []
    for r in responses:
        for val in r.answers.values():
            if isinstance(val, str) and len(val.strip()) > 0:
                text_responses.append(val)

    common_themes = [
        ThemeCount(theme=theme, count=count)
        for theme, count in _extract_themes(text_responses)
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
