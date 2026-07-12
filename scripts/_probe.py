"""Quick probe to confirm the user's reported issues."""
import json, time, urllib.request

BASE = "http://127.0.0.1:8102"

def get(path, timeout=30):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8")

def post_json(path, body, timeout=120):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8")

print("== 1. Initial sessions list ==")
status, body = get("/sessions")
data = json.loads(body)
ids = [s["session_id"] for s in data.get("sessions", [])]
print(f"  status={status} count={len(ids)}")
print(f"  ids={ids[:8]}...")

NEW_SID = "probe-py-1"
print(f"\n== 2. POST /chat with new sid={NEW_SID} ==")
try:
    status, body = post_json("/chat", {"session_id": NEW_SID, "message": "hello there"}, timeout=120)
    print(f"  status={status}")
    d = json.loads(body)
    print(f"  answer_preview={d.get('answer','')[:80]!r}")
except Exception as e:
    print(f"  ERROR: {e}")

print(f"\n== 3. Sessions list after chat ==")
status, body = get("/sessions")
data = json.loads(body)
ids = [s["session_id"] for s in data.get("sessions", [])]
print(f"  count={len(ids)}")
print(f"  probe-py-1 in list? {NEW_SID in ids}")

print(f"\n== 4. Direct fetch /session/{NEW_SID}/messages ==")
status, body = get(f"/session/{NEW_SID}/messages", timeout=20)
print(f"  status={status}")
print(f"  body={body[:300]}")

print(f"\n== 5. /admin/kb/sources ==")
status, body = get("/admin/kb/sources", timeout=30)
print(f"  status={status}")
data = json.loads(body)
print(f"  total_sources={data.get('total_sources')} total_chunks={data.get('total_chunks')}")
print(f"  sources:")
for s in data.get("sources", []):
    print(f"    - {s['source']}  ({s['chunks']} chunks)")