"""What the WhatsApp menu says: every message, the menu tree, office hours.

docs/feature-3-whatsapp-line.md §5. The menu is data, kept here and nowhere
else, so changing an answer is a text edit and a pull request. The engine that
walks it is services/whatsapp_menu.py.

The seven topics are the questions a funeral home is asked most, so a family
can get an answer at any hour without waiting for a person. Each topic's last
option is "None of these", which offers to go back or to ask for a person.
Only that request reaches staff.

Plans and prices must match frontend/src/data/plans.ts, the single source of
truth for plans. tests/test_whatsapp_menu.py reads that file and fails if they
drift apart.

Facts only. Nothing here promises a payout date or a response time the office
hasn't committed to, and nothing ever asks for an ID number, a card number or
banking details: scammers copy exactly those messages.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal

# South Africa has no daylight saving, so a fixed offset is exact, and needs no
# time zone database (Windows has none without the tzdata package).
SAST = timezone(timedelta(hours=2), "SAST")

PHONES_24H = "079 751 0648 or 082 954 9241"
OFFICE_ADDRESS = "Edendale Main Road, Kwadaya, Pietermaritzburg 3201"
MAP_LINK = "https://www.google.com/maps/search/?api=1&query=Edendale+Main+Road+Kwadaya+Pietermaritzburg"
WEBSITE_JOIN = "https://induduzo.co.za/register"
EMAIL = "Info@induduzo.co.za"
HOURS_TEXT = "Mon–Fri 8am–5pm and Sat 8am–1pm"

# --------------------------------------------------------------------------
# Office hours. Decided by the owner on 21 Oct 2026.
# --------------------------------------------------------------------------

# Weekday (Monday is 0) -> (opens, closes). Sunday is closed.
OPENING_HOURS: dict[int, tuple[time, time]] = {
    0: (time(8), time(17)),
    1: (time(8), time(17)),
    2: (time(8), time(17)),
    3: (time(8), time(17)),
    4: (time(8), time(17)),
    5: (time(8), time(13)),
}

# Public holidays, when the office is closed. Update every year. A holiday on
# a Sunday moves to the Monday (Public Holidays Act), so the Monday is listed.
PUBLIC_HOLIDAYS: frozenset[date] = frozenset({
    # 2026
    date(2026, 1, 1), date(2026, 3, 21), date(2026, 4, 3), date(2026, 4, 6),
    date(2026, 4, 27), date(2026, 5, 1), date(2026, 6, 16), date(2026, 8, 10),
    date(2026, 9, 24), date(2026, 12, 16), date(2026, 12, 25), date(2026, 12, 26),
    # 2027
    date(2027, 1, 1), date(2027, 3, 22), date(2027, 3, 26), date(2027, 3, 29),
    date(2027, 4, 27), date(2027, 5, 1), date(2027, 6, 16), date(2027, 8, 9),
    date(2027, 9, 24), date(2027, 12, 16), date(2027, 12, 25), date(2027, 12, 27),
})


def _hours_on(day: date) -> tuple[time, time] | None:
    if day in PUBLIC_HOLIDAYS:
        return None
    return OPENING_HOURS.get(day.weekday())


def office_open(now: datetime) -> bool:
    local = now.astimezone(SAST)
    hours = _hours_on(local.date())
    return hours is not None and hours[0] <= local.time() < hours[1]


def next_opening(now: datetime) -> datetime:
    """When the office next opens, after `now`. Within the hour if it's open."""
    local = now.astimezone(SAST)
    for ahead in range(0, 14):
        day = local.date() + timedelta(days=ahead)
        hours = _hours_on(day)
        if hours is None:
            continue
        opens = datetime.combine(day, hours[0], SAST)
        if opens > local:
            return opens
    raise RuntimeError("No opening hours in the next two weeks; check OPENING_HOURS.")


