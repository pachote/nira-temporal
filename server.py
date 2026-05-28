"""
NIRA Temporal Agent MCP
Claude sets its own reminders, schedules future actions, time-aware context injection.
"""
import json
import os
import time
import uuid
import threading
from pathlib import Path
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "NIRA Temporal Agent",
    instructions=(
        "Time-aware scheduling. Set reminders, schedule future checks, create recurring tasks. "
        "schedule_remind creates a reminder. schedule_list shows pending. "
        "schedule_check polls for due items. schedule_cron creates recurring jobs."
    )
)

SCHEDULE_FILE = Path(os.environ.get("NIRA_DATA_DIR",
    str(Path.home() / "nira_temporal"))) / "nira_schedule.json"

_lock = threading.Lock()


def _load() -> list[dict]:
    try:
        if SCHEDULE_FILE.exists():
            return json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def _save(items: list[dict]) -> None:
    SCHEDULE_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")


@mcp.tool()
def schedule_remind(
    message: str,
    delay_minutes: float = 0,
    at_time: str = "",
    repeat: str = "",
    tags: list[str] = None,
) -> dict:
    """
    Schedule a reminder or future action note.
    delay_minutes: fire after this many minutes from now.
    at_time: specific time like '14:30' or '2026-05-27 09:00'.
    repeat: '', 'daily', 'hourly', 'weekly'.
    tags: categorization tags for filtering.
    Returns: {schedule_id, fires_at}
    """
    import datetime

    now = time.time()
    if at_time:
        try:
            for fmt in ("%Y-%m-%d %H:%M", "%H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.datetime.strptime(at_time, fmt)
                    if fmt == "%H:%M":
                        today = datetime.datetime.now()
                        dt = dt.replace(year=today.year, month=today.month, day=today.day)
                    fires_at = dt.timestamp()
                    break
                except ValueError:
                    continue
            else:
                fires_at = now + delay_minutes * 60
        except Exception:
            fires_at = now + delay_minutes * 60
    else:
        fires_at = now + delay_minutes * 60

    item = {
        "id": str(uuid.uuid4())[:8],
        "message": message,
        "fires_at": fires_at,
        "created_at": now,
        "repeat": repeat,
        "tags": tags or [],
        "fired": False,
        "fire_count": 0,
    }

    with _lock:
        items = _load()
        items.append(item)
        _save(items)

    fires_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(fires_at))
    return {"schedule_id": item["id"], "message": message, "fires_at": fires_str}


@mcp.tool()
def schedule_check(mark_fired: bool = True) -> dict:
    """
    Check for any reminders or scheduled items that are now due.
    Call this at the start of sessions to catch anything that fired while you were away.
    Returns: {due: [{id, message, fired_at, tags}], pending_count}
    """
    now = time.time()
    due = []

    with _lock:
        items = _load()
        updated = []
        for item in items:
            if not item["fired"] and item["fires_at"] <= now:
                due.append({
                    "id": item["id"],
                    "message": item["message"],
                    "fired_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(item["fires_at"])),
                    "tags": item.get("tags", []),
                    "overdue_s": int(now - item["fires_at"]),
                })
                item["fire_count"] = item.get("fire_count", 0) + 1

                if item.get("repeat") == "daily":
                    item["fires_at"] += 86400
                    item["fired"] = False
                elif item.get("repeat") == "hourly":
                    item["fires_at"] += 3600
                    item["fired"] = False
                elif item.get("repeat") == "weekly":
                    item["fires_at"] += 86400 * 7
                    item["fired"] = False
                elif mark_fired:
                    item["fired"] = True

            if not (item["fired"] and not item.get("repeat")):
                updated.append(item)

        _save(updated)
        pending = sum(1 for i in updated if not i["fired"])

    return {"due": due, "pending_count": pending, "checked_at": time.strftime("%Y-%m-%d %H:%M:%S")}


@mcp.tool()
def schedule_list(include_fired: bool = False, tag: str = "") -> dict:
    """
    List all scheduled items.
    Returns: {items: [{id, message, fires_at, repeat, tags, fired}]}
    """
    items = _load()
    result = []
    for item in items:
        if not include_fired and item.get("fired") and not item.get("repeat"):
            continue
        if tag and tag not in item.get("tags", []):
            continue
        fires_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(item["fires_at"]))
        delta = item["fires_at"] - time.time()
        result.append({
            "id": item["id"],
            "message": item["message"],
            "fires_at": fires_str,
            "in_minutes": round(delta / 60, 1) if delta > 0 else "OVERDUE",
            "repeat": item.get("repeat", ""),
            "tags": item.get("tags", []),
            "fired": item.get("fired", False),
        })
    result.sort(key=lambda x: x["fires_at"])
    return {"items": result, "total": len(result)}


@mcp.tool()
def schedule_cancel(schedule_id: str) -> dict:
    """Cancel a scheduled item by ID."""
    with _lock:
        items = _load()
        before = len(items)
        items = [i for i in items if i["id"] != schedule_id]
        _save(items)
    removed = before - len(items)
    return {"cancelled": removed > 0, "schedule_id": schedule_id}


@mcp.tool()
def schedule_note(
    content: str,
    category: str = "general",
    expires_days: int = 30,
) -> dict:
    """
    Save a time-stamped note for future sessions. Like a message to your future self.
    category: 'todo', 'idea', 'warning', 'reminder', 'general'.
    Returns: {note_id, saved_at}
    """
    note_file = SCHEDULE_FILE.parent / "nira_notes.json"
    try:
        notes = json.loads(note_file.read_text(encoding="utf-8")) if note_file.exists() else []
    except Exception:
        notes = []

    note = {
        "id": str(uuid.uuid4())[:8],
        "content": content,
        "category": category,
        "created_at": time.time(),
        "expires_at": time.time() + expires_days * 86400,
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    notes.append(note)
    # Prune expired
    notes = [n for n in notes if n.get("expires_at", 0) > time.time()]
    note_file.write_text(json.dumps(notes, indent=2), encoding="utf-8")
    return {"note_id": note["id"], "saved_at": note["saved_at"], "category": category}


@mcp.tool()
def schedule_notes_list(category: str = "") -> dict:
    """List all saved notes, optionally filtered by category."""
    note_file = SCHEDULE_FILE.parent / "nira_notes.json"
    try:
        notes = json.loads(note_file.read_text(encoding="utf-8")) if note_file.exists() else []
    except Exception:
        notes = []

    notes = [n for n in notes if n.get("expires_at", 0) > time.time()]
    if category:
        notes = [n for n in notes if n.get("category") == category]
    notes.sort(key=lambda x: x["created_at"], reverse=True)
    return {"notes": notes[:50], "total": len(notes)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
