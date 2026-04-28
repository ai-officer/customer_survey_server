"""POST /api/responses (public) + GET /api/responses (auth, ownership-scoped)."""

from app.models import SurveyDistribution, SurveyStatus
import uuid


def _post_response(client, *, survey_id, answers=None, user_agent="ua-1", **extra):
    body = {
        "surveyId": survey_id,
        "answers": answers or {},
        "is_complete": True,
        **extra,
    }
    return client.post(
        "/api/responses",
        json=body,
        headers={"User-Agent": user_agent},
    )


# ── Submit (public) ──────────────────────────────────────────────────────────


def test_submit_response_to_published_survey(
    client, manager_user, make_survey
):
    survey = make_survey(owner=manager_user, status=SurveyStatus.published)
    r = _post_response(client, survey_id=survey.id, answers={"q1": 5})
    assert r.status_code == 201
    body = r.json()
    assert body["surveyId"] == survey.id
    assert body["answers"] == {"q1": 5}
    assert body["isAnonymous"] is False


def test_submit_response_anonymous_strips_name(
    client, manager_user, make_survey
):
    survey = make_survey(owner=manager_user, status=SurveyStatus.published)
    r = _post_response(
        client,
        survey_id=survey.id,
        respondent_name="Alice",
        is_anonymous=True,
    )
    assert r.status_code == 201
    assert r.json()["respondentName"] is None
    assert r.json()["isAnonymous"] is True


def test_submit_response_named_respondent(
    client, manager_user, make_survey
):
    survey = make_survey(owner=manager_user, status=SurveyStatus.published)
    r = _post_response(
        client,
        survey_id=survey.id,
        respondent_name="Bob",
        is_anonymous=False,
    )
    assert r.status_code == 201
    assert r.json()["respondentName"] == "Bob"


def test_cannot_submit_to_draft_survey(client, manager_user, make_survey):
    survey = make_survey(owner=manager_user, status=SurveyStatus.draft)
    r = _post_response(client, survey_id=survey.id)
    assert r.status_code == 403
    assert "not accepting responses" in r.json()["detail"].lower()


def test_cannot_submit_to_archived_survey(client, manager_user, make_survey):
    survey = make_survey(owner=manager_user, status=SurveyStatus.archived)
    r = _post_response(client, survey_id=survey.id)
    assert r.status_code == 403


def test_submit_to_unknown_survey_404(client):
    r = _post_response(client, survey_id=str(uuid.uuid4()))
    assert r.status_code == 404


def test_duplicate_submission_same_fingerprint_409(
    client, manager_user, make_survey
):
    survey = make_survey(owner=manager_user, status=SurveyStatus.published)
    first = _post_response(client, survey_id=survey.id, user_agent="ua-x")
    assert first.status_code == 201
    second = _post_response(client, survey_id=survey.id, user_agent="ua-x")
    assert second.status_code == 409


def test_different_user_agent_can_submit_to_same_survey(
    client, manager_user, make_survey
):
    survey = make_survey(owner=manager_user, status=SurveyStatus.published)
    a = _post_response(client, survey_id=survey.id, user_agent="ua-a")
    b = _post_response(client, survey_id=survey.id, user_agent="ua-b")
    assert a.status_code == 201
    assert b.status_code == 201


def test_submit_marks_distribution_as_responded(
    client, db, manager_user, make_survey
):
    survey = make_survey(owner=manager_user, status=SurveyStatus.published)
    dist = SurveyDistribution(
        id=str(uuid.uuid4()),
        survey_id=survey.id,
        email="alice@example.com",
        has_responded=False,
    )
    db.add(dist)
    db.commit()

    r = _post_response(
        client,
        survey_id=survey.id,
        respondent_email="alice@example.com",
    )
    assert r.status_code == 201

    db.refresh(dist)
    assert dist.has_responded is True


# ── List (auth) ──────────────────────────────────────────────────────────────


def test_list_responses_admin_sees_all(
    client, admin_headers, manager_user, other_manager, make_survey, make_response
):
    s1 = make_survey(owner=manager_user, status=SurveyStatus.published)
    s2 = make_survey(owner=other_manager, status=SurveyStatus.published)
    make_response(survey=s1)
    make_response(survey=s2)
    r = client.get("/api/responses", headers=admin_headers)
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_list_responses_manager_sees_only_own_surveys(
    client, manager_headers, manager_user, other_manager, make_survey, make_response
):
    mine = make_survey(owner=manager_user, status=SurveyStatus.published)
    theirs = make_survey(owner=other_manager, status=SurveyStatus.published)
    make_response(survey=mine)
    make_response(survey=theirs)
    r = client.get("/api/responses", headers=manager_headers)
    assert r.status_code == 200
    survey_ids = {row["surveyId"] for row in r.json()}
    assert survey_ids == {mine.id}


def test_list_responses_filtered_by_survey_id(
    client, manager_headers, manager_user, make_survey, make_response
):
    s1 = make_survey(owner=manager_user, status=SurveyStatus.published)
    s2 = make_survey(owner=manager_user, status=SurveyStatus.published)
    make_response(survey=s1)
    make_response(survey=s1)
    make_response(survey=s2)
    r = client.get(f"/api/responses?survey_id={s1.id}", headers=manager_headers)
    assert r.status_code == 200
    assert len(r.json()) == 2
    assert all(row["surveyId"] == s1.id for row in r.json())


def test_manager_cannot_list_responses_for_others_survey(
    client, manager_headers, other_manager, make_survey, make_response
):
    theirs = make_survey(owner=other_manager, status=SurveyStatus.published)
    make_response(survey=theirs)
    r = client.get(f"/api/responses?survey_id={theirs.id}", headers=manager_headers)
    assert r.status_code == 403


def test_list_responses_unauth(client):
    r = client.get("/api/responses")
    assert r.status_code == 401
