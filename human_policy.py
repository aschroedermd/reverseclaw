"""Boundary and policy loading for human API endpoints."""

import json
import os
from typing import Any


BOUNDARIES_FILE_DEFAULT = "human-boundaries.json"


def default_boundaries() -> dict[str, Any]:
    return {
        "version": 1,
        "blocked_tags": [],
        "max_estimated_cost_usd": 0.0,
        "allow_purchases": False,
        "allow_sensitive_data": False,
        "allow_external_contact": True,
        "allow_physical_presence": True,
        "max_estimated_effort_minutes": 240,
        "notes": "",
    }


def load_boundaries(path: str = BOUNDARIES_FILE_DEFAULT) -> dict[str, Any]:
    boundaries = default_boundaries()
    if not os.path.exists(path):
        return boundaries

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data.get("blocked_tags"), list):
        boundaries["blocked_tags"] = [
            str(tag).strip().lower()
            for tag in data["blocked_tags"]
            if str(tag).strip()
        ]

    for key in (
        "allow_purchases",
        "allow_sensitive_data",
        "allow_external_contact",
        "allow_physical_presence",
    ):
        if key in data:
            boundaries[key] = bool(data[key])

    for key in ("max_estimated_cost_usd", "max_estimated_effort_minutes"):
        if key in data and data[key] is not None:
            try:
                boundaries[key] = float(data[key]) if key.endswith("_usd") else int(data[key])
            except (TypeError, ValueError):
                pass

    if "notes" in data and data["notes"] is not None:
        boundaries["notes"] = str(data["notes"]).strip()

    return boundaries


def summarize_boundaries(boundaries: dict[str, Any]) -> str:
    blocked = boundaries.get("blocked_tags") or []
    parts = [
        f"Sensitive data: {'no' if not boundaries.get('allow_sensitive_data') else 'yes'}",
        f"External contact: {'yes' if boundaries.get('allow_external_contact') else 'no'}",
        f"Physical presence: {'yes' if boundaries.get('allow_physical_presence') else 'no'}",
        f"Purchases: {'yes' if boundaries.get('allow_purchases') else 'no'}",
        f"Max cost: ${boundaries.get('max_estimated_cost_usd', 0):.2f}",
        f"Max effort: {boundaries.get('max_estimated_effort_minutes', 0)} min",
    ]
    if blocked:
        parts.append("Blocked tags: " + ", ".join(blocked))
    if boundaries.get("notes"):
        parts.append("Notes: " + boundaries["notes"])
    return " | ".join(parts)


def validate_task_against_boundaries(task_req, boundaries: dict[str, Any]) -> list[str]:
    violations = []
    blocked_tags = set(boundaries.get("blocked_tags") or [])
    task_tags = {str(tag).strip().lower() for tag in getattr(task_req, "task_tags", []) if str(tag).strip()}
    overlapping = sorted(blocked_tags.intersection(task_tags))
    if overlapping:
        violations.append(f"task_tags include blocked categories: {', '.join(overlapping)}")

    estimated_cost = getattr(task_req, "estimated_cost_usd", None)
    if estimated_cost is not None:
        if float(estimated_cost) > float(boundaries.get("max_estimated_cost_usd", 0.0)):
            violations.append(
                f"estimated_cost_usd ({estimated_cost}) exceeds max_estimated_cost_usd "
                f"({boundaries.get('max_estimated_cost_usd')})"
            )
        if float(estimated_cost) > 0 and not boundaries.get("allow_purchases", False):
            if getattr(task_req, "requires_purchase", False):
                violations.append("task requires a purchase but purchases are not allowed")

    if getattr(task_req, "requires_sensitive_data", False) and not boundaries.get("allow_sensitive_data", False):
        violations.append("task requires sensitive data but sensitive data handling is not allowed")

    if getattr(task_req, "requires_external_contact", False) and not boundaries.get("allow_external_contact", True):
        violations.append("task requires contacting other people but external contact is not allowed")

    if getattr(task_req, "requires_physical_presence", False) and not boundaries.get("allow_physical_presence", True):
        violations.append("task requires physical presence but physical tasks are not allowed")

    estimated_effort = getattr(task_req, "estimated_effort_minutes", None)
    max_effort = boundaries.get("max_estimated_effort_minutes")
    if estimated_effort is not None and max_effort is not None:
        if int(estimated_effort) > int(max_effort):
            violations.append(
                f"estimated_effort_minutes ({estimated_effort}) exceeds max_estimated_effort_minutes ({max_effort})"
            )

    return violations
