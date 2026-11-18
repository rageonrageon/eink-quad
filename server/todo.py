"""The to-do list: a plain list of tasks kept in a JSON file next to config.json (on Railway, on the /data volume).

Tasks are added, finished and deleted from the settings page. Each task:
  {"id", "title", "due": "" or "YYYY-MM-DD", "added": "YYYY-MM-DD", "done": bool}
Order is the order they were added. A finished task leaves the screen but stays in the settings list (greyed out)
until it is cleared, so a mis-tap can be undone. If "remove after N days" is set, a task older than N days (counted
from the day it was added) is deleted by prune(); 0 means tasks stay until cleared.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
import uuid
from dataclasses import dataclass

PATH = os.environ.get("QUAD_TODOS") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "todos.json")
_lock = threading.Lock()


@dataclass
class Item:
    id: str
    title: str
    due: dt.date | None = None


def load(path: str | None = None) -> list:
    try:
        with open(path or PATH, encoding="utf-8") as f:
            data = json.load(f)
        return [t for t in data if isinstance(t, dict) and t.get("id") and t.get("title")]
    except (OSError, ValueError):
        return []


def _save(items: list, path: str | None = None):
    p = path or PATH
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=1)
    os.replace(tmp, p)


def add(title: str, due: str = "", today: dt.date | None = None, path: str | None = None) -> dict:
    title = (title or "").strip()
    if not title:
        raise ValueError("Give the task a title")
    due = (due or "").strip()
    if due:
        try:
            dt.date.fromisoformat(due)
        except ValueError:
            raise ValueError("Due date should look like 2026-11-20")
    t = {"id": uuid.uuid4().hex[:8], "title": title[:80], "due": due,
         "added": (today or dt.date.today()).isoformat(), "done": False}
    with _lock:
        items = load(path)
        items.append(t)
        _save(items, path)
    return t


def set_done(tid: str, done: bool = True, path: str | None = None) -> bool:
    with _lock:
        items = load(path)
        hit = False
        for t in items:
            if t["id"] == tid:
                t["done"], hit = bool(done), True
        if hit:
            _save(items, path)
    return hit


def delete(tid: str, path: str | None = None) -> bool:
    with _lock:
        items = load(path)
        keep = [t for t in items if t["id"] != tid]
        if len(keep) == len(items):
            return False
        _save(keep, path)
    return True


def clear_done(path: str | None = None) -> int:
    with _lock:
        items = load(path)
        keep = [t for t in items if not t.get("done")]
        if len(keep) != len(items):
            _save(keep, path)
    return len(items) - len(keep)


def prune(today: dt.date, expire_days: int, path: str | None = None) -> int:
    """Delete tasks added more than expire_days ago. 0 (or less) keeps everything."""
    if not expire_days or expire_days <= 0:
        return 0
    with _lock:
        items = load(path)
        keep = []
        for t in items:
            try:
                age = (today - dt.date.fromisoformat(t.get("added") or today.isoformat())).days
            except ValueError:
                age = 0
            if age <= expire_days:
                keep.append(t)
        if len(keep) != len(items):
            _save(keep, path)
    return len(items) - len(keep)


def open_items(path: str | None = None) -> list:
    """What the tile shows: tasks not finished, in the order added."""
    out = []
    for t in load(path):
        if t.get("done"):
            continue
        try:
            due = dt.date.fromisoformat(t["due"]) if t.get("due") else None
        except ValueError:
            due = None
        out.append(Item(t["id"], t["title"], due))
    return out


def listing(path: str | None = None) -> list:
    """Everything, for the settings page: open tasks first (in the order added), then finished ones."""
    items = load(path)
    return [t for t in items if not t.get("done")] + [t for t in items if t.get("done")]
