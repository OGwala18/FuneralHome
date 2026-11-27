"""The private feedback questionnaire: the owner's post-funeral survey.

It is not on the website. It opens only at /feedback/<link_code>, the link the
office sends with its WhatsApp condolence message or prints as a QR code.
Without the code the page is the site's ordinary "page not found", and so is
this API's answer. ?v=short asks only the questions marked short (the owner's
five-question version).

PUBLIC (the questionnaire page, no sign-in)
    GET  /api/feedback/{code}?v=full|short     title, introduction, questions
    POST /api/feedback/{code}/responses        the answers, optionally a name and number

STAFF (the portal: Settings > Website settings)
    GET   /api/admin/feedback                  links, questions, results, responses
    GET   /api/admin/feedback/people           the families who answered, for Growth
    PATCH /api/admin/feedback/survey           change the wording, questions, open/close (admin, owner)
    POST  /api/admin/feedback/survey/new-link  replace the link (admin, owner)

Answering each question is voluntary, but since 27 Nov 2026 (migration 0033)
every family gives a first name and surname, and a cellphone number or an
email address, so the office can follow up and see them under Growth. The page
says plainly that giving them is agreeing to be contacted about the feedback,
so contact_consent is recorded.

A question is one of four kinds, each in English and isiZulu:
    choice  pick one of `options`
    scale   a whole number from `min` to `max` (1-5, or 0-10), words at each end
    grid    each of `rows` rated on the same `options` (e.g. Excellent ... Not used)
    text    a written answer

Logs carry the response id, never a name or a number (ARCHITECTURE.md §7.9).
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import (BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator,
                      model_validator)

from ..auth import StaffUser, require_role, require_staff
from ..config import get_settings
from ..db import connection
from ..errors import ApiError
from ..ratelimit import enforce, feedback_open_limiter, feedback_send_limiter
from ..schemas import (_EMAIL_RE, _FORMULA_START, Line, Name, Text, clean_text,
                       normalise_mobile)
from ..services.staff import log_staff_event

logger = logging.getLogger(__name__)

public_router = APIRouter(prefix="/api/feedback", tags=["feedback"])
admin_router = APIRouter(prefix="/api/admin/feedback", tags=["admin"],
                         dependencies=[Depends(require_staff)])

QuestionKind = Literal["choice", "scale", "grid", "text"]
Version = Literal["full", "short"]

_CODE_RE = re.compile(r"^[a-z0-9]{10,32}$")
_MOBILE_RE = re.compile(r"^\+27[6-8][0-9]{8}$")
_LIMIT_MESSAGE = ("We have received a lot from this connection. Please try again later, "
                  "or phone us on 069 706 0387.")
MAX_QUESTIONS = 15
MAX_TEXT_ANSWER = 2000

# The same answer for a wrong code, a closed questionnaire and a malformed
# code, so trying codes teaches nothing.
_NOT_FOUND = "This page does not exist."


# ------------------------------------------------------------ questions ---

class Choice(BaseModel):
    """One option of a choice or grid question, or one row of a grid."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    value: str = Field(pattern=r"^[a-z0-9_]{1,40}$")
    en: Line = Field(min_length=1, max_length=120)
    zu: Line | None = Field(default=None, max_length=120)

    @field_validator("zu")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return value or None