def when_text(moment: datetime, now: datetime) -> str:
    """'at 08:00 tomorrow' or 'at 08:00 on Monday', for a promise to a family."""
    local, today = moment.astimezone(SAST), now.astimezone(SAST).date()
    clock = local.strftime("%H:%M")
    if local.date() == today:
        return f"at {clock} today"
    if local.date() == today + timedelta(days=1):
        return f"at {clock} tomorrow"
    return f"at {clock} on {local.strftime('%A')}"


# --------------------------------------------------------------------------
# The menu tree.
# --------------------------------------------------------------------------

# Where an option leads: another node, or one of these.
ESCALATE_CALL = "escalate:call"
ESCALATE_WHATSAPP = "escalate:whatsapp"
ESCALATE_URGENT_CALL = "escalate:call:urgent"
RATE = "rate"          # ask for a 1-5 rating about the topic
BACK = "back"          # the menu the family came from


@dataclass(frozen=True)
class Option:
    label: str
    goto: str


@dataclass(frozen=True)
class Node:
    id: str
    kind: Literal["menu", "answer", "agent"]
    # Short, for the office email and the portal: "Claims and payouts".
    title: str
    text: str
    options: tuple[Option, ...] = ()
    # Where "None of these", "No" and "Go back" return to.
    parent: str = "main"


# The last option on every topic.
NONE_OF_THESE = Option("None of these", "agent")


def _plan_text(name: str, price: str, who: str, includes: list[str]) -> str:
    return (
        f"*{name}* – {price}\n"
        f"{who}\n\n"
        "Includes: " + ", ".join(includes) + ".\n\n"
        "Every plan: R50 joining fee, a 3-month waiting period, and a guaranteed "
        "payout of R1,000 for someone under 21 or R2,000 for 21 and over.\n\n"
        f"Join online in a few minutes: {WEBSITE_JOIN}"
    )


GREETING = "Sawubona 🙏 Welcome to Induduzo Funeral Home."

NODES: dict[str, Node] = {}


def _add(*nodes: Node) -> None:
    for node in nodes:
        if node.id in NODES:
            raise ValueError(f"Duplicate menu node {node.id}")
        NODES[node.id] = node


