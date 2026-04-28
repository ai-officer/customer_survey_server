"""GET /api/analytics + /api/analytics/{survey_id}.

The analytics computation is non-trivial; these tests are smoke-level —
they verify the endpoints respond with the expected response-shape and
sane numeric outputs given a known dataset.
"""

import uuid

from app.models import SurveyStatus


# ── Dashboard ────────────────────────────────────────────────────────────────


def test_dashboard_analytics_empty(client, admin_headers):
    r = client.get("/api/analytics", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    # Top-level shape
    expected_keys = {
        "totalResponses",
        "surveyCount",
        "activeSurveys",
        "completionRate",
        "csat",
        "nps",
        "responseTrend",
        "surveyPerformance",
        "ratingDistribution",
        "departmentBreakdown",
        "departmentEngagement",
        "adminSurveyBreakdown",
    }
    assert expected_keys <= set(body.keys())
    assert body["totalResponses"] == 0
    assert body["surveyCount"] == 0


def test_dashboard_analytics_counts_published_surveys(
    client, admin_headers, admin_user, make_survey
):
    make_survey(owner=admin_user, status=SurveyStatus.published)
    make_survey(owner=admin_user, status=SurveyStatus.published)
    make_survey(owner=admin_user, status=SurveyStatus.draft)
    r = client.get("/api/analytics", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["surveyCount"] == 3
    assert body["activeSurveys"] == 2


def test_dashboard_analytics_unauth(client):
    r = client.get("/api/analytics")
    assert r.status_code == 401


# ── Per-survey ───────────────────────────────────────────────────────────────


def test_survey_analytics_returns_shape(
    client, admin_headers, admin_user, make_survey
):
    s = make_survey(owner=admin_user, status=SurveyStatus.published)
    r = client.get(f"/api/analytics/{s.id}", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert "surveyTitle" in body
    assert "totalResponses" in body
    assert body["surveyTitle"] == s.title


def test_survey_analytics_unknown_survey_404(client, admin_headers):
    r = client.get(f"/api/analytics/{uuid.uuid4()}", headers=admin_headers)
    assert r.status_code == 404


def test_survey_analytics_unauth(client, admin_user, make_survey):
    s = make_survey(owner=admin_user, status=SurveyStatus.published)
    r = client.get(f"/api/analytics/{s.id}")
    assert r.status_code == 401
