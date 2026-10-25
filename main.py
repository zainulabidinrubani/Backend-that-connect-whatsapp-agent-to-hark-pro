import os
import requests
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

BASE = "https://api.whatsapp.com/agent/v1"
WA_TOKEN = os.environ["WA_TOKEN"]
RELAY_KEY = os.environ["RELAY_KEY"]
recipient = os.environ.get("WA_RECIPIENT")

app = FastAPI()
HEADERS = {"Authorization": f"Bearer {WA_TOKEN}", "Content-Type": "application/json"}


class Msg(BaseModel):
    text: str


def check(key):
    if key != RELAY_KEY:
        raise HTTPException(401, "bad key")


def discover():
    """Find the creator's id (user:...) from the agent's update buffer."""
    global recipient
    if recipient:
        return recipient
    r = requests.get(f"{BASE}/updates", headers=HEADERS,
                     params={"offset": 0, "limit": 100, "timeout": 0}, timeout=30)
    if r.status_code == 204:
        return None
    r.raise_for_status()
    for entry in r.json().get("entry", []):
        for ch in entry.get("changes", []):
            v = ch.get("value", {})
            ids = [m.get("from") for m in v.get("messages", [])]
            ids += [s.get("recipient_id") for s in v.get("statuses", [])]
            ids += [c.get("wa_id") for c in v.get("contacts", [])]
            for i in ids:
                if i and i.startswith("user:"):
                    recipient = i
                    return recipient
    return None


@app.get("/ping")
def ping(x_api_key: str = Header(None)):
    check(x_api_key)
    return {"ok": True, "recipient_known": bool(discover())}


@app.post("/send")
def send(msg: Msg, x_api_key: str = Header(None)):
    check(x_api_key)
    to = discover()
    if not to:
        raise HTTPException(409, "Message the agent once on WhatsApp first")
    sent = []
    text = msg.text
    while text:  # WhatsApp text limit is 4096 chars
        chunk, text = text[:4000], text[4000:]
        body = {"messaging_product": "whatsapp", "to": to,
                "type": "text", "text": {"body": chunk}}
        r = requests.post(f"{BASE}/messages", headers=HEADERS, json=body, timeout=30)
        if r.status_code >= 400:
            raise HTTPException(502, r.text[:300])
        sent.append(r.json())
    return {"ok": True, "parts": len(sent)}
