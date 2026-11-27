"""The private feedback questionnaire: the owner's post-funeral survey.

Opens only by its link; ten questions or the five-question short version;
choice, 1-5 and 0-10 scales, a rating grid and a written answer; an optional
name and number. Staff change the wording and the link, and read the results.
"""

from __future__ import annotations

import json

import pytest

ADMIN = "/api/admin/feedback"
SHORT = ["q2", "q3", "q6", "q9", "q10"]


@pytest.fixture(scope="module")
def db_module():
    import os

    import psycopg

    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        yield conn


@pytest.fixture(scope="module")
def seeded(db_module):
    """The survey as migration 0032 left it, taken before any test changes it."""
    return db_module.execute(
        "select title_en, title_zu, intro_en, intro_zu, questions from feedback_surveys"
    ).fetchone()


@pytest.fixture
def survey(db, seeded):
    """Open, with the owner's survey restored, for each test. Returns the link code."""
    db.execute(
        "update feedback_surveys set is_open = true, title_en = %s, title_zu = %s, "
        "intro_en = %s, intro_zu = %s, questions = %s::jsonb",
        (seeded[0], seeded[1], seeded[2], seeded[3], json.dumps(seeded[4])),
    )
    return db.execute("select link_code from feedback_surveys").fetchone()[0]


def full_answers(**overrides):
    given = {
        "q1": "edendale",
        "q2": 5,
        "q3": 4,
        "q4": "yes_fully",
        "q5": "easy",
        "q6": "small_delays",
        "q7": {"casket": "excellent", "vehicles": "good", "staff": "excellent"},
        "q8": "yes",
        "q9": 9,
        "q10": "Kind staff. The tent arrived late.",
    }
    given.update(overrides)
    return [{"id": k, "answer": v} for k, v in given.items() if v is not None]


def send(client, code, **body):
    payload = {"answers": full_answers(), "source": "qr", "first_name": "Ayanda",
               "surname": "Testfamily", "mobile": "082 000 0011"}
    payload.update(body)
    return client.post(f"/api/feedback/{code}/responses",
                       json={k: v for k, v in payload.items() if v is not ...})


# --- the owner's survey, as seeded --------------------------------------------------

def test_the_link_opens_the_owners_ten_questions_in_both_languages(client, survey):
    body = client.get(f"/api/feedback/{survey}").json()
    assert body["title_en"] == "Post-Funeral Family Feedback"
    assert body["title_zu"] == "Imibono Yomndeni Ngemva Komngcwabo"
    assert body["intro_en"].startswith("We are sorry for your loss")
    questions = body["questions"]
    assert [q["id"] for q in questions] == [f"q{n}" for n in range(1, 11)]
    assert [q["kind"] for q in questions] == ["choice", "scale", "scale", "choice", "choice",
                                              "choice", "grid", "choice", "scale", "text"]
    q1, q9, q7 = questions[0], questions[8], questions[6]
    assert [o["en"] for o in q1["options"]][-1] == "Not sure"
    assert q1["options"][-1]["zu"] == "Angiqiniseki"
    assert (q9["min"], q9["max"], q9["low_en"], q9["high_zu"]) == (0, 10, "Not at all likely",
                                                                   "Nakanjani")
    assert [r["value"] for r in q7["rows"]] == ["casket", "vehicles", "equipment", "programmes",
                                                "staff"]
    assert [o["en"] for o in q7["options"]] == ["Excellent", "Good", "Fair", "Poor", "Not used"]
    assert all(q["text_zu"] for q in questions)


def test_the_short_version_asks_the_five_starred_questions(client, survey):
    body = client.get(f"/api/feedback/{survey}?v=short").json()
    assert body["version"] == "short"
    assert [q["id"] for q in body["questions"]] == SHORT


# --- hidden unless you have the link ----------------------------------------------

@pytest.mark.parametrize("code", ["aaaaaaaaaaaa", "short", "has-a-dash-in", "ABCDEFGHIJKL"])
def test_any_other_code_is_simply_not_found(client, survey, code):
    response = client.get(f"/api/feedback/{code}")
    assert response.status_code == 404
    assert response.json()["detail"] == "This page does not exist."


def test_a_closed_questionnaire_looks_exactly_like_a_wrong_link(client, survey, db):
    db.execute("update feedback_surveys set is_open = false")
    assert client.get(f"/api/feedback/{survey}").status_code == 404
    assert send(client, survey).status_code == 404


