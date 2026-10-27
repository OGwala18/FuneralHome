"""The WhatsApp menu, walked step by step: docs/feature-3-whatsapp-line.md §5.

No database and no Twilio: services/whatsapp_menu.py is pure, so each test is
messages in and replies out. The content checks at the bottom keep the menu's
words honest: every option leads somewhere, every message fits in one
WhatsApp, and the plans match the website.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.services import whatsapp_content as content
from app.services import whatsapp_menu as menu
from app.services.whatsapp_content import NODES, SAST

REPO = Path(__file__).resolve().parents[2]

# A Tuesday morning, when the office is open.
OPEN = datetime(2026, 10, 27, 10, 0, tzinfo=SAST)
# A Saturday afternoon, after the office has closed.
CLOSED = datetime(2026, 10, 31, 14, 0, tzinfo=SAST)


class Chat:
    """One family, one conversation, threaded through respond()."""

    def __init__(self, now: datetime = OPEN) -> None:
        self.state, self.data, self.misses = menu.IDLE, {}, 0
        self.now = now
        self.last: datetime | None = None
        self.turns: list[menu.Turn] = []

    def send(self, text: str = "", *, media: bool = False, after: timedelta = timedelta(seconds=20)) -> menu.Turn:
        self.now += after
        turn = menu.respond(state=self.state, data=self.data, misses=self.misses, text=text,
                            has_media=media, now=self.now, idle_since=self.last)
        self.state, self.data, self.misses = turn.state, turn.data, turn.misses
        self.last = self.now
        self.turns.append(turn)
        return turn

    @property
    def reply(self) -> str:
        return "\n".join(self.turns[-1].replies)


# ----------------------------------------------------------------- Greeting ---

def test_a_first_message_gets_the_greeting_and_the_seven_topics():
    chat = Chat()
    turn = chat.send("Hello")

    assert chat.state == "main"
    assert turn.replies[0].startswith(content.GREETING)
    for i, option in enumerate(NODES["main"].options, start=1):
        assert f"{i}. {option.label}" in chat.reply
    assert len(NODES["main"].options) == 7


def test_any_first_message_gets_the_greeting_even_a_number():
    chat = Chat()
    chat.send("3")
    assert chat.state == "main"
    assert content.GREETING in chat.reply


def test_half_an_hour_of_silence_starts_again():
    chat = Chat()
    chat.send("hi")
    chat.send("2")
    assert chat.state == "claims"

    chat.send("1", after=timedelta(minutes=31))
    assert chat.state == "main"
    assert content.GREETING in chat.reply


def test_a_reply_within_half_an_hour_carries_on():
    chat = Chat()
    chat.send("hi")
    chat.send("2", after=timedelta(minutes=29))
    assert chat.state == "claims"


@pytest.mark.parametrize("word", ["menu", "MENU", "0", "Menu."])
def test_menu_and_zero_go_back_to_the_main_menu(word):
    chat = Chat()
    chat.send("hi")
    chat.send("3")
    chat.send(word)
    assert chat.state == "main"


@pytest.mark.parametrize("typed", ["2", " 2 ", "2.", "(2)", "2️⃣"])
def test_numbers_are_read_the_way_people_type_them(typed):
    chat = Chat()
    chat.send("hi")
    chat.send(typed)
    assert chat.state == "claims"


# ------------------------------------------------------------------ Topics ---

@pytest.mark.parametrize("topic", range(1, 8))
def test_every_topic_opens_and_offers_none_of_these(topic):
    chat = Chat()
    chat.send("hi")
    chat.send(str(topic))
    node = NODES[chat.state]

    assert node.kind == "menu"
    assert node.options[-1].label == "None of these"
    assert f"{len(node.options)}. None of these" in chat.reply


def _answers() -> list[tuple[str, str]]:
    """Every (topic number, option number) that ends at an answer."""
    found = []
    for t, topic in enumerate(NODES["main"].options, start=1):
        for o, option in enumerate(NODES[topic.goto].options, start=1):
            if option.goto in NODES and NODES[option.goto].kind == "answer":
                found.append((str(t), str(o)))
    return found


@pytest.mark.parametrize("topic, option", _answers())
def test_every_answer_is_reached_and_asks_whether_it_helped(topic, option):
    chat = Chat()
    chat.send("hi")
    chat.send(topic)
    chat.send(option)

    assert NODES[chat.state].kind == "answer"
    assert NODES[chat.state].text in chat.reply
    assert content.ANSWER_FOLLOW_UP in chat.reply


def test_someone_has_passed_away_gives_the_24_hour_numbers_straight_away():
    chat = Chat()
    chat.send("hi")
    chat.send("1")

    assert chat.state == "death"
    assert content.PHONES_24H in chat.reply
    # Help is in the same message as the options, not behind another step.
    assert len(chat.turns[-1].replies) == 1


def test_please_phone_me_now_is_urgent_and_escalates_at_once():
    chat = Chat()
    chat.send("hi")
    chat.send("1")
    turn = chat.send("1")

    assert turn.escalate == menu.Escalate(channel="call", urgent=True, topic="death")
    assert chat.state == menu.ESCALATED
    assert content.PHONES_24H in chat.reply


def test_bereavement_out_of_hours_says_call_now_and_when_the_office_will():
    chat = Chat(now=CLOSED)
    chat.send("hi")
    chat.send("1")
    chat.send("1")

    assert "please call" in chat.reply
    assert "at 08:00 on Monday" in chat.reply


def test_a_topic_can_lead_to_another_topic():
    chat = Chat()
    chat.send("hi")
    chat.send("4")   # My policy
    chat.send("3")   # What my plan covers
    assert chat.state == "plans"


# ---------------------------------------------------------- Asking a person ---

def test_none_of_these_offers_going_back_or_a_person():
    chat = Chat()
    chat.send("hi")
    chat.send("2")
    chat.send("5")   # None of these

    assert chat.state == "agent"
    assert chat.data == {"back": "claims", "topic": "claims"}
    assert "1. Go back" in chat.reply
    assert "2. A person replies to me here on WhatsApp" in chat.reply
    assert "3. A person phones me" in chat.reply
    assert content.HOURS_TEXT in chat.reply


def test_go_back_returns_to_the_topic():
    chat = Chat()
    chat.send("hi")
    chat.send("2")
    chat.send("5")
    chat.send("1")
    assert chat.state == "claims"


@pytest.mark.parametrize("pick, channel", [("2", "whatsapp"), ("3", "call")])
def test_asking_for_a_person_escalates_with_the_topic(pick, channel):
    chat = Chat()
    chat.send("hi")
    chat.send("3")   # Paying my premium
    chat.send("5")   # None of these
    turn = chat.send(pick)

    assert turn.escalate == menu.Escalate(channel=channel, urgent=False, topic="pay")
    assert chat.state == menu.ESCALATED
    assert "as soon as possible" in chat.reply


def test_out_of_hours_the_family_is_told_when_the_office_opens():
    chat = Chat(now=CLOSED)
    chat.send("hi")
    chat.send("2")
    chat.send("5")
    chat.send("3")

    assert "The office is closed now" in chat.reply
    assert "at 08:00 on Monday" in chat.reply


def test_no_after_an_answer_offers_a_person_about_that_answer():
    chat = Chat()
    chat.send("hi")
    chat.send("3")
    chat.send("3")   # Wrong amount
    chat.send("2")   # No, I need more help

    assert chat.state == "agent"
    assert chat.data == {"back": "pay", "topic": "pay.wrong"}
    turn = chat.send("3")
    assert turn.escalate.topic == "pay.wrong"


def test_a_complaint_goes_to_a_person_by_their_choice():
    chat = Chat()
    chat.send("hi")
    chat.send("7")
    chat.send("1")   # Make a complaint

    assert chat.state == "complaint"
    assert "We're sorry something went wrong" in chat.reply
    turn = chat.send("2")
    assert turn.escalate == menu.Escalate(channel="whatsapp", urgent=False, topic="complaint")


def test_two_replies_it_cant_use_offer_a_person():
    chat = Chat()
    chat.send("hi")
    chat.send("2")
    chat.send("what about my money")

    assert chat.state == "claims"
    assert chat.reply.startswith(content.NOT_UNDERSTOOD)
    assert chat.misses == 1

    chat.send("hello??? anyone")
    assert chat.state == "agent"
    assert chat.reply.startswith(content.NOT_HELPING)
    assert chat.misses == 0


def test_a_number_that_isnt_an_option_is_not_understood():
    chat = Chat()
    chat.send("hi")
    chat.send("9")
    assert chat.state == "main"
    assert chat.reply.startswith(content.NOT_UNDERSTOOD)


def test_a_photo_in_the_menu_is_explained():
    chat = Chat()
    chat.send("hi")
    chat.send("", media=True)
    assert chat.reply.startswith(content.MEDIA_IN_MENU)


# ----------------------------------------------------------------- Ratings ---

def test_yes_after_an_answer_asks_for_a_rating_and_then_a_comment():
    chat = Chat()
    chat.send("hi")
    chat.send("5")
    chat.send("1")   # Plan A
    chat.send("1")   # Yes, thank you

    assert chat.state == menu.RATING
    assert chat.reply == content.ASK_RATING_AFTER_ANSWER

    turn = chat.send("5")
    assert turn.feedback == menu.Feedback(topic="plans.a", rating=5)
    assert chat.state == menu.RATING_COMMENT

    turn = chat.send("Very clear, thank you")
    assert turn.feedback == menu.Feedback(topic="plans.a", comment="Very clear, thank you")
    assert chat.state == menu.IDLE
    assert chat.reply == content.THANKS_FOR_COMMENT


def test_a_low_rating_offers_a_person():
    chat = Chat()
    chat.send("hi")
    chat.send("5")
    chat.send("1")
    chat.send("1")
    chat.send("1")   # rated 1

    assert chat.state == menu.LOW_RATING
    turn = chat.send("2")
    assert turn.escalate == menu.Escalate(channel="call", urgent=False, topic="plans.a")


def test_a_low_rating_can_be_left_there():
    chat = Chat()
    chat.send("hi")
    chat.send("5")
    chat.send("1")
    chat.send("1")
    chat.send("2")
    chat.send("0")
    assert chat.state == menu.IDLE
    assert chat.reply == content.THANKS_FOR_RATING


def test_a_compliment_is_a_rating_about_a_compliment():
    chat = Chat()
    chat.send("hi")
    chat.send("7")
    chat.send("2")   # Pay a compliment

    assert chat.reply == content.ASK_RATING_COMPLIMENT
    turn = chat.send("5")
    assert turn.feedback == menu.Feedback(topic="compliment", rating=5)


def test_words_instead_of_a_rating_are_kept_as_the_comment():
    chat = Chat()
    chat.send("hi")
    chat.send("7")
    chat.send("2")
    turn = chat.send("Thank you for looking after my mother")
    assert turn.feedback == menu.Feedback(topic="compliment",
                                          comment="Thank you for looking after my mother")


def test_a_rating_after_staff_help_keeps_the_escalation():
    # services/whatsapp_line.resolve() leaves the conversation like this.
    chat = Chat()
    chat.state, chat.data, chat.last = menu.RATING, {"topic": "staff", "escalation_id": "e1"}, OPEN
    turn = chat.send("4")
    assert turn.feedback == menu.Feedback(topic="staff", rating=4)
    assert chat.data["escalation_id"] == "e1"


# ------------------------------------------------------------ Office hours ---

@pytest.mark.parametrize("moment, is_open", [
    (datetime(2026, 10, 27, 7, 59, tzinfo=SAST), False),
    (datetime(2026, 10, 27, 8, 0, tzinfo=SAST), True),
    (datetime(2026, 10, 27, 16, 59, tzinfo=SAST), True),
    (datetime(2026, 10, 27, 17, 0, tzinfo=SAST), False),
    (datetime(2026, 10, 31, 12, 59, tzinfo=SAST), True),     # Saturday morning
    (datetime(2026, 10, 31, 13, 0, tzinfo=SAST), False),     # Saturday afternoon
    (datetime(2026, 11, 1, 10, 0, tzinfo=SAST), False),      # Sunday
    (datetime(2026, 12, 16, 10, 0, tzinfo=SAST), False),     # Day of Reconciliation
])
def test_office_hours(moment, is_open):
    assert content.office_open(moment) is is_open


@pytest.mark.parametrize("moment, opens, said", [
    (datetime(2026, 10, 27, 18, 0, tzinfo=SAST), datetime(2026, 10, 28, 8, 0, tzinfo=SAST), "at 08:00 tomorrow"),
    (datetime(2026, 10, 28, 6, 0, tzinfo=SAST), datetime(2026, 10, 28, 8, 0, tzinfo=SAST), "at 08:00 today"),
    (datetime(2026, 10, 31, 14, 0, tzinfo=SAST), datetime(2026, 11, 2, 8, 0, tzinfo=SAST), "at 08:00 on Monday"),
    (datetime(2026, 12, 15, 18, 0, tzinfo=SAST), datetime(2026, 12, 17, 8, 0, tzinfo=SAST), "at 08:00 on Thursday"),
])
def test_the_next_opening_skips_sundays_and_holidays(moment, opens, said):
    assert content.next_opening(moment) == opens
    assert content.when_text(opens, moment) == said


def test_utc_times_are_read_in_south_african_time():
    from datetime import timezone
    assert content.office_open(datetime(2026, 10, 27, 6, 30, tzinfo=timezone.utc))      # 08:30 SAST
    assert not content.office_open(datetime(2026, 10, 27, 15, 30, tzinfo=timezone.utc))  # 17:30 SAST


# ----------------------------------------------------------------- Content ---

def test_every_option_leads_somewhere():
    specials = {content.ESCALATE_CALL, content.ESCALATE_WHATSAPP,
                content.ESCALATE_URGENT_CALL, content.RATE, content.BACK}
    for node in NODES.values():
        for option in node.options:
            assert option.goto in NODES or option.goto in specials, (node.id, option.goto)
        assert node.parent in NODES, node.id


def test_every_topic_is_reachable_from_the_main_menu():
    seen, queue = set(), ["main"]
    while queue:
        node = NODES[queue.pop()]
        if node.id in seen:
            continue
        seen.add(node.id)
        queue += [o.goto for o in node.options if o.goto in NODES]
    assert seen == set(NODES)


def test_every_message_fits_in_one_whatsapp():
    for node in NODES.values():
        assert len(menu.render(node, greet=node.id == "main")) <= 1600, node.id
        # The prefix a missed reply adds still fits.
        assert len(content.MEDIA_IN_MENU + "\n\n" + menu.render(node)) <= 1600, node.id


def test_the_menu_never_asks_for_an_id_number_or_bank_details():
    asking = re.compile(r"(send|give|type|reply with|enter)[^.]{0,40}"
                        r"(id number|card number|pin|bank details|account number)", re.I)
    warning = re.compile(r"\b(don't|never|not)\b", re.I)
    for node in NODES.values():
        # "Please don't send ID numbers" is the point; "send your ID number" never is.
        for sentence in re.split(r"[.\n]", node.text):
            assert not asking.search(sentence) or warning.search(sentence), node.id


def _plans_ts() -> str:
    path = REPO / "frontend" / "src" / "data" / "plans.ts"
    if not path.exists():
        pytest.skip("frontend/src/data/plans.ts is not in this checkout")
    return path.read_text(encoding="utf-8")


def test_plan_names_and_prices_match_the_website():
    source = _plans_ts()
    plans = re.findall(
        r'id: "([a-z-]+)",\s*name: \{ en: "([^"]+)".*?price: "([^"]+)"', source, re.S)
    assert len(plans) == 4
    nodes = {"plan-a": "plans.a", "plan-b": "plans.b", "plan-c": "plans.c",
             "dome-plan": "plans.dome"}
    menu_text = menu.render(NODES["plans"])
    for plan_id, name, price in plans:
        text = NODES[nodes[plan_id]].text
        assert name in text, plan_id
        assert price in text, plan_id
        assert name.split(" (")[0] in menu_text and price in menu_text, plan_id


def test_plan_c_age_prices_match_the_website():
    source = _plans_ts()
    block = source[source.index('id: "plan-c"'):source.index('id: "dome-plan"')]
    prices = set(re.findall(r'"(R\d+)"', block))
    for price in prices:
        assert price in NODES["plans.c"].text, price


def test_the_dome_plans_monthly_option_matches_the_website():
    source = _plans_ts()
    alt = re.search(r'priceAlt: \{\s*en: "or ([^"]+)"', source).group(1)
    assert alt in NODES["plans.dome"].text


def test_the_24_hour_numbers_match_the_website():
    contact = (REPO / "frontend" / "src" / "lib" / "contact.ts")
    if not contact.exists():
        pytest.skip("frontend/src/lib/contact.ts is not in this checkout")
    numbers = re.findall(r'phone\("([0-9 ]+)"', contact.read_text(encoding="utf-8"))
    for number in numbers:
        assert number in content.PHONES_24H
