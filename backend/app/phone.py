"""Sri Lankan phone-number generation for the *affected service line*.

The AI agent asks the caller to key in the landline or mobile number of the
affected service. This module produces realistic synthetic numbers for the seed
and demo scripts — a fixed line (district area code) for broadband/PEO faults, a
mobile (07x) for coverage/SIM/roaming.

The stored value is the full number; the dashboard masks it at render
(prefix + last 4). Nothing here masks — generation only.
"""

from __future__ import annotations

import random

# District → fixed-line area code (with leading 0). Sri Lanka Telecom regions.
AREA_CODE: dict[str, str] = {
    "Colombo": "011", "Gampaha": "033", "Kalutara": "034", "Kandy": "081",
    "Matale": "066", "Nuwara Eliya": "052", "Galle": "091", "Matara": "041",
    "Hambantota": "047", "Jaffna": "021", "Kilinochchi": "021", "Mannar": "023",
    "Vavuniya": "024", "Mullaitivu": "024", "Batticaloa": "065", "Ampara": "063",
    "Trincomalee": "026", "Kurunegala": "037", "Puttalam": "032",
    "Anuradhapura": "025", "Polonnaruwa": "027", "Badulla": "055",
    "Monaragala": "055", "Ratnapura": "045", "Kegalle": "035",
}
DEFAULT_AREA_CODE = "011"

# Valid Sri Lankan mobile prefixes by operator. 073 and 079 are unassigned.
SLT_MOBILE_PREFIXES = ["070", "071"]                        # Mobitel — SLT's own mobile
OTHER_MOBILE_PREFIXES = ["072", "074", "075", "076", "077", "078"]  # Dialog/Hutch/Airtel
MOBILE_PREFIXES = SLT_MOBILE_PREFIXES + OTHER_MOBILE_PREFIXES        # any operator

# Intents where the fault is on a fixed line → the agent captures a landline.
FIXED_LINE_INTENTS = {"broadband_fault", "broadband_speed", "router_wifi", "peo_tv"}
# Intents about a mobile service → the agent captures a mobile number.
MOBILE_INTENTS = {"mobile_coverage", "sim_services", "roaming"}
# Follow-ups reference an existing fault, which could be either.
EITHER_INTENTS = {"complaint_followup"}


def _mobile(rng: random.Random) -> str:
    """Any-operator mobile — for the caller's own CLI / callback number."""
    return rng.choice(MOBILE_PREFIXES) + f"{rng.randint(0, 9_999_999):07d}"


def _slt_mobile(rng: random.Random) -> str:
    """A Mobitel (SLT) mobile — for an *affected service line*, which must be
    an SLT number, never a competitor's (Dialog/Hutch/Airtel)."""
    return rng.choice(SLT_MOBILE_PREFIXES) + f"{rng.randint(0, 9_999_999):07d}"


def random_mobile(rng: random.Random) -> str:
    """A random mobile number — for demo scripts with no stable caller pool."""
    return _mobile(rng)


def caller_number_from_id(caller_id: int) -> str:
    """Deterministic incoming number (CLI) for a synthetic caller.

    Derived from the caller id so a repeat caller shows the *same* number across
    all their calls — matching how `customer_ref` is stable per `caller_hash`.
    The caller may be on any operator (they can phone in from any handset), but
    the prefix must be a real one — pick deterministically from the valid set.
    """
    prefix = MOBILE_PREFIXES[caller_id % len(MOBILE_PREFIXES)]
    return prefix + f"{caller_id % 10_000_000:07d}"


def _fixed(district: str | None, rng: random.Random) -> str:
    area = AREA_CODE.get(district or "", DEFAULT_AREA_CODE)
    # SLT fixed subscriber numbers commonly start 2/4/5 after the area code.
    return area + rng.choice("245") + f"{rng.randint(0, 999_999):06d}"


def affected_number(intent: str, district: str | None, rng: random.Random) -> str | None:
    """The affected line for this call, or None when the call isn't line-specific.

    Account-level intents (billing, reload, data, package changes, general info)
    return None — the agent has no single line to ask about, so the column reads
    "—" for them, which is the honest picture.
    """
    # Affected mobile lines are SLT services, so they use Mobitel prefixes only —
    # a customer can't report a fault on a Dialog/Hutch/Airtel number to SLT.
    if intent in FIXED_LINE_INTENTS:
        return _fixed(district, rng)
    if intent in MOBILE_INTENTS:
        return _slt_mobile(rng)
    if intent in EITHER_INTENTS:
        return _fixed(district, rng) if rng.random() < 0.5 else _slt_mobile(rng)
    return None


# Probability that a callback-eligible call actually captured a callback number.
_CALLBACK_RATE = 0.45


def callback_number(
    handled_by: str, resolved: bool, churn_risk: bool, rng: random.Random
) -> str | None:
    """The number the caller agreed to be called back on, or None.

    A callback is only offered when the call couldn't be closed live or the
    caller is a retention risk — escalated, unresolved, or churn-flagged. Even
    then only some callers accept, so we gate on a probability. Callbacks are
    given as mobiles. Resolved account-level calls never carry one.
    """
    eligible = handled_by == "escalated" or not resolved or churn_risk
    if eligible and rng.random() < _CALLBACK_RATE:
        return _mobile(rng)
    return None
