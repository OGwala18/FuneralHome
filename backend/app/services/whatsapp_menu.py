"""The WhatsApp menu's engine: given where a family is and what they wrote,
what to say next.

Pure on purpose: no database, no Twilio, no clock it reads for itself. The
caller (services/whatsapp_line.py) loads the conversation under a row lock,
calls respond(), and saves what it returns. That keeps every path through the
menu testable from a table of messages in and replies out.

The words are in services/whatsapp_content.py. This module only walks them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import whatsapp_content as content
from .whatsapp_content import NODES, Node

# A conversation left this long starts again from the greeting.
RESTART_AFTER = timedelta(minutes=30)

# Replies in a row the menu didn't understand before it offers a person.
MAX_MISSES = 2

IDLE = "idle"
RATING = "rating"
RATING_COMMENT = "rating_comment"
LOW_RATING = "low_rating"
ESCALATED = "escalated"

GREETINGS = frozenset({
    "hi", "hello", "hey", "hallo", "helo", "hie", "howzit", "good morning",
    "good afternoon", "good evening", "morning", "sawubona", "sanibonani",
    "sanibona", "yebo", "start over", "restart",
})
MENU_WORDS = frozenset({"menu", "main menu", "0", "back to menu", "home"})

_KEYCAP = re.compile("([0-9])️?⃣")


@dataclass(frozen=True)
class Escalate:
    channel: str   # 'whatsapp' or 'call'
    urgent: bool
    topic: str     # a node id


@dataclass(frozen=True)
class Feedback:
    topic: str
    rating: int | None = None
    comment: str | None = None


@dataclass
class Turn:
    replies: list[str]
    state: str
    data: dict = field(default_factory=dict)
    misses: int = 0
    escalate: Escalate | None = None
    feedback: Feedback | None = None
    # The menu step the reply belongs to, for the statistics. Never text.
    # 'rating', 'escalated' and 'not_understood' for the steps around them.
    node: str | None = None


def normalise(text: str | None) -> str:
    """Lower case, keycap emoji as digits, and the punctuation people add
    around a choice ("1.", "(2)", "3!") taken off."""
    value = _KEYCAP.sub(r"\1", (text or "").strip().lower())
    return value.strip(" .,!?)(:;-*_'\"")


def choice(text: str) -> int | None:
    value = normalise(text)
    return int(value) if value.isdigit() and len(value) <= 2 else None


# --------------------------------------------------------------- Rendering ---

def render(node: Node, *, greet: bool = False) -> str:
    if node.kind == "answer":
        return f"{node.text}\n\n{content.ANSWER_FOLLOW_UP}"

    if node.kind == "agent":
        lines = [f"{i}. {o.label}" for i, o in enumerate(content.AGENT_OPTIONS, start=1)]
        return f"{node.text}\n" + "\n".join(lines) + f"\n{content.AGENT_FOOTER}"

    lines = "\n".join(f"{i}. {o.label}" for i, o in enumerate(node.options, start=1))
    footer = content.MAIN_FOOTER if node.id == "main" else content.MENU_FOOTER
    head = f"{content.GREETING}\n\n{node.text}" if greet else node.text
    return f"{head}\n\n{lines}\n\n{footer}"


def _show(node_id: str, *, greet: bool = False, data: dict | None = None,
          prefix: str | None = None) -> Turn:
    node = NODES[node_id]
    text = render(node, greet=greet)
    return Turn(replies=[f"{prefix}\n\n{text}" if prefix else text],
                state=node.id, data=data or {}, node=node.id)


def _main(greet: bool = False) -> Turn:
    return _show("main", greet=greet)


def _agent(*, back: str, topic: str, node_id: str = "agent",
           text: str | None = None) -> Turn:
    """Offer a person. `back` is where "Go back" leads; `topic` is what they
    were asking about, which the office sees."""
    node = NODES[node_id]
    rendered = render(node)
    if text:
        rendered = text + rendered[len(node.text):]
    return Turn(replies=[rendered], state=node.id,
                data={"back": back, "topic": topic}, node=node.id)


def _escalate(channel: str, *, urgent: bool, topic: str, now: datetime) -> Turn:
    return Turn(
        replies=[content.escalated_text(channel=channel, urgent=urgent, now=now)],
        state=ESCALATED, data={"topic": topic},
        escalate=Escalate(channel=channel, urgent=urgent, topic=topic),
        node="escalated",
    )


def _goto(target: str, *, came_from: Node, now: datetime) -> Turn:
    if target == content.ESCALATE_URGENT_CALL:
        return _escalate("call", urgent=True, topic=came_from.id, now=now)
    if target == content.RATE:
        return Turn(replies=[content.ASK_RATING_COMPLIMENT], state=RATING,
                    data={"topic": "compliment"}, node="rating")
    node = NODES[target]
    if node.kind == "agent":
        # "None of these" on a topic: back to that topic, about that topic.
        back = came_from.id if target == "agent" else node.parent
        return _agent(back=back, topic=came_from.id if target == "agent" else node.id,
                      node_id=node.id)
    return _show(node.id)


def _miss(state: str, data: dict, misses: int, *, media: bool) -> Turn:
    """A reply the current step can't use. The second in a row offers a person."""
    misses += 1
    current = NODES.get(state, NODES["main"])
    if misses >= MAX_MISSES:
        turn = _agent(back=current.id, topic=current.id, text=content.NOT_HELPING)
        turn.misses = 0
        return turn
    prefix = content.MEDIA_IN_MENU if media else content.NOT_UNDERSTOOD
    turn = _show(current.id, data=data, prefix=prefix)
    turn.node = "not_understood"
    turn.misses = misses
    return turn


