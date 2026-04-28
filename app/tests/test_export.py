"""GET /api/export/responses/{survey_id}?format=csv|xlsx|pdf — admin/manager."""

import uuid

from app.models import QuestionType, SurveyStatus


def _build_survey_with_question(make_survey, owner):
    return make_survey(
        owner=owner,
        title="Export Survey",
        status=SurveyStatus.published,
        questions=[{"type": QuestionType.text, "text": "Comments?"}],
    )


# ── CSV ──────────────────────────────────────────────────────────────────────


def test_export_csv(
    client, admin_headers, admin_user, make_survey, make_response, db
):
    survey = _build_survey_with_question(make_survey, admin_user)
    qid = survey.questions[0].id
    make_response(survey=survey, answers={qid: "Great service"}, respondent_name="Alice")
    r = client.get(
        f"/api/export/responses/{survey.id}?format=csv",
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert ".csv" in r.headers.get("content-disposition", "")
    text = r.text
    assert "Comments?" in text
    assert "Alice" in text
    assert "Great service" in text


def test_export_default_format_is_csv(
    client, admin_headers, admin_user, make_survey
):
    survey = _build_survey_with_question(make_survey, admin_user)
    r = client.get(
        f"/api/export/responses/{survey.id}",
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]


# ── XLSX ─────────────────────────────────────────────────────────────────────


def test_export_xlsx(
    client, admin_headers, admin_user, make_survey, make_response
):
    survey = _build_survey_with_question(make_survey, admin_user)
    qid = survey.questions[0].id
    make_response(survey=survey, answers={qid: "Wow"})
    r = client.get(
        f"/api/export/responses/{survey.id}?format=xlsx",
        headers=admin_headers,
    )
    assert r.status_code == 200
    # XLSX files start with the ZIP magic bytes (PK\x03\x04)
    assert r.content[:4] == b"PK\x03\x04"
    assert ".xlsx" in r.headers.get("content-disposition", "")


# ── PDF ──────────────────────────────────────────────────────────────────────


def test_export_pdf(
    client, admin_headers, admin_user, make_survey, make_response
):
    survey = _build_survey_with_question(make_survey, admin_user)
    qid = survey.questions[0].id
    make_response(survey=survey, answers={qid: "Solid"})
    r = client.get(
        f"/api/export/responses/{survey.id}?format=pdf",
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    # PDF files always begin with %PDF
    assert r.content[:4] == b"%PDF"


# ── Validation / auth ─────────────────────────────────────────────────────────


def test_export_invalid_format_rejected(
    client, admin_headers, admin_user, make_survey
):
    s = _build_survey_with_question(make_survey, admin_user)
    r = client.get(
        f"/api/export/responses/{s.id}?format=docx",
        headers=admin_headers,
    )
    assert r.status_code == 422  # FastAPI Query pattern validation


def test_export_unknown_survey_404(client, admin_headers):
    r = client.get(
        f"/api/export/responses/{uuid.uuid4()}?format=csv",
        headers=admin_headers,
    )
    assert r.status_code == 404


def test_export_manager_can_only_export_own_survey(
    client, manager_headers, other_manager, make_survey
):
    foreign = _build_survey_with_question(make_survey, other_manager)
    r = client.get(
        f"/api/export/responses/{foreign.id}?format=csv",
        headers=manager_headers,
    )
    assert r.status_code == 403


def test_export_unauth_401(client, admin_user, make_survey):
    s = _build_survey_with_question(make_survey, admin_user)
    r = client.get(f"/api/export/responses/{s.id}?format=csv")
    assert r.status_code == 401
