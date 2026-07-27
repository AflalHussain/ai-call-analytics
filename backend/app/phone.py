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

MOBILE_PREFIXES = ["070", "071", "072", "074", "075", "076", "077", "078"]

# Intents where the fault is on a fixed line → the agent captures a landline.
FIXED_LINE_INTENTS = {"broadband_fault", "broadband_speed", "router_wifi", "peo_tv"}
# Intents about a mobile service → the agent captures a mobile number.
MOBILE_INTENTS = {"mobile_coverage", "sim_services", "roaming"}
# Follow-ups reference an existing fault, which could be either.
EITHER_INTENTS = {"complaint_followup"}


def _mobile(rng: random.Random) -> str:
    return rng.choice(MOBILE_PREFIXES) + f"{rng.randint(0, 9_999_999):07d}"


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
    if intent in FIXED_LINE_INTENTS:
        return _fixed(district, rng)
    if intent in MOBILE_INTENTS:
        return _mobile(rng)
    if intent in EITHER_INTENTS:
        return _fixed(district, rng) if rng.random() < 0.5 else _mobile(rng)
    return None