_add(
    Node(
        id="main", kind="menu", title="Main menu",
        text="How can we help you today?",
        options=(
            Option("Someone has passed away", "death"),
            Option("Claims and payouts", "claims"),
            Option("Paying my premium", "pay"),
            Option("My policy and family members", "policy"),
            Option("Plans, prices and joining", "plans"),
            Option("Funeral arrangements", "arrange"),
            Option("Complaints, compliments and contact", "contact"),
        ),
    ),

    # 1. Someone has passed away. Help comes first, before any menu.
    Node(
        id="death", kind="menu", title="Someone has passed away",
        text=(
            "We are so sorry for your loss. 🙏\n\n"
            f"Our 24-hour lines are always open: *{PHONES_24H}*.\n\n"
            "If they passed away at home, a doctor or the police must first "
            "confirm the death. Then call us and we will collect them, day or night."
        ),
        options=(
            Option("Please phone me now", ESCALATE_URGENT_CALL),
            Option("What happens next?", "death.next"),
            Option("Documents for the claim", "claims.documents"),
            NONE_OF_THESE,
        ),
    ),
    Node(
        id="death.next", kind="answer", title="What happens after a death", parent="death",
        text=(
            "What happens next:\n"
            "1. We collect your loved one and keep them in our mortuary (amakhaza).\n"
            "2. The doctor or police give the family the notice of death. Take it "
            "to Home Affairs to register the death and get the death certificate.\n"
            "3. Come to our office, and a family liaison plans the funeral with you: "
            "the date, the venue and everything your plan includes.\n\n"
            "Please don't send ID numbers or documents on WhatsApp."
        ),
    ),

    # 2. Claims and payouts.
    Node(
        id="claims", kind="menu", title="Claims and payouts",
        text="Claims and payouts. Choose a question:",
        options=(
            Option("Documents I need to claim", "claims.documents"),
            Option("How the payout works", "claims.payout"),
            Option("My claim is taking long", "claims.delayed"),
            Option("Claiming in the waiting period", "claims.waiting"),
            NONE_OF_THESE,
        ),
    ),
    Node(
        id="claims.documents", kind="answer", title="Documents to claim", parent="claims",
        text=(
            "To claim, bring these to our office:\n"
            "• The death certificate from Home Affairs\n"
            "• A certified copy of the ID of the person who passed away\n"
            "• A certified copy of the main member's ID\n"
            "• Your policy number, if you have it\n\n"
            "Please bring them in person. Never send ID documents or bank details "
            "on WhatsApp: we will never ask for them here."
        ),
    ),
    Node(
        id="claims.payout", kind="answer", title="How the payout works", parent="claims",
        text=(
            "Your plan pays for the funeral itself: we provide everything it "
            "includes, from collection to the burial.\n\n"
            "Every plan also has a guaranteed cash payout: R1,000 for someone under "
            "21, or R2,000 for 21 and over. It is paid once the claim documents are "
            "complete. Your family liaison will tell you when."
        ),
    ),
    Node(
        id="claims.delayed", kind="answer", title="A claim taking long", parent="claims",
        text=(
            "We're sorry for the wait. A claim is usually held up by a missing "
            "document, or a premium that wasn't paid.\n\n"
            "Have your policy number ready, and choose 2 below: a person will check "
            "your claim and tell you exactly what's outstanding."
        ),
    ),
    Node(
        id="claims.waiting", kind="answer", title="The waiting period", parent="claims",
        text=(
            "Every plan has a 3-month waiting period from the day you join. A claim "
            "in that time is checked against your policy's start date and what your "
            "plan allows.\n\n"
            "Your family liaison can check the dates on your policy: choose 2 below."
        ),
    ),

    # 3. Paying my premium.
    Node(
        id="pay", kind="menu", title="Paying my premium",
        text="Paying your premium. Choose a question:",
        options=(
            Option("Ways to pay", "pay.ways"),
            Option("I missed a payment", "pay.missed"),
            Option("Wrong amount or a double deduction", "pay.wrong"),
            Option("Changing or cancelling my debit order", "pay.change"),
            NONE_OF_THESE,
        ),
    ),
    Node(
        id="pay.ways", kind="answer", title="Ways to pay", parent="pay",
        text=(
            "You can pay by debit order, stop order, EFT, Easypay or Pay@, or in "
            "cash or by card at our office.\n\n"
            "We never send banking details on WhatsApp, and we will never ask for "
            "your card number or PIN. For our account details, phone the office on "
            "079 751 0648."
        ),
    ),
    Node(
        id="pay.missed", kind="answer", title="A missed payment", parent="pay",
        text=(
            "Please pay the missed premium as soon as you can, at the office or the "
            "way you usually pay.\n\n"
            "A policy that falls behind can lapse, and a lapsed policy can't be "
            "claimed on. If you've missed more than one, choose 2 below and we'll "
            "help you get back on track."
        ),
    ),
    Node(
        id="pay.wrong", kind="answer", title="A wrong deduction", parent="pay",
        text=(
            "We're sorry about that. Please check your bank statement for the date "
            "and the amount, then choose 2 below. A person will check it against your "
            "policy and put any mistake right."
        ),
    ),
    Node(
        id="pay.change", kind="answer", title="Changing a debit order", parent="pay",
        text=(
            "To change or cancel a debit order, come to the office with your ID, or "
            "choose 2 below to ask a person to phone you.\n\n"
            "To protect you from fraud, bank details are never changed over WhatsApp."
        ),
    ),

    # 4. My policy and family members.
    Node(
        id="policy", kind="menu", title="My policy and family members",
        text="Your policy. Choose a question:",
        options=(
            Option("Adding or removing family members", "policy.members"),
            Option("Changing my beneficiary or contact details", "policy.details"),
            Option("What my plan covers", "plans"),
            Option("A copy of my policy", "policy.copy"),
            NONE_OF_THESE,
        ),
    ),
    Node(
        id="policy.members", kind="answer", title="Adding family members", parent="policy",
        text=(
            "You can cover up to 15 people on Plan A, Plan B and the Dome Plan. "
            "Plan C's couple option covers your children under 21.\n\n"
            "To add or remove someone, bring their ID or birth certificate to the "
            "office, or choose 2 below to ask a person to phone you."
        ),
    ),
    Node(
        id="policy.details", kind="answer", title="Changing policy details", parent="policy",
        text=(
            "For your safety, beneficiaries and contact details are changed by our "
            "staff, not over WhatsApp. Come to the office with your ID, or choose 2 "
            "below to ask a person to phone you."
        ),
    ),
    Node(
        id="policy.copy", kind="answer", title="A copy of my policy", parent="policy",
        text=(
            "Ask at the office for a printed copy of your policy, or choose 2 below "
            "and we'll arrange one for you."
        ),
    ),

    # 5. Plans, prices and joining.
    Node(
        id="plans", kind="menu", title="Plans, prices and joining",
        text="Our plans. Choose one to see what it includes:",
        options=(
            Option("Plan A (Urban) – R350 p/m", "plans.a"),
            Option("Plan B (Emakhaya) – R250 p/m", "plans.b"),
            Option("Plan C (Singles/Couples) – from R50 p/m", "plans.c"),
            Option("Dome Plan – R400 once-off", "plans.dome"),
            Option("How to join", "plans.join"),
            NONE_OF_THESE,
        ),
    ),
    Node(
        id="plans.a", kind="answer", title="Plan A (Urban)", parent="plans",
        text=_plan_text(
            "Plan A (Urban)", "R350 p/m", "Up to 15 family members. No age limits.",
            ["casket", "cross", "mortuary fridge", "tent (2 poles) and 50 chairs",
             "A3 photo frame", "50 programmes", "gown", "hearse and family car",
             "doctor fees", "a grave at Ethembeni Cemetery", "cemetery equipment"],
        ),
    ),
    Node(
        id="plans.b", kind="answer", title="Plan B (Emakhaya)", parent="plans",
        text=_plan_text(
            "Plan B (Emakhaya)", "R250 p/m",
            "Up to 15 family members. No age limits. For a funeral at the family home.",
            ["removal", "mortuary storage", "doctor fees", "casket", "cross", "gown",
             "hearse and family car", "tent (2 poles) and 50 chairs",
             "A3 photo frame", "50 programmes"],
        ),
    ),
    Node(
        id="plans.c", kind="answer", title="Plan C (Singles/Couples)", parent="plans",
        text=_plan_text(
            "Plan C (Singles/Couples)", "from R50 p/m",
            "One person aged 21–85, or a couple aged 21–59, priced by age. The couple "
            "option covers your children under 21.\n"
            "Single, flat lid: R50 (21–45), R60 (46–59), R80 (60–75), R120 (76–85).\n"
            "Single, casket: R150, R180, R200, R250 for the same ages.\n"
            "Couple, flat lid: R100 (21–45), R200 (46–59).",
            ["removal", "mortuary storage", "doctor fees",
             "flat lid or casket (by age)", "cross", "gown", "hearse",
             "tent (2 poles) and 50 chairs"],
        ),
    ),
    Node(
        id="plans.dome", kind="answer", title="Dome Plan", parent="plans",
        text=_plan_text(
            "Dome Plan", "R400 once-off, or R300 once-off + R50 p/m",
            "The main member and 14 others, 15 people in total.",
            ["2 family cars", "hearse", "casket", "cross", "mortuary fridge",
             "tent (2 poles)", "100 programmes", "A3 photo frame", "gown",
             "doctor fees", "a grave at Ethembeni Cemetery", "cemetery equipment"],
        ),
    ),
    Node(
        id="plans.join", kind="answer", title="How to join", parent="plans",
        text=(
            f"Join online in a few minutes: {WEBSITE_JOIN}\n\n"
            "Or visit our office with your ID. A family liaison will phone you "
            "within one working day to finish your application."
        ),
    ),

    # 6. Funeral arrangements.
    Node(
        id="arrange", kind="menu", title="Funeral arrangements",
        text="Funeral arrangements. Choose a question:",
        options=(
            Option("Collecting my loved one", "arrange.collect"),
            Option("Booking the funeral date", "arrange.date"),
            Option("Tent, chairs, hearse and programmes", "arrange.items"),
            Option("A funeral at the family home (emakhaya)", "arrange.home"),
            NONE_OF_THESE,
        ),
    ),
    Node(
        id="arrange.collect", kind="answer", title="Collecting the deceased", parent="arrange",
        text=(
            "We collect day or night, from home or from hospital. Call our 24-hour "
            f"lines: *{PHONES_24H}*.\n\n"
            "Your loved one stays in our mortuary (amakhaza) until the funeral."
        ),
    ),
    Node(
        id="arrange.date", kind="answer", title="Booking the funeral date", parent="arrange",
        text=(
            "The funeral date is booked with your family liaison at our office, once "
            "the death is registered at Home Affairs. Saturdays fill up first, so "
            "please come in as early as you can."
        ),
    ),
    Node(
        id="arrange.items", kind="answer", title="Tent, chairs and hearse", parent="arrange",
        text=(
            "What's included depends on your plan. Plan A and Plan B, for example, "
            "include a tent (2 poles) and 50 chairs, a hearse and a family car, and "
            "50 programmes. The Dome Plan has 2 family cars and 100 programmes.\n\n"
            "Your family liaison confirms the list and the delivery time with you. "
            "Extras can be added at a cost."
        ),
    ),
    Node(
        id="arrange.home", kind="answer", title="A funeral at home", parent="arrange",
        text=(
            "Plan B (Emakhaya) is made for a funeral at the family home: it covers "
            "everything from collecting your loved one to the service at home.\n\n"
            "Tell your family liaison where the home is, so the hearse, tent and "
            "chairs can be planned."
        ),
    ),

    # 7. Complaints, compliments and contact.
    Node(
        id="contact", kind="menu", title="Complaints, compliments and contact",
        text="Choose one:",
        options=(
            Option("Make a complaint", "complaint"),
            Option("Pay a compliment", RATE),
            Option("Our office and hours", "contact.office"),
            Option("Phone numbers and email", "contact.numbers"),
            NONE_OF_THESE,
        ),
    ),
    Node(
        id="contact.office", kind="answer", title="Office and hours", parent="contact",
        text=(
            f"Our office: {OFFICE_ADDRESS}\n"
            f"Map: {MAP_LINK}\n\n"
            f"Open {HOURS_TEXT}. Closed on Sundays and public holidays.\n\n"
            f"If someone has passed away, call any time: *{PHONES_24H}*."
        ),
    ),
    Node(
        id="contact.numbers", kind="answer", title="Phone numbers", parent="contact",
        text=(
            f"Phone, 24 hours: *{PHONES_24H}*\n"
            f"Email: {EMAIL}\n"
            "WhatsApp: this number.\n\n"
            f"The office is open {HOURS_TEXT}."
        ),
    ),

    # Asking for a person. Reached from "None of these", "No, I need more
    # help", a complaint, or two replies the menu didn't understand.
    Node(
        id="agent", kind="agent", title="Asked for a person",
        text="Sorry we couldn't answer that here. You can:",
    ),
    Node(
        id="complaint", kind="agent", title="Complaint", parent="contact",
        text=(
            "We're sorry something went wrong. A senior member of our team will look "
            "into it personally. How would you like us to contact you?"
        ),
    ),
)

