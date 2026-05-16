import ollama
import queue_store
import json

MODEL = "qwen3.5:9b"

def build_prompt(session_id: str) -> str:
    session = queue_store.get_session(session_id)
    history_text = "\n".join([
        f"Command: {h['command']}\nOutput: {h['output']}"
        for h in session["history"]
    ])
    return f"""You are an autonomous red team agent.
Your goal: {session['goal']}
Environment:
  OS: {session['os']}
  User: {session['user']}
  Hostname: {session['hostname']}

Commands run so far:
{history_text if history_text else "None yet."}

Based on the goal and history, return ONLY the next shell command to run.
No explanation. No markdown. Just the raw command."""

def decide_next_task(session_id: str) -> str:
    prompt = build_prompt(session_id)
    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    command = response["message"]["content"].strip()
    return command

def run_react_loop(session_id: str, max_steps: int = 10):
    print(f"Starting ReAct loop for session {session_id}")
    for step in range(max_steps):
        print(f"\n--- Step {step + 1} ---")
        
        # Reason — LLM decides next task
        command = decide_next_task(session_id)
        print(f"LLM decided: {command}")

        # Act — queue the task for agent
        queue_store.add_task(session_id, command)

        # Observe — wait for result
        import time
        time.sleep(6)  # wait for agent to execute and report back

        # check history for latest result
        history = queue_store.get_history(session_id)
        if history:
            last = history[-1]
            print(f"Result: {last['output']}")
        
        # stop condition
        if "GOAL_COMPLETE" in command:
            print("LLM signaled goal complete.")
            break