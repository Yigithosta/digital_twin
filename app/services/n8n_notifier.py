"""
n8n webhook bildirimi.
Anomali tespitinde n8n workflow'unu tetikler.
"""
import urllib.request
import json
import os
from dotenv import load_dotenv

load_dotenv()

N8N_WEBHOOK = os.getenv("N8N_WEBHOOK_URL", "http://localhost:5678/webhook/anomali-alarm")


def notify(payload: dict):
    try:
        data = json.dumps(payload).encode()
        req  = urllib.request.Request(
            N8N_WEBHOOK,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False