# The options on every agent node, in this order.
AGENT_OPTIONS: tuple[Option, ...] = (
    Option("Go back", BACK),
    Option("A person replies to me here on WhatsApp", ESCALATE_WHATSAPP),
    Option("A person phones me", ESCALATE_CALL),
)

# --------------------------------------------------------------------------
# Everything else the line says.
# --------------------------------------------------------------------------

MENU_FOOTER = "Reply with a number, or 0 for the main menu."
MAIN_FOOTER = "Reply with a number."

ANSWER_FOLLOW_UP = (
    "Did this answer your question?\n"
    "1. Yes, thank you\n"
    "2. No, I need more help\n"
    "0. Main menu"
)

AGENT_FOOTER = f"0. Main menu\n\nOur office is open {HOURS_TEXT}."

NOT_UNDERSTOOD = "Sorry, I didn't understand that. Please reply with a number from the list."
NOT_HELPING = "It looks like the menu isn't helping. You can:"
MEDIA_IN_MENU = (
    "Thank you. We can't open photos or documents in this menu. "
    "Please reply with a number from the list."
)
ID_NUMBER_REMOVED = (
    "Please don't send ID numbers or card numbers on WhatsApp. We have removed it "
    "from our records. Our staff will confirm details like these with you on a call."
)

ASK_RATING = "How would you rate our help? Reply 1 (poor) to 5 (excellent), or 0 for the main menu."
ASK_RATING_AFTER_ANSWER = "Glad we could help. 🙏 " + ASK_RATING
ASK_RATING_COMPLIMENT = (
    "Thank you! 🙏 Kind words mean a lot to our team. How would you rate us? "
    "Reply 1 (poor) to 5 (excellent)."
)
ASK_RATING_AFTER_STAFF = (
    "Thank you for talking to Induduzo Funeral Home. How would you rate our help "
    "today? Reply 1 (poor) to 5 (excellent)."
)
ASK_COMMENT = (
    "Thank you. If you'd like to add a few words, type them now. "
    "Or reply 0 for the main menu."
)
LOW_RATING = (
    "We're sorry we didn't help enough. Would you like a person to contact you?\n"
    "1. A person replies to me here on WhatsApp\n"
    "2. A person phones me\n"
    "0. No, thank you"
)
THANKS_FOR_COMMENT = "Thank you, we have passed that on to the team. 🙏 Reply MENU any time."
THANKS_FOR_RATING = "Thank you for your feedback. 🙏 Reply MENU any time."