# ----------------------------------------------------------------- Respond ---

def respond(*, state: str, data: dict, misses: int, text: str | None,
            has_media: bool, now: datetime, idle_since: datetime | None) -> Turn:
    """The next step for a family that wrote `text` while at `state`.

    `idle_since` is the last message either way. STOP, START and a
    conversation a person is handling are the caller's job, not this one's.
    """
    words = normalise(text)
    number = choice(text or "")

    stale = idle_since is None or now - idle_since > RESTART_AFTER
    if state in (IDLE, ESCALATED) or stale or (state not in NODES and state not in
                                               (RATING, RATING_COMMENT, LOW_RATING)):
        return _main(greet=True)
    if words in GREETINGS:
        return _main(greet=True)
    if state == LOW_RATING and number == 0:
        return Turn(replies=[content.THANKS_FOR_RATING], state=IDLE, node="rating")
    if words in MENU_WORDS:
        return _main()

    if state == RATING:
        if number is not None and 1 <= number <= 5:
            topic = data.get("topic", "unknown")
            if number <= 2:
                return Turn(replies=[content.LOW_RATING], state=LOW_RATING,
                            data=dict(data),
                            feedback=Feedback(topic=topic, rating=number), node="rating")
            return Turn(replies=[content.ASK_COMMENT], state=RATING_COMMENT,
                        data=dict(data),
                        feedback=Feedback(topic=topic, rating=number), node="rating")
        if words and not has_media:
            # Words instead of a number: keep them as the comment.
            topic = data.get("topic", "unknown")
            return Turn(replies=[content.THANKS_FOR_COMMENT], state=IDLE,
                        feedback=Feedback(topic=topic, comment=text.strip()[:1000]),
                        node="rating")
        return Turn(replies=[content.ASK_RATING], state=RATING, data=data,
                    misses=misses + 1, node="rating")

    if state == RATING_COMMENT:
        topic = data.get("topic", "unknown")
        if words and not has_media:
            return Turn(replies=[content.THANKS_FOR_COMMENT], state=IDLE,
                        feedback=Feedback(topic=topic, comment=text.strip()[:1000]),
                        node="rating")
        return _main()

    if state == LOW_RATING:
        topic = data.get("topic", "unknown")
        if number == 1:
            return _escalate("whatsapp", urgent=False, topic=topic, now=now)
        if number == 2:
            return _escalate("call", urgent=False, topic=topic, now=now)
        return Turn(replies=[content.THANKS_FOR_RATING], state=IDLE, node="rating")

    node = NODES[state]

    if has_media and not words:
        return _miss(state, data, misses, media=True)

    if node.kind == "answer":
        if number == 1 or words in ("yes", "y", "yebo"):
            return Turn(replies=[content.ASK_RATING_AFTER_ANSWER], state=RATING,
                        data={"topic": node.id}, node="rating")
        if number == 2 or words in ("no", "n", "cha"):
            return _agent(back=node.parent, topic=node.id)
        return _miss(state, data, misses, media=False)

    if node.kind == "agent":
        topic = data.get("topic", node.id)
        if number == 1:
            back = data.get("back") or node.parent
            return _show(back if back in NODES else "main")
        if number == 2:
            return _escalate("whatsapp", urgent=False, topic=topic, now=now)
        if number == 3:
            return _escalate("call", urgent=False, topic=topic, now=now)
        return _miss(state, data, misses, media=False)

    # A menu.
    if number is not None and 1 <= number <= len(node.options):
        return _goto(node.options[number - 1].goto, came_from=node, now=now)
    return _miss(state, data, misses, media=False)
