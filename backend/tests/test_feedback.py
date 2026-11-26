"""The private feedback questionnaire: open only by its link, then name,
number, answers, thanks and a rating. Staff change the questions and the link.
"""

from __future__ import annotations

import pytest

ADMIN = "/api/admin/feedback"


@pytest.fixture
def survey(db):
    """The questionnaire migration 0032 created, opened and reset to its
    five placeholder questions for each test."""
    db.execute(
        """
        update feedback_surveys set is_open = true, questions = '[
          {"id": "q1", "kind": "text",   "text_en": "How did you hear about us?"},
          {"id": "q2", "kind": "yes_no", "text_en": "Were you treated with respect?",
           "text_zu": "Ingabe niphathwe ngenhlonipho?"},
          {"id": "q3", "kind": "scale",  "text_en": "How easy was it to reach us?"},
          {"id": "q4", "kind": "yes_no", "text_en": "Was everything explained clearly?"},
          {"id": "q5", "kind": "text",   "text_en": "What could we do better?"}
        ]'::jsonb
        """
    )
    code = db.execute("select link_code from feedback_surveys").fetchone()[0]
    return code


def answers(**overrides):
    given = {"q1": "A friend", "q2": "yes", "q3": "4", "q4": "no", "q5": ""}
    given.update(overrides)
    return [{"id": k, "answer": v} for k, v in given.items()]


def person(**overrides):
    body = {
        "first_name": "Thandi",
        "surname": "Mkhize",
        "mobile": "082 123 4567",
        "answers": answers(),
        "contact_consent": True,
        "source": "qr",
    }
    body.update(overrides)
    return body


# --- hidden unless you have the link ----------------------------------------------

def test_the_link_opens_the_questions(client, survey):
    response = client.get(f"/api/feedback/{survey}")
    assert response.status_code == 200
    questions = response.json()["questions"]
    assert [q["id"] for q in questions] == ["q1", "q2", "q3", "q4", "q5"]
    assert questions[1]["text_zu"] == "Ingabe niphathwe ngenhlonipho?"


@pytest.mark.parametrize("code", ["aaaaaaaaaaaa", "short", "has-a-dash-in", "ABCDEFGHIJKL"])
def test_any_other_code_is_simply_not_found(client, survey, code):
    response = client.get(f"/api/feedback/{code}")
    assert response.status_code == 404
    assert response.json()["detail"] == "This page does not exist."


def test_a_closed_questionnaire_looks_exactly_like_a_wrong_link(client, survey, db):
    db.execute("update feedback_surveys set is_open = false")
    assert client.get(f"/api/feedback/{survey}").status_code == 404
    assert client.post(f"/api/feedback/{survey}/responses", json=person()).status_code == 404


def test_guessing_codes_quickly_is_slowed_down(client, survey):
    statuses = [client.get(f"/api/feedback/zz{n:010d}").status_code for n in range(61)]
    assert statuses[-1] == 429


# --- answering --------------------------------------------------------------------

def test_answers_are_saved_with_the_wording_the_person_saw(client, survey, db):
    response = client.post(f"/api/feedback/{survey}/responses",
                           json=person(language="zu"))
    assert response.status_code == 201, response.text
    row = db.execute(
        "select first_name, surname, mobile, source, language, answers, rating "
        "from feedback_responses where id = %s", (response.json()["id"],)).fetchone()
    assert row[:5] == ("Thandi", "Mkhize", "+27821234567", "qr", "zu")
    assert row[5][1] == {"id": "q2", "kind": "yes_no",
                         "question": "Ingabe niphathwe ngenhlonipho?", "answer": "yes"}
    # No isiZulu wording for q1: the English one is what was shown.
    assert row[5][0]["question"] == "How did you hear about us?"
    assert row[6] is None


def test_a_written_answer_may_be_left_blank_but_choices_may_not(client, survey):
    blank_text = client.post(f"/api/feedback/{survey}/responses",
                             json=person(answers=answers(q1="", q5="")))
    assert blank_text.status_code == 201

    missing_choice = client.post(f"/api/feedback/{survey}/responses",
                                 json=person(answers=answers(q2="maybe", q3="9")))
    assert missing_choice.status_code == 422
    fields = missing_choice.json()["field_errors"]
    assert set(fields) == {"answers.q2", "answers.q3"}


@pytest.mark.parametrize("change", [
    {"contact_consent": False},
    {"mobile": "12345"},
    {"first_name": ""},
    {"surname": "<script>"},
    {"website": "http://spam.example"},          # the honeypot
    {"answers": answers(q1="=cmd|' /C calc'!A0")},  # spreadsheet formula
    {"answers": [{"id": "q1", "answer": "a"}, {"id": "q1", "answer": "b"}]},
    {"source": "facebook"},
])
def test_what_is_sent_is_checked(client, survey, change):
    assert client.post(f"/api/feedback/{survey}/responses",
                       json=person(**change)).status_code == 422


def test_a_question_that_no_longer_exists_is_refused(client, survey):
    extra = answers()
    extra.append({"id": "q9", "answer": "yes"})
    response = client.post(f"/api/feedback/{survey}/responses", json=person(answers=extra))
    assert response.status_code == 422
    assert "answers.q9" in response.json()["field_errors"]