STOPPED = (
    "You won't get automatic messages from Induduzo any more. Reply START to turn "
    f"them back on. For help, call {PHONES_24H}."
)

# While a person is handling the conversation, the menu stays quiet. If the
# family writes again before anyone has replied, this goes out at most once an
# hour, so they know they haven't been forgotten.
HOLDING = (
    "Thank you, we have your message. A member of our team will get back to you "
    "{when}. Reply MENU to go back to the menu."
)


def escalated_text(*, channel: str, urgent: bool, now: datetime) -> str:
    """What the family is told once their request reaches staff."""
    if urgent:
        if office_open(now):
            return (
                "We've asked our team to phone you now. If you need us sooner, call "
                f"*{PHONES_24H}*, day or night."
            )
        return (
            f"Our office is closed, but our 24-hour lines are open: please call "
            f"*{PHONES_24H}* now. We have also asked the office to phone you when it "
            f"opens {when_text(next_opening(now), now)}."
        )

    how = ("reply to you here on WhatsApp" if channel == "whatsapp"
           else "phone you on this number")
    if office_open(now):
        lead = f"Thank you. We've asked a member of our team to {how} as soon as possible."
    else:
        lead = (
            f"Thank you. The office is closed now, so a member of our team will {how} "
            f"when it opens {when_text(next_opening(now), now)}."
        )
    note = (" If you'd like, type a short note about what you need. Please don't "
            "send ID numbers or bank details.")
    urgent_help = f"\n\nIf someone has passed away, call {PHONES_24H} any time."
    return lead + note + ("" if office_open(now) else urgent_help)


def holding_text(now: datetime) -> str:
    when = "as soon as possible" if office_open(now) else (
        f"when the office opens {when_text(next_opening(now), now)}")
    return HOLDING.format(when=when)
