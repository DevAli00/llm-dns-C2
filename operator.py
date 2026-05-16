import queue_store
import react_engine
import threading

def create_session_interactive():
    print("\n--- New Session ---")
    session_id = input("Session ID: ")
    goal = input("Goal: ")
    os = input("OS: ")
    user = input("User: ")
    hostname = input("Hostname: ")
    queue_store.create_session(session_id, goal, os, user, hostname)
    print(f"Session {session_id} created.")
    return session_id

def watch_session(session_id: str):
    import time
    print(f"\n--- Watching session {session_id} ---")
    seen = 0
    while True:
        history = queue_store.sessions[session_id]["history"]
        if len(history) > seen:
            for entry in history[seen:]:
                print(f"\n> {entry['command']}")
                print(f"  {entry['output']}")
            seen = len(history)
        time.sleep(2)

def start():
    print("DNS C2 Operator Console")
    print("=======================")
    while True:
        print("\n[1] New session")
        print("[2] Launch ReAct loop")
        print("[3] Watch session")
        print("[4] Exit")
        choice = input("\n> ")

        if choice == "1":
            create_session_interactive()

        elif choice == "2":
            session_id = input("Session ID: ")
            steps = int(input("Max steps: "))
            t = threading.Thread(
                target=react_engine.run_react_loop,
                args=(session_id, steps)
            )
            t.daemon = True
            t.start()
            print("ReAct loop started in background.")

        elif choice == "3":
            session_id = input("Session ID: ")
            watch_session(session_id)

        elif choice == "4":
            break

if __name__ == "__main__":
    start()