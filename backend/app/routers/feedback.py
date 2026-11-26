"""The private feedback questionnaire.

It is not on the website. It opens only at /feedback/<link_code>, the link the
office prints as a QR code and passes on to families. Without the code the
page is the site's ordinary "page not found", and so is this API's answer.

PUBLIC (the questionnaire page, no sign-in)
    GET  /api/feedback/{code}                      the questions
    POST /api/feedback/{code}/responses            name, surname, mobile, answers
    POST /api/feedback/responses/{id}/rating       the 1-5 rating at the end

STAFF (the portal: Settings > Website settings)
    GET   /api/admin/feedback                      link, questions, responses
    PATCH /api/admin/feedback/survey               change questions, open/close (admin, owner)
    POST  /api/admin/feedback/survey/new-link      replace the link (admin, owner)

The response is saved before the rating is asked for, so a person who closes
the page at "rate our service" has still been heard. The rating goes onto that
same response, once, within two hours, addressed by the response's id: a
random uuid only that person's browser was given.

Logs carry the response id, never a name or a number (ARCHITECTURE.md §7.9).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..auth import StaffUser, require_role, require_staff
from ..config import get_settings
from ..db import connection
from ..errors import ApiError
from ..ratelimit import (
    enforce,
    feedback_open_limiter,
    feedback_rating_limiter,
    feedback_send_limiter,
)
from ..schemas import Line, Name, Text, normalise_mobile
from ..services.staff import log_staff_event

logger = logging.getLogger(__name__)

public_router = APIRouter(prefix="/api/feedback", tags=["feedback"])
admin_router = APIRouter(prefix="/api/admin/feedback", tags=["admin"],
                         dependencies=[Depends(require_staff)])

QuestionKind = Literal["text", "yes_no", "scale"]

_CODE_RE = re.compile(r"^[a-z0-9]{10,32}$")
_MOBILE_RE = re.compile(r"^\+27[6-8][0-9]{8}$")
_RATING_WINDOW = "2 hours"
_LIMIT_MESSAGE = ("We have received a lot from this connection. Please try again later, "
                  "or phone us on 069 706 0387.")

# The same answer for a wrong code, a closed questionnaire and a malformed
# code, so trying codes teaches nothing.
_NOT_FOUND = "This page does not exist."


class Question(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    id: str = Field(pattern=r"^q[0-9]{1,2}$")
    kind: QuestionKind
    text_en: Line = Field(min_length=3, max_length=200)
    text_zu: Line | None = Field(default=None, max_length=200)

    @field_validator("text_zu")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return value or None


class QuestionnaireOut(BaseModel):
    questions: list[Question]


class AnswerIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    id: str = Field(pattern=r"^q[0-9]{1,2}$")
    answer: Text = Field(default="", max_length=1000)


class ResponseIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    first_name: Name = Field(min_length=1, max_length=80)
    surname: Name = Field(min_length=1, max_length=80)
    mobile: str
    answers: list[AnswerIn] = Field(max_length=10)
    contact_consent: bool
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

    @field_validator("mobile")
    @classmethod
    def _mobile(cls, value: str) -> str:
        normalised = normalise_mobile(value)
        if not _MOBILE_RE.fullmatch(normalised):
            raise ValueError("Enter a valid South African mobile number, e.g. 082 123 4567")
        return normalised

    @field_validator("contact_consent")
    @classmethod
    def _consent(cls, value: bool) -> bool:
        if not value:
            raise ValueError("We need your permission to keep your answers and contact you")
        return value

    @model_validator(mode="after")
    def _one_answer_each(self) -> "ResponseIn":
        ids = [a.id for a in self.answers]
        if len(ids) != len(set(ids)):
            raise ValueError("Each question may be answered once")
        return self


class ResponseCreated(BaseModel):
    id: UUID


class RatingIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    rating: int = Field(ge=1, le=5)
    comment: Text | None = Field(default=None, max_length=1000)

    @field_validator("comment")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return value or None


class Thanks(BaseModel):
    ok: bool = True


# --------------------------------------------------------------- public ---

def _open_survey(conn, code: str) -> dict:
    if not _CODE_RE.fullmatch(code):
        raise ApiError(status.HTTP_404_NOT_FOUND, "not_found", _NOT_FOUND)
    row = conn.execute(
        "select id, questions from feedback_surveys where link_code = %s and is_open",
        (code,),
    ).fetchone()
    if row is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "not_found", _NOT_FOUND)
    return row


@public_router.get("/{code}", response_model=QuestionnaireOut)
def questionnaire(code: str, request: Request) -> QuestionnaireOut:
    enforce(feedback_open_limiter, request, _LIMIT_MESSAGE)
    with connection() as conn:
        survey = _open_survey(conn, code)
    return QuestionnaireOut(questions=[Question(**q) for q in survey["questions"]])


def _check_answers(questions: list[dict], answers: list[AnswerIn]) -> dict[str, str]:
    """Every question answered in its own form. A written answer may be blank."""
    given = {a.id: a.answer for a in answers}
    known = {q["id"] for q in questions}
    errors: dict[str, str] = {}
    for unknown in sorted(set(given) - known):
        errors[f"answers.{unknown}"] = "This question is no longer asked. Please reload the page."
    for q in questions:
        answer = given.get(q["id"], "")
        if q["kind"] == "yes_no" and answer not in ("yes", "no"):
            errors[f"answers.{q['id']}"] = "Please choose yes or no"
        elif q["kind"] == "scale" and answer not in ("1", "2", "3", "4", "5"):
            errors[f"answers.{q['id']}"] = "Please choose from 1 to 5"
    return errors


@public_router.post("/{code}/responses", response_model=ResponseCreated,
                    status_code=status.HTTP_201_CREATED)
def send_response(code: str, payload: ResponseIn, request: Request) -> ResponseCreated:
    enforce(feedback_send_limiter, request, _LIMIT_MESSAGE)
    with connection() as conn:
        survey = _open_survey(conn, code)
        questions = survey["questions"]
        errors = _check_answers(questions, payload.answers)
        if errors:
            raise _field_errors(errors)
        given = {a.id: a.answer for a in payload.answers}
        # The wording the person actually saw, kept with the answer.
        answers = [{
            "id": q["id"],
            "kind": q["kind"],
            "question": (q.get("text_zu") if payload.language == "zu" else None) or q["text_en"],
            "answer": given.get(q["id"], ""),
        } for q in questions]
        response_id = conn.execute(
            """
            insert into feedback_responses
                   (survey_id, first_name, surname, mobile, answers,
                    contact_consent, source, language)
            values (%s, %s, %s, %s, %s::jsonb, true, %s, %s)
            returning id
            """,
            (survey["id"], payload.first_name, payload.surname, payload.mobile,
             json.dumps(answers), payload.source, payload.language),
        ).fetchone()["id"]
    logger.info("Feedback response %s received (%s)", response_id, payload.source)
    return ResponseCreated(id=response_id)


def _field_errors(errors: dict[str, str]) -> RequestValidationError:
    """A 422 shaped like every other validation failure, with field_errors the
    page can put beside the right question."""
    return RequestValidationError([
        {"loc": ("body", *key.split(".")), "msg": message, "type": "value_error"}
        for key, message in errors.items()
    ])


@public_router.post("/responses/{response_id}/rating", response_model=Thanks)
def rate(response_id: UUID, payload: RatingIn, request: Request) -> Thanks:
    enforce(feedback_rating_limiter, request, _LIMIT_MESSAGE)
    with connection() as conn:
        row = conn.execute(
            f"""
            update feedback_responses
               set rating = %s, rating_comment = %s, rated_at = now()
             where id = %s and rating is null
               and created_at > now() - interval '{_RATING_WINDOW}'
            returning id
            """,
            (payload.rating, payload.comment, response_id),
        ).fetchone()
    if row is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "not_found",
                       "This rating has already been given, or the page has expired.")
    logger.info("Feedback response %s rated", response_id)
    return Thanks()


# ---------------------------------------------------------------- staff ---

class SurveyOut(BaseModel):
    link_code: str
    link: str
    is_open: bool
    questions: list[Question]
    updated_at: datetime
    updated_by: str | None


class FeedbackRow(BaseModel):
    id: UUID
    first_name: str
    surname: str
    mobile: str
    answers: list[dict]
    source: str
    language: str
    rating: int | None
    rating_comment: str | None
    created_at: datetime


class FeedbackSummary(BaseModel):
    responses: int
    rated: int
    # A display figure (e.g. 4.3), never money, so a float is right here.
    average_rating: float | None
    by_rating: dict[str, int]


class FeedbackAdminOut(BaseModel):
    survey: SurveyOut
    summary: FeedbackSummary
    responses: list[FeedbackRow]
    can_edit: bool


class SurveyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[Question] | None = Field(default=None, min_length=1, max_length=10)
    is_open: bool | None = None

    @field_validator("questions")
    @classmethod
    def _unique_ids(cls, value: list[Question] | None) -> list[Question] | None:
        if value is not None and len({q.id for q in value}) != len(value):
            raise ValueError("Each question needs its own id")
        return value


def _survey_out(row: dict) -> SurveyOut:
    base = get_settings().public_site_url
    return SurveyOut(
        link_code=row["link_code"],
        link=f"{base}/feedback/{row['link_code']}",
        is_open=row["is_open"],
        questions=[Question(**q) for q in row["questions"]],
        updated_at=row["updated_at"],
        updated_by=row["updated_by"],
    )


_SURVEY_COLUMNS = "id, link_code, is_open, questions, updated_at, updated_by"


def _the_survey(conn) -> dict:
    row = conn.execute(f"select {_SURVEY_COLUMNS} from feedback_surveys limit 1").fetchone()
    if row is None:
        # Migration 0032 creates it; reaching this means the migration did not run.
        raise ApiError(status.HTTP_503_SERVICE_UNAVAILABLE, "service_unavailable",
                       "The questionnaire is not set up on this server yet.")
    return row


@admin_router.get("", response_model=FeedbackAdminOut)
def feedback_overview(staff: StaffUser = Depends(require_staff)) -> FeedbackAdminOut:
    with connection() as conn:
        survey = _the_survey(conn)
        counts = conn.execute(
            """
            select count(*) as responses, count(rating) as rated,
                   round(avg(rating)::numeric, 1)::float as average_rating,
                   count(*) filter (where rating = 1) as r1,
                   count(*) filter (where rating = 2) as r2,
                   count(*) filter (where rating = 3) as r3,
                   count(*) filter (where rating = 4) as r4,
                   count(*) filter (where rating = 5) as r5
              from feedback_responses where survey_id = %s
            """,
            (survey["id"],),
        ).fetchone()
        rows = conn.execute(
            """
            select id, first_name, surname, mobile, answers, source, language,
                   rating, rating_comment, created_at
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
        summary=FeedbackSummary(
            responses=counts["responses"], rated=counts["rated"],
            average_rating=counts["average_rating"],
            by_rating={str(n): counts[f"r{n}"] for n in range(1, 6)},
        ),
        responses=[FeedbackRow(**r) for r in rows],
        can_edit=staff.role in ("admin", "owner"),
    )


@admin_router.patch("/survey", response_model=SurveyOut)
def change_survey(payload: SurveyIn,
                  staff: StaffUser = Depends(require_role("admin"))) -> SurveyOut:
    if payload.questions is None and payload.is_open is None:
        raise ApiError(422, "validation_failed",
                       "Nothing to change.")
    with connection() as conn:
        survey = _the_survey(conn)
        questions = (json.dumps([q.model_dump() for q in payload.questions])
                     if payload.questions is not None else None)
        row = conn.execute(
            f"""
            update feedback_surveys
               set questions  = coalesce(%s::jsonb, questions),
                   is_open    = coalesce(%s, is_open),
                   updated_by = %s,
                   updated_at = now()
             where id = %s
            returning {_SURVEY_COLUMNS}
            """,
            (questions, payload.is_open, staff.email, survey["id"]),
        ).fetchone()
        log_staff_event(conn, staff.email, "feedback_survey_changed", str(survey["id"]), {
            "questions": len(payload.questions) if payload.questions is not None else None,
            "is_open": payload.is_open,
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
