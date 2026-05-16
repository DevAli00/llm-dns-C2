from collections import deque

sessions = {}

def create_session(session_id, goal, os, user, hostname):
    sessions[session_id] = {
        "goal": goal,
        "os": os,
        "user": user,
        "hostname": hostname,
        "task_queue": deque(),
        "history": [],
        "status": "idle"
    }

def add_task(session_id, command):
    sessions[session_id]["task_queue"].append(command)
    sessions[session_id]["status"] = "active"

def get_next_task(session_id):
    queue = sessions[session_id]["task_queue"]
    if len(queue) == 0:
        return None
    return queue.popleft()

def store_result(session_id, command, output):
    sessions[session_id]["history"].append({
        "command": command,
        "output": output
    })