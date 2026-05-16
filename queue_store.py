from collections import deque
import json
import os

DB_FILE = "sessions.json"

def _load() -> dict:
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, "r") as f:
        data = json.load(f)
    for s in data.values():
        s["task_queue"] = deque(s["task_queue"])
    return data

def _save(sessions: dict) -> None:
    data = {k: {**v, "task_queue": list(v["task_queue"])}
            for k, v in sessions.items()}
    with open(DB_FILE, "w") as f:
        json.dump(data, f)

def create_session(session_id: str, goal: str, os: str, user: str, hostname: str) -> None:
    sessions = _load()
    sessions[session_id] = {
        "goal": goal,
        "os": os,
        "user": user,
        "hostname": hostname,
        "task_queue": deque(),
        "history": [],
        "status": "idle",
        "last_task": None,
    }
    _save(sessions)

def add_task(session_id: str, command: str) -> None:
    sessions = _load()
    sessions[session_id]["task_queue"].append(command)
    sessions[session_id]["status"] = "active"
    _save(sessions)

def get_next_task(session_id: str) -> str | None:
    sessions = _load()
    queue = sessions[session_id]["task_queue"]
    if len(queue) == 0:
        return None
    task = queue.popleft()
    sessions[session_id]["last_task"] = task
    _save(sessions)
    return task

def store_result(session_id: str, command: str, output: str) -> None:
    sessions = _load()
    sessions[session_id]["history"].append({
        "command": command,
        "output": output,
    })
    _save(sessions)

def session_exists(session_id: str) -> bool:
    return session_id in _load()

def get_session(session_id: str) -> dict | None:
    return _load().get(session_id)

def get_last_task(session_id: str) -> str | None:
    session = _load().get(session_id)
    return session["last_task"] if session else None

def get_history(session_id: str) -> list:
    session = _load().get(session_id)
    return session["history"] if session else []