class Question(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    id: str = Field(pattern=r"^q[0-9]{1,2}$")
    kind: QuestionKind
    text_en: Line = Field(min_length=3, max_length=300)
    text_zu: Line | None = Field(default=None, max_length=300)
    # In the five-question short version (?v=short).
    short: bool = False
    required: bool = False
    options: list[Choice] | None = Field(default=None, max_length=12)
    rows: list[Choice] | None = Field(default=None, max_length=12)
    min: int | None = Field(default=None, ge=0, le=1)
    max: int | None = Field(default=None, ge=2, le=10)
    low_en: Line | None = Field(default=None, max_length=60)
    low_zu: Line | None = Field(default=None, max_length=60)
    high_en: Line | None = Field(default=None, max_length=60)
    high_zu: Line | None = Field(default=None, max_length=60)

    @field_validator("text_zu", "low_en", "low_zu", "high_en", "high_zu")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def _shape(self) -> "Question":
        def unique(items: list[Choice], what: str) -> None:
            if len({i.value for i in items}) != len(items):
                raise ValueError(f"Two {what} have the same wording")

        if self.kind in ("choice", "grid"):
            if not self.options or len(self.options) < 2:
                raise ValueError("Give at least two options to choose from")
            unique(self.options, "options")
        else:
            self.options = None
        if self.kind == "grid":
            if not self.rows:
                raise ValueError("Give at least one thing to rate")
            unique(self.rows, "things to rate")
        else:
            self.rows = None
        if self.kind == "scale":
            if self.min is None or self.max is None:
                raise ValueError("A scale needs its lowest and highest number")
        else:
            self.min = self.max = None
            self.low_en = self.low_zu = self.high_en = self.high_zu = None
        return self


class QuestionnaireOut(BaseModel):
    title_en: str
    title_zu: str | None
    intro_en: str
    intro_zu: str | None
    version: Version
    questions: list[Question]


# -------------------------------------------------------------- answers ---

class AnswerIn(BaseModel):
    # Strip whitespace also makes pydantic refuse a lone UTF-16 surrogate, which
    # Postgres cannot store (a 500 otherwise).
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(pattern=r"^q[0-9]{1,2}$")
    # choice: an option's value. scale: the number. grid: {row: option}. text: the words.
    # Strict: JSON true, false and 4.0 are not numbers on a scale.
    answer: StrictInt | StrictStr | dict[StrictStr, StrictStr]


class ResponseIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    answers: list[AnswerIn] = Field(max_length=MAX_QUESTIONS)
    first_name: Name = Field(min_length=1, max_length=80)
    surname: Name = Field(min_length=1, max_length=80)
    # At least one of the two (checked in send_response, as a field error).
    mobile: str | None = None
    email: str | None = Field(default=None, max_length=255)
    version: Version = "full"
    source: Literal["qr", "link"] = "link"
    language: Literal["en", "zu"] = "en"
    # Honeypot, as on the enquiry form: hidden from people, filled by bots.
    website: str = ""

    @field_validator("website")
    @classmethod
    def _honeypot(cls, value: str) -> str:
        if value.strip():
            raise ValueError("Enter a valid value")
        return ""

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        if not _EMAIL_RE.fullmatch(value) or value.startswith(_FORMULA_START):
            raise ValueError("Enter a valid email address")
        return value.lower()

    @field_validator("mobile")
    @classmethod
    def _mobile(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        normalised = normalise_mobile(value)
        if not _MOBILE_RE.fullmatch(normalised):
            raise ValueError("Enter a valid South African cellphone number, e.g. 082 123 4567")
        return normalised

    @model_validator(mode="after")
    def _one_answer_each(self) -> "ResponseIn":
        ids = [a.id for a in self.answers]
        if len(ids) != len(set(ids)):
            raise ValueError("Each question may be answered once")
        return self


class ResponseCreated(BaseModel):
    id: UUID


def _label(items: list[dict], value: str) -> str:
    return next((i["en"] for i in items if i["value"] == value), value)


def _check_answers(questions: list[dict], answers: list[AnswerIn],
                   language: str) -> tuple[list[dict], dict[str, str]]:
    """The answers as stored, with the wording shown and an English label, and
    any field errors keyed answers.<id>."""
    given = {a.id: a.answer for a in answers}
    known = {q["id"] for q in questions}
    errors: dict[str, str] = {}
    for unknown in sorted(set(given) - known):
        errors[f"answers.{unknown}"] = "This question is no longer asked. Please reload the page."

    stored: list[dict] = []
    for q in questions:
        key = f"answers.{q['id']}"
        raw = given.get(q["id"])
        if raw is None or raw == "" or raw == {}:
            if q.get("required"):
                errors[key] = "Please answer this question"
            continue
        kind = q["kind"]
        answer: Any
        if kind == "choice":
            if not isinstance(raw, str) or raw not in {o["value"] for o in q["options"]}:
                errors[key] = "Please choose one of the answers"
                continue
            answer, label = raw, _label(q["options"], raw)
        elif kind == "scale":
            # One or two ASCII digits only: str.isdigit() also passes '³', which
            # int() refuses, and a 5,000-digit string would exceed int()'s limit.
            number = raw if isinstance(raw, int) else (
                int(raw) if isinstance(raw, str) and re.fullmatch(r"[0-9]{1,2}", raw) else None)
            if number is None or not q["min"] <= number <= q["max"]:
                errors[key] = f"Please choose from {q['min']} to {q['max']}"
                continue
            answer, label = number, str(number)
        elif kind == "grid":
            rows = {r["value"]: r for r in q["rows"]}
            options = {o["value"] for o in q["options"]}
            if (not isinstance(raw, dict) or not set(raw) <= set(rows)
                    or not set(raw.values()) <= options
                    or (q.get("required") and set(raw) != set(rows))):
                errors[key] = "Please choose one answer for each line"
                continue
            answer = {r: raw[r] for r in rows if r in raw}
            label = "; ".join(f"{rows[r]['en']}: {_label(q['options'], v)}"
                              for r, v in answer.items())
        else:
            if not isinstance(raw, str):
                errors[key] = "Please write your answer"
                continue
            try:
                answer = (clean_text(raw.strip()) or "")[:MAX_TEXT_ANSWER]
            except ValueError as exc:
                errors[key] = str(exc)
                continue
            if not answer:
                if q.get("required"):
                    errors[key] = "Please answer this question"
                continue
            label = answer
        stored.append({
            "id": q["id"],
            "kind": kind,
            "question": (q.get("text_zu") if language == "zu" else None) or q["text_en"],
            "question_en": q["text_en"],
            "answer": answer,
            "label": label,
        })
    return stored, errors


def _field_errors(errors: dict[str, str]) -> RequestValidationError:
    """A 422 shaped like every other validation failure, with field_errors the
    page can put beside the right question."""
    return RequestValidationError([
        {"loc": ("body", *key.split(".")), "msg": message, "type": "value_error"}
        for key, message in errors.items()
    ])


# --------------------------------------------------------------- public ---

_SURVEY_COLUMNS = ("id, link_code, title_en, title_zu, intro_en, intro_zu, is_open, questions, "
                   "updated_at, updated_by")


def _open_survey(conn, code: str) -> dict:
    if not _CODE_RE.fullmatch(code):
        raise ApiError(status.HTTP_404_NOT_FOUND, "not_found", _NOT_FOUND)
    row = conn.execute(
        f"select {_SURVEY_COLUMNS} from feedback_surveys where link_code = %s and is_open",
        (code,),
    ).fetchone()
    if row is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "not_found", _NOT_FOUND)
    return row


def asked(questions: list[dict], version: str) -> list[dict]:
    """The questions a version asks. A short version with none marked asks them all."""
    if version == "short":
        return [q for q in questions if q.get("short")] or questions
    return questions


@public_router.get("/{code}", response_model=QuestionnaireOut)
def questionnaire(code: str, request: Request,
                  v: Version = Query(default="full")) -> QuestionnaireOut:
    enforce(feedback_open_limiter, request, _LIMIT_MESSAGE)
    with connection() as conn:
        survey = _open_survey(conn, code)
    return QuestionnaireOut(
        title_en=survey["title_en"], title_zu=survey["title_zu"],
        intro_en=survey["intro_en"], intro_zu=survey["intro_zu"], version=v,
        questions=[Question(**q) for q in asked(survey["questions"], v)],
    )


@public_router.post("/{code}/responses", response_model=ResponseCreated,
                    status_code=status.HTTP_201_CREATED)
def send_response(code: str, payload: ResponseIn, request: Request) -> ResponseCreated:
    enforce(feedback_send_limiter, request, _LIMIT_MESSAGE)
    with connection() as conn:
        survey = _open_survey(conn, code)
        answers, errors = _check_answers(asked(survey["questions"], payload.version),
                                         payload.answers, payload.language)
        if errors:
            raise _field_errors(errors)
        if not answers:
            raise ApiError(422, "validation_failed",
                           "Please answer at least one question before sending.")
        if payload.mobile is None and payload.email is None:
            raise _field_errors({"mobile": "Give a cellphone number or an email address"})
        response_id = conn.execute(
            """
            insert into feedback_responses
                   (survey_id, first_name, surname, name, mobile, email, answers,
                    contact_consent, version, source, language)
            values (%s, %s, %s, %s, %s, %s, %s::jsonb, true, %s, %s, %s)
            returning id
            """,
            (survey["id"], payload.first_name, payload.surname,
             f"{payload.first_name} {payload.surname}"[:120], payload.mobile, payload.email,
             json.dumps(answers, ensure_ascii=False), payload.version, payload.source,
             payload.language),
        ).fetchone()["id"]
    logger.info("Feedback response %s received (%s, %s)", response_id, payload.version,
                payload.source)
    return ResponseCreated(id=response_id)


# ---------------------------------------------------------------- staff ---

class SurveyOut(BaseModel):
    link_code: str
    link: str
    short_link: str
    title_en: str
    title_zu: str | None
    intro_en: str
    intro_zu: str | None
    is_open: bool
    questions: list[Question]
    updated_at: datetime
    updated_by: str | None


class FeedbackRow(BaseModel):
    id: UUID
    first_name: str | None
    surname: str | None
    name: str | None
    mobile: str | None
    email: str | None
    answers: list[dict]
    version: str
    source: str
    language: str
    created_at: datetime


class QuestionResult(BaseModel):
    """What everyone said to one question, counted."""

    id: str
    kind: str
    text_en: str
    answered: int
    # scale: the mean, and for 0-10 the recommend score (NPS: % 9-10 minus % 0-6).
    average: float | None = None
    nps: int | None = None
    # choice and scale: {value: count}. grid: {row: {option: count}}.
    counts: dict[str, int] | None = None
    grid: dict[str, dict[str, int]] | None = None


class FeedbackSummary(BaseModel):
    responses: int
    named: int
    short_version: int
    # Counted from up to the latest 5,000 responses.
    questions: list[QuestionResult]


class FeedbackAdminOut(BaseModel):
    survey: SurveyOut
    summary: FeedbackSummary
    responses: list[FeedbackRow]
    can_edit: bool
    # Every question id that has answers on record, current or removed. A new
    # question must not take one, or it would inherit those answers' results.
    answered_ids: list[str]


class SurveyIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    questions: list[Question] | None = Field(default=None, min_length=1,
                                             max_length=MAX_QUESTIONS)
    is_open: bool | None = None
    title_en: Line | None = Field(default=None, min_length=1, max_length=120)
    title_zu: Line | None = Field(default=None, max_length=120)
    intro_en: Text | None = Field(default=None, min_length=1, max_length=1000)
    intro_zu: Text | None = Field(default=None, max_length=1000)

    @field_validator("questions")
    @classmethod
    def _unique_ids(cls, value: list[Question] | None) -> list[Question] | None:
        if value is not None and len({q.id for q in value}) != len(value):
            raise ValueError("Each question needs its own id")
        return value


def _survey_out(row: dict) -> SurveyOut:
    link = f"{get_settings().public_site_url}/feedback/{row['link_code']}"
    return SurveyOut(
        link_code=row["link_code"], link=link, short_link=f"{link}?v=short",
        title_en=row["title_en"], title_zu=row["title_zu"],
        intro_en=row["intro_en"], intro_zu=row["intro_zu"],
        is_open=row["is_open"],
        questions=[Question(**q) for q in row["questions"]],
        updated_at=row["updated_at"], updated_by=row["updated_by"],
    )


def _the_survey(conn) -> dict:
    row = conn.execute(f"select {_SURVEY_COLUMNS} from feedback_surveys limit 1").fetchone()
    if row is None:
        # Migration 0032 creates it; reaching this means the migration did not run.
        raise ApiError(status.HTTP_503_SERVICE_UNAVAILABLE, "service_unavailable",
                       "The questionnaire is not set up on this server yet.")
    return row


def _id_order(question_id: str) -> int:
    return int(question_id[1:]) if re.fullmatch(r"q[0-9]+", question_id or "") else 0


def summarise(questions: list[dict], answer_sets: list[list[dict]]) -> list[QuestionResult]:
    """Count every answer, per question, against the questions as they are now.
    An answer for an option since removed is still counted, under its value."""
    results = []
    for q in questions:
        mine = [a["answer"] for answers in answer_sets for a in answers
                if a.get("id") == q["id"] and a.get("kind") == q["kind"]]
        result = QuestionResult(id=q["id"], kind=q["kind"], text_en=q["text_en"],
                                answered=len(mine))
        if q["kind"] == "scale":
            numbers = [n for n in mine if isinstance(n, int)]
            tally = Counter(numbers)
            result.counts = {str(n): tally.get(n, 0) for n in range(q["min"], q["max"] + 1)}
            if numbers:
                result.average = round(sum(numbers) / len(numbers), 1)
                if q["min"] == 0 and q["max"] == 10:
                    promoters = sum(1 for n in numbers if n >= 9)
                    detractors = sum(1 for n in numbers if n <= 6)
                    result.nps = round(100 * (promoters - detractors) / len(numbers))
        elif q["kind"] == "choice":
            tally = Counter(a for a in mine if isinstance(a, str))
            result.counts = {o["value"]: tally.get(o["value"], 0) for o in q["options"]}
            for value, n in tally.items():
                result.counts.setdefault(value, n)
        elif q["kind"] == "grid":
            grid: dict[str, dict[str, int]] = {
                r["value"]: {o["value"]: 0 for o in q["options"]} for r in q["rows"]}
            for answer in mine:
                if isinstance(answer, dict):
                    for row, option in answer.items():
                        cell = grid.setdefault(row, {})
                        cell[option] = cell.get(option, 0) + 1
            result.grid = grid
        results.append(result)
    return results


@admin_router.get("", response_model=FeedbackAdminOut)
def feedback_overview(staff: StaffUser = Depends(require_staff)) -> FeedbackAdminOut:
    with connection() as conn:
        survey = _the_survey(conn)
        counts = conn.execute(
            """
            select count(*) as responses,
                   count(*) filter (where contact_consent) as named,
                   count(*) filter (where version = 'short') as short_version
              from feedback_responses where survey_id = %s
            """,
            (survey["id"],),
        ).fetchone()
        answer_sets = [r["answers"] for r in conn.execute(
            "select answers from feedback_responses where survey_id = %s "
            "order by created_at desc limit 5000", (survey["id"],)).fetchall()]
        conn_answered_ids = conn.execute(
            "select distinct a->>'id' as id from feedback_responses r, "
            "jsonb_array_elements(r.answers) a where r.survey_id = %s", (survey["id"],)).fetchall()
        rows = conn.execute(
            """
            select id, first_name, surname, name, mobile, email, answers, version, source,
                   language, created_at
              from feedback_responses
             where survey_id = %s
             order by created_at desc
             limit 200
            """,
            (survey["id"],),
        ).fetchall()
        log_staff_event(conn, staff.email, "feedback_viewed", None, {"rows": len(rows)})
    return FeedbackAdminOut(
        survey=_survey_out(survey),
        summary=FeedbackSummary(responses=counts["responses"], named=counts["named"],
                                short_version=counts["short_version"],
                                questions=summarise(survey["questions"], answer_sets)),
        responses=[FeedbackRow(**r) for r in rows],
        can_edit=staff.role in ("admin", "owner"),
        answered_ids=sorted({r["id"] for r in conn_answered_ids}, key=_id_order),
    )


class FeedbackPerson(BaseModel):
    """One family who answered, as Growth lists them."""

    id: UUID
    first_name: str | None
    surname: str | None
    # Responses saved before 0033 have only this.
    name: str | None
    mobile: str | None
    email: str | None
    created_at: datetime
    version: str
    source: str
    # Q2 "how satisfied" (1-5) and Q9 "how likely to recommend" (0-10), when answered.
    satisfaction: int | None = None
    recommend: int | None = None


class FeedbackPeople(BaseModel):
    people: list[FeedbackPerson]
    total: int
    anonymous: int


def _scale_answer(answers: list[dict], question_id: str) -> int | None:
    value = next((a.get("answer") for a in answers if a.get("id") == question_id
                  and a.get("kind") == "scale"), None)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


@admin_router.get("/people", response_model=FeedbackPeople)
def feedback_people(staff: StaffUser = Depends(require_staff)) -> FeedbackPeople:
    """Everyone who answered the questionnaire and left their details, newest
    first (the latest 1,000). For Growth."""
    with connection() as conn:
        counts = conn.execute(
            "select count(*) filter (where contact_consent) as named, "
            "count(*) filter (where not contact_consent) as anonymous from feedback_responses"
        ).fetchone()
        rows = conn.execute(
            """
            select id, first_name, surname, name, mobile, email, created_at, version, source,
                   answers
              from feedback_responses
             where contact_consent
             order by created_at desc
             limit 1000
            """
        ).fetchall()
        log_staff_event(conn, staff.email, "feedback_people_viewed", None, {"rows": len(rows)})
    people = [FeedbackPerson(
        **{k: r[k] for k in ("id", "first_name", "surname", "name", "mobile", "email",
                              "created_at", "version", "source")},
        satisfaction=_scale_answer(r["answers"], "q2"),
        recommend=_scale_answer(r["answers"], "q9"),
    ) for r in rows]
    return FeedbackPeople(people=people, total=counts["named"], anonymous=counts["anonymous"])


@admin_router.patch("/survey", response_model=SurveyOut)
def change_survey(payload: SurveyIn,
                  staff: StaffUser = Depends(require_role("admin"))) -> SurveyOut:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise ApiError(422, "validation_failed", "Nothing to change.")
    for required in ("title_en", "intro_en", "is_open", "questions"):
        if required in changes and changes[required] is None:
            raise ApiError(422, "validation_failed", f"{required} cannot be blank.")
    with connection() as conn:
        survey = _the_survey(conn)
        sets = ["updated_by = %(staff)s", "updated_at = now()"]
        params: dict[str, Any] = {"staff": staff.email, "id": survey["id"]}
        if payload.questions is not None:
            sets.append("questions = %(questions)s::jsonb")
            params["questions"] = json.dumps(
                [q.model_dump(exclude_none=True) for q in payload.questions], ensure_ascii=False)
        for column in ("is_open", "title_en", "title_zu", "intro_en", "intro_zu"):
            if column in changes:
                sets.append(f"{column} = %({column})s")
                value = changes[column]
                params[column] = (value or None) if column.endswith("_zu") else value
        row = conn.execute(
            f"update feedback_surveys set {', '.join(sets)} where id = %(id)s "
            f"returning {_SURVEY_COLUMNS}",
            params,
        ).fetchone()
        log_staff_event(conn, staff.email, "feedback_survey_changed", str(survey["id"]), {
            "changed": sorted(changes),
            "questions": len(payload.questions) if payload.questions is not None else None,
        })
    return _survey_out(row)


@admin_router.post("/survey/new-link", response_model=SurveyOut)
def new_link(staff: StaffUser = Depends(require_role("admin"))) -> SurveyOut:
    """A new link. The old one, and every QR code printed from it, stops at once."""
    with connection() as conn:
        survey = _the_survey(conn)
        row = conn.execute(
            f"""
            update feedback_surveys
               set link_code  = substr(replace(gen_random_uuid()::text, '-', ''), 1, 12),
                   updated_by = %s,
                   updated_at = now()
             where id = %s
            returning {_SURVEY_COLUMNS}
            """,
            (staff.email, survey["id"]),
        ).fetchone()
        log_staff_event(conn, staff.email, "feedback_link_replaced", str(survey["id"]), {})
    return _survey_out(row)
