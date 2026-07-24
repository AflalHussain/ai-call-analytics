"""Runtime-editable ROI inputs.

Everything here should ultimately come from SLT Mobitel. Until it does, the
`figures_are_client_supplied` flag stays False and the UI labels every derived
figure as an estimate based on our placeholder inputs — never as measured fact.
"""

from __future__ import annotations

from typing import Any

from . import db

_FIELDS = (
    "human_baseline_aht_sec",
    "agent_cost_per_hour_lkr",
    "baseline_containment_pct",
    "baseline_abandon_pct",
    "baseline_csat",
    "figures_are_client_supplied",
)


async def get_config() -> dict[str, Any]:
    async with db.pool().acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM config WHERE id = 1")
    cfg = dict(row)
    cfg.pop("id", None)
    # Times/Decimals aren't JSON-serialisable as-is.
    cfg["business_hours_start"] = cfg["business_hours_start"].strftime("%H:%M")
    cfg["business_hours_end"] = cfg["business_hours_end"].strftime("%H:%M")
    for key in ("agent_cost_per_hour_lkr", "baseline_containment_pct",
                "baseline_abandon_pct", "baseline_csat"):
        cfg[key] = float(cfg[key])
    return cfg


async def patch_config(patch: dict[str, Any]) -> dict[str, Any]:
    updates = {k: v for k, v in patch.items() if k in _FIELDS and v is not None}
    if updates:
        sets = ", ".join(f"{k} = ${i + 1}" for i, k in enumerate(updates))
        async with db.pool().acquire() as conn:
            await conn.execute(
                f"UPDATE config SET {sets} WHERE id = 1", *updates.values()
            )
    return await get_config()