def test_no_name_or_number_reaches_the_log(client, survey, caplog):
    with caplog.at_level("INFO"):
        client.post(f"/api/feedback/{survey}/responses", json=person())
    text = caplog.text
    assert "Feedback response" in text
    assert "Thandi" not in text and "Mkhize" not in text and "4567" not in text


# --- the rating at the end --------------------------------------------------------

def test_the_rating_is_added_once(client, survey, db):
    response_id = client.post(f"/api/feedback/{survey}/responses", json=person()).json()["id"]
    first = client.post(f"/api/feedback/responses/{response_id}/rating",
                        json={"rating": 5, "comment": "Very kind people"})
    assert first.status_code == 200
    again = client.post(f"/api/feedback/responses/{response_id}/rating", json={"rating": 1})
    assert again.status_code == 404
    assert db.execute("select rating, rating_comment from feedback_responses where id = %s",
                      (response_id,)).fetchone() == (5, "Very kind people")


def test_a_rating_must_be_one_to_five(client, survey):
    response_id = client.post(f"/api/feedback/{survey}/responses", json=person()).json()["id"]
    for bad in (0, 6, "five"):
        assert client.post(f"/api/feedback/responses/{response_id}/rating",
                           json={"rating": bad}).status_code == 422


def test_an_old_response_cannot_be_rated_later(client, survey, db):
    response_id = client.post(f"/api/feedback/{survey}/responses", json=person()).json()["id"]
    db.execute("update feedback_responses set created_at = now() - interval '3 hours' "
               "where id = %s", (response_id,))
    assert client.post(f"/api/feedback/responses/{response_id}/rating",
                       json={"rating": 4}).status_code == 404


def test_rating_an_unknown_response_is_not_found(client):
    assert client.post("/api/feedback/responses/00000000-0000-0000-0000-000000000000/rating",
                       json={"rating": 4}).status_code == 404


# --- staff ------------------------------------------------------------------------

def test_staff_must_sign_in(client):
    assert client.get(ADMIN).status_code == 401
    assert client.patch(f"{ADMIN}/survey", json={"is_open": False}).status_code == 401
    assert client.post(f"{ADMIN}/survey/new-link").status_code == 401


def test_staff_see_the_link_responses_and_average(client, survey, staff_as):
    first = client.post(f"/api/feedback/{survey}/responses", json=person()).json()["id"]
    client.post(f"/api/feedback/responses/{first}/rating", json={"rating": 4})
    staff_as("viewer")
    overview = client.get(ADMIN).json()
    assert overview["survey"]["link"] == f"https://induduzo.co.za/feedback/{survey}"
    assert overview["can_edit"] is False
    assert overview["summary"]["responses"] >= 1
    assert overview["summary"]["by_rating"]["4"] >= 1
    assert overview["responses"][0]["first_name"] == "Thandi"


def test_a_viewer_cannot_change_the_questions(client, survey, staff_as):
    staff_as("viewer")
    assert client.patch(f"{ADMIN}/survey", json={"is_open": False}).status_code == 403
    assert client.post(f"{ADMIN}/survey/new-link").status_code == 403


def test_an_admin_changes_the_questions_and_the_page_follows(client, survey, staff_as):
    staff_as("admin")
    new = [
        {"id": "q1", "kind": "scale", "text_en": "How was the service on the day?"},
        {"id": "q2", "kind": "text", "text_en": "Anything else?", "text_zu": ""},
    ]
    changed = client.patch(f"{ADMIN}/survey", json={"questions": new})
    assert changed.status_code == 200, changed.text
    assert changed.json()["questions"][1]["text_zu"] is None
    assert changed.json()["updated_by"] == "admin@staff.test"
    shown = client.get(f"/api/feedback/{survey}").json()["questions"]
    assert [q["text_en"] for q in shown] == ["How was the service on the day?", "Anything else?"]


@pytest.mark.parametrize("bad", [
    {"questions": []},
    {"questions": [{"id": "q1", "kind": "essay", "text_en": "Tell us"}]},
    {"questions": [{"id": "q1", "kind": "text", "text_en": "A"}, ]},
    {"questions": [{"id": "q1", "kind": "text", "text_en": "Same id"},
                   {"id": "q1", "kind": "text", "text_en": "Same id again"}]},
    {"questions": [{"id": "q1", "kind": "text", "text_en": "x"}] * 11},
    {},
])
def test_bad_questions_are_refused(client, survey, staff_as, bad):
    staff_as("admin")
    assert client.patch(f"{ADMIN}/survey", json=bad).status_code == 422


def test_a_new_link_stops_the_old_one_at_once(client, survey, staff_as):
    staff_as("owner")
    replaced = client.post(f"{ADMIN}/survey/new-link").json()
    assert replaced["link_code"] != survey
    assert client.get(f"/api/feedback/{survey}").status_code == 404
    assert client.get(f"/api/feedback/{replaced['link_code']}").status_code == 200


def test_closing_it_hides_the_page(client, survey, staff_as):
    staff_as("admin")
    assert client.patch(f"{ADMIN}/survey", json={"is_open": False}).json()["is_open"] is False
    assert client.get(f"/api/feedback/{survey}").status_code == 404