def test_guessing_codes_quickly_is_slowed_down(client, survey):
    statuses = [client.get(f"/api/feedback/zz{n:010d}").status_code for n in range(61)]
    assert statuses[-1] == 429


# --- answering --------------------------------------------------------------------

def test_a_response_keeps_the_familys_details_with_their_consent(client, survey, db):
    response = send(client, survey)
    assert response.status_code == 201, response.text
    row = db.execute(
        "select first_name, surname, name, mobile, email, contact_consent, version, source, "
        "language, answers from feedback_responses where id = %s",
        (response.json()["id"],)).fetchone()
    assert row[:9] == ("Ayanda", "Testfamily", "Ayanda Testfamily", "+27820000011", None, True,
                       "full", "qr", "en")
    answers = {a["id"]: a for a in row[9]}
    assert answers["q1"]["label"] == "Edendale Main Road (Head Office)"
    assert answers["q7"]["answer"] == {"casket": "excellent", "vehicles": "good",
                                       "staff": "excellent"}
    assert answers["q7"]["label"].startswith("Casket or coffin: Excellent; Hearse and vehicles: Good")
    assert answers["q9"]["answer"] == 9


@pytest.mark.parametrize("change, field", [
    ({"first_name": ""}, "first_name"),
    ({"surname": ...}, "surname"),
    ({"mobile": None}, "mobile"),                      # no cellphone and no email
    ({"mobile": "", "email": ""}, "mobile"),
    ({"email": "not-an-email"}, "email"),
])
def test_name_surname_and_a_cellphone_or_email_are_required(client, survey, change, field):
    response = send(client, survey, **change)
    assert response.status_code == 422
    assert field in response.json()["field_errors"]


def test_an_email_instead_of_a_cellphone_is_enough(client, survey, db):
    response = send(client, survey, mobile=None, email="Family@Example.com")
    assert response.status_code == 201, response.text
    assert db.execute("select email, mobile from feedback_responses where id = %s",
                      (response.json()["id"],)).fetchone() == ("family@example.com", None)


def test_the_isizulu_wording_seen_is_kept(client, survey, db):
    response = send(client, survey, first_name="Thandi", surname="Mkhize",
                    mobile="082 123 4567", language="zu")
    assert response.status_code == 201
    row = db.execute(
        "select name, mobile, contact_consent, answers from feedback_responses where id = %s",
        (response.json()["id"],)).fetchone()
    assert row[:3] == ("Thandi Mkhize", "+27821234567", True)
    # The isiZulu wording the person saw is kept, with the English beside it.
    q2 = next(a for a in row[3] if a["id"] == "q2")
    assert q2["question"] == "Sekukonke, waneliseke kangakanani ngomsebenzi wethu?"
    assert q2["question_en"] == "Overall, how satisfied were you with our service?"


def test_answering_is_voluntary_but_something_must_be_answered(client, survey):
    one = send(client, survey, answers=[{"id": "q10", "answer": "Thank you"}])
    assert one.status_code == 201
    none = send(client, survey, answers=[])
    assert none.status_code == 422
    blank = send(client, survey, answers=[{"id": "q10", "answer": "   "}])
    assert blank.status_code == 422


def test_the_short_version_takes_only_its_own_questions(client, survey):
    short = [{"id": "q2", "answer": 4}, {"id": "q9", "answer": 10}]
    assert send(client, survey, version="short", answers=short).status_code == 201
    wrong = send(client, survey, version="short", answers=[{"id": "q1", "answer": "boshoff"}])
    assert wrong.status_code == 422
    assert "answers.q1" in wrong.json()["field_errors"]


@pytest.mark.parametrize("question, answer", [
    ("q1", "durban"),                           # not an option
    ("q2", 6),                                  # off the 1-5 scale
    ("q2", 0),
    ("q9", 11),                                 # off the 0-10 scale
    ("q9", "ten"),
    ("q7", {"casket": "amazing"}),              # not a grid option
    ("q7", {"limousine": "good"}),              # not a grid row
    ("q7", "good"),                             # not one per line
    ("q10", '=HYPERLINK("http://x")'),          # a spreadsheet formula
    ("q4", {"a": "b"}),
    ("q2", "³"),                           # isdigit() but not a number int() reads
    ("q2", "9" * 5000),                         # past int()'s digit limit
    ("q9", "١٠"),                     # Arabic-Indic digits
])
def test_each_kind_of_answer_is_checked(client, survey, question, answer):
    response = send(client, survey, answers=full_answers(**{question: answer}))
    assert response.status_code == 422
    assert f"answers.{question}" in response.json()["field_errors"]


