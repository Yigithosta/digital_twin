"""n8n webhook bildirimi: alarm anında otomasyon akışını tetikler."""

import json
import urllib.request

from app.config import N8N_WEBHOOK_URL


def notify(payload: dict) -> bool:
    req = urllib.request.Request(
        N8N_WEBHOOK_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except OSError:
        return False   # n8n çalışmıyorsa bildirim atlanır
