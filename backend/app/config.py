"""Operational settings — read only.

Business hours drive the "answered outside office hours" KPI; timezone anchors
the daily and heatmap aggregates to Sri Lanka local time. There are no
editable ROI inputs any more (the cost/baseline settings were removed with the
"Agent cost avoided" tile and the contact-centre comparison), so this is a
read-only surface.
"""

from __future__ import annotations

from typing import Any

from . import db


async def get_config() -> dict[str, Any]:
    async with db.pool().acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM config WHERE id = 1")
    cfg = dict(row)
    cfg.pop("id", None)
    cfg["business_hours_start"] = cfg["business_hours_start"].strftime("%H:%M")
    cfg["business_hours_end"] = cfg["business_hours_end"].strftime("%H:%M")
    return cfg