@pytest.mark.parametrize("question, answer", [
    ("q2", True),                               # JSON true is not a 1
    ("q9", False),                              # nor false a 0
    ("q2", 4.0),
])
def test_values_that_only_look_like_numbers_are_refused(client, survey, question, answer):
    response = send(client, survey, answers=full_answers(**{question: answer}))
    assert response.status_code == 422, response.text


def test_a_lone_surrogate_in_a_written_answer_is_refused_not_a_500(client, survey):
    # Sent as raw JSON: the \ud800 escape is valid JSON but no character Postgres can store.
    body = '{"answers": [{"id": "q10", "answer": "good \\ud800 job"}]}'
    response = client.post(f"/api/feedback/{survey}/responses", content=body,
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 422, response.text


def test_a_required_question_must_be_answered(client, survey, db):
    db.execute("""
        update feedback_surveys set questions = jsonb_set(questions, '{1,required}', 'true')
    """)
    response = send(client, survey, answers=full_answers(q2=None))
    assert response.status_code == 422
    assert response.json()["field_errors"]["answers.q2"] == "Please answer this question"


@pytest.mark.parametrize("change", [
    {"mobile": "12345"},
    {"first_name": "<script>"},
    {"name": "Old field"},                       # 0032's single name field is gone
    {"website": "http://spam.example"},          # the honeypot
    {"answers": [{"id": "q1", "answer": "edendale"}, {"id": "q1", "answer": "boshoff"}]},
    {"answers": [{"id": "q99", "answer": "x"}]},
    {"source": "facebook"},
    {"version": "medium"},
])
def test_what_is_sent_is_checked(client, survey, change):
    assert send(client, survey, **change).status_code == 422


def test_no_name_or_number_reaches_the_log(client, survey, caplog):
    with caplog.at_level("INFO"):
        send(client, survey, first_name="Thandi", surname="Mkhize", mobile="082 123 4567",
             email="thandi@example.com")
    assert "Feedback response" in caplog.text
    for secret in ("Thandi", "Mkhize", "4567", "example.com"):
        assert secret not in caplog.text


# --- staff ------------------------------------------------------------------------

def test_staff_must_sign_in(client):
    assert client.get(ADMIN).status_code == 401
    assert client.patch(f"{ADMIN}/survey", json={"is_open": False}).status_code == 401
    assert client.post(f"{ADMIN}/survey/new-link").status_code == 401


def test_staff_see_both_links_and_the_counted_results(client, survey, staff_as):
    send(client, survey, answers=full_answers(q2=5, q9=10, q1="boshoff"))
    send(client, survey, answers=full_answers(q2=3, q9=6, q1="boshoff",
                                              q7={"casket": "poor"}),
         first_name="Sipho", surname="Dube", mobile="0831234567")
    staff_as("viewer")
    overview = client.get(ADMIN).json()
    s = overview["survey"]
    assert s["link"] == f"https://induduzo.co.za/feedback/{survey}"
    assert s["short_link"] == f"https://induduzo.co.za/feedback/{survey}?v=short"
    assert overview["can_edit"] is False
    assert overview["summary"]["named"] >= 1
    results = {r["id"]: r for r in overview["summary"]["questions"]}
    assert results["q1"]["counts"]["boshoff"] >= 2
    assert results["q2"]["average"] is not None
    assert results["q9"]["nps"] is not None and -100 <= results["q9"]["nps"] <= 100
    assert results["q7"]["grid"]["casket"]["poor"] >= 1
    latest = overview["responses"][0]
    assert (latest["first_name"], latest["surname"], latest["mobile"]) == (
        "Sipho", "Dube", "+27831234567")


def test_growth_lists_every_family_who_answered_with_their_scores(client, survey, staff_as):
    assert client.get(f"{ADMIN}/people").status_code == 401
    send(client, survey, first_name="Nomsa", surname="Growthlist", mobile=None,
         email="nomsa@example.com", answers=full_answers(q2=4, q9=10))
    staff_as("viewer")
    body = client.get(f"{ADMIN}/people").json()
    first = body["people"][0]
    assert (first["first_name"], first["surname"], first["email"], first["mobile"]) == (
        "Nomsa", "Growthlist", "nomsa@example.com", None)
    assert (first["satisfaction"], first["recommend"]) == (4, 10)
    assert body["total"] >= 1


def test_staff_are_told_which_question_ids_already_have_answers(client, survey, staff_as):
    send(client, survey, answers=[{"id": "q10", "answer": "Thank you"}])
    staff_as("admin")
    assert "q10" in client.get(ADMIN).json()["answered_ids"]


def test_the_recommend_score_is_promoters_minus_detractors():
    from app.routers.feedback import summarise

    q9 = {"id": "q9", "kind": "scale", "text_en": "Recommend?", "min": 0, "max": 10}
    sets = [[{"id": "q9", "kind": "scale", "answer": n}] for n in (10, 9, 8, 6, 0)]
    result = summarise([q9], sets)[0]
    assert result.nps == round(100 * (2 - 2) / 5)
    assert result.average == 6.6
    assert result.counts["10"] == 1 and result.counts["7"] == 0


def test_a_viewer_cannot_change_the_survey(client, survey, staff_as):
    staff_as("viewer")
    assert client.patch(f"{ADMIN}/survey", json={"is_open": False}).status_code == 403
    assert client.post(f"{ADMIN}/survey/new-link").status_code == 403


def test_an_admin_changes_the_wording_and_questions_and_the_page_follows(client, survey,
                                                                         staff_as):
    staff_as("admin")
    new = [
        {"id": "q1", "kind": "scale", "text_en": "How was the service on the day?",
         "min": 1, "max": 5, "low_en": "Bad", "high_en": "Good", "short": True},
        {"id": "q2", "kind": "choice", "text_en": "Which branch?", "text_zu": "",
         "options": [{"value": "a", "en": "Edendale"}, {"value": "b", "en": "Boshoff", "zu": ""}]},
        {"id": "q3", "kind": "grid", "text_en": "Rate these",
         "rows": [{"value": "tent", "en": "Tent"}],
         "options": [{"value": "good", "en": "Good"}, {"value": "poor", "en": "Poor"}]},
        {"id": "q4", "kind": "text", "text_en": "Anything else?", "required": True},
    ]
    changed = client.patch(f"{ADMIN}/survey", json={
        "questions": new, "title_en": "Tell us how we did", "intro_zu": "",
    })
    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert body["title_en"] == "Tell us how we did" and body["intro_zu"] is None
    assert body["questions"][1]["options"][1]["zu"] is None
    assert body["updated_by"] == "admin@staff.test"
    shown = client.get(f"/api/feedback/{survey}").json()
    assert [q["text_en"] for q in shown["questions"]] == [q["text_en"] for q in new]
    assert [q["id"] for q in client.get(f"/api/feedback/{survey}?v=short").json()["questions"]] \
        == ["q1"]


@pytest.mark.parametrize("bad", [
    {"questions": []},
    {"questions": [{"id": "q1", "kind": "essay", "text_en": "Tell us"}]},
    {"questions": [{"id": "q1", "kind": "text", "text_en": "A"}]},
    {"questions": [{"id": "q1", "kind": "choice", "text_en": "Pick one",
                    "options": [{"value": "a", "en": "Only one"}]}]},
    {"questions": [{"id": "q1", "kind": "choice", "text_en": "Pick one",
                    "options": [{"value": "a", "en": "One"}, {"value": "a", "en": "Same"}]}]},
    {"questions": [{"id": "q1", "kind": "grid", "text_en": "Rate these",
                    "options": [{"value": "a", "en": "A"}, {"value": "b", "en": "B"}]}]},
    {"questions": [{"id": "q1", "kind": "scale", "text_en": "How much?"}]},
    {"questions": [{"id": "q1", "kind": "scale", "text_en": "How much?", "min": 1, "max": 50}]},
    {"questions": [{"id": "q1", "kind": "choice", "text_en": "Pick one",
                    "options": [{"value": "Bad Value!", "en": "x"}, {"value": "b", "en": "y"}]}]},
    {"questions": [{"id": "q1", "kind": "text", "text_en": "Same id"},
                   {"id": "q1", "kind": "text", "text_en": "Same id again"}]},
    {"questions": [{"id": f"q{n}", "kind": "text", "text_en": "Question"} for n in range(16)]},
    {"title_en": ""},
    {"title_en": None},
    {},
])
def test_bad_changes_are_refused(client, survey, staff_as, bad):
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
