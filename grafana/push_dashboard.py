"""
Grafana'ya gelişmiş dashboard yükler.
Çalıştırma: python grafana/push_dashboard.py
"""
import json, urllib.request, urllib.error

GRAFANA = "http://localhost:3000"
AUTH    = ("admin", "admin123")

dashboard = {
  "uid": "maden-digital_twin-v2",
  "title": "Maden Dijital İkiz — Ekipman İzleme",
  "schemaVersion": 38,
  "version": 2,
  "refresh": "10s",
  "time": {"from": "now-3h", "to": "now"},
  "timezone": "browser",
  "tags": ["maden", "digital_twin", "anomali"],
  "panels": [

    # ── Stat: Toplam Okuma ──────────────────────────────
    {
      "id": 1, "type": "stat", "title": "Toplam Sensör Okuması",
      "gridPos": {"x": 0, "y": 0, "w": 6, "h": 4},
      "datasource": {"uid": "timescaledb"},
      "targets": [{"rawSql": "SELECT COUNT(*) as value FROM sensor_readings", "format": "table"}],
      "fieldConfig": {"defaults": {"color": {"mode": "fixed", "fixedColor": "blue"}, "unit": "short",
        "thresholds": {"mode": "absolute", "steps": [{"color": "blue", "value": None}]}}}
    },

    # ── Stat: Anomali Oranı ─────────────────────────────
    {
      "id": 2, "type": "stat", "title": "Anomali Oranı (24 Saat)",
      "gridPos": {"x": 6, "y": 0, "w": 6, "h": 4},
      "datasource": {"uid": "timescaledb"},
      "targets": [{"rawSql": """
        SELECT ROUND(
          100.0 * COUNT(*) FILTER (WHERE is_anomaly = true) / NULLIF(COUNT(*),0), 2
        ) as value
        FROM sensor_readings
        WHERE time >= NOW() - INTERVAL '24 hours'
      """, "format": "table"}],
      "fieldConfig": {"defaults": {"unit": "percent", "color": {"mode": "thresholds"},
        "thresholds": {"mode": "absolute", "steps": [
          {"color": "green", "value": None},
          {"color": "yellow", "value": 3},
          {"color": "red", "value": 7}
        ]}}}
    },

    # ── Stat: Aktif Anomali ─────────────────────────────
    {
      "id": 3, "type": "stat", "title": "Çözülmemiş Anomaliler",
      "gridPos": {"x": 12, "y": 0, "w": 6, "h": 4},
      "datasource": {"uid": "timescaledb"},
      "targets": [{"rawSql": "SELECT COUNT(*) as value FROM anomaly_logs WHERE resolved = false", "format": "table"}],
      "fieldConfig": {"defaults": {"color": {"mode": "thresholds"},
        "thresholds": {"mode": "absolute", "steps": [
          {"color": "green", "value": None},
          {"color": "yellow", "value": 5},
          {"color": "red", "value": 15}
        ]}}}
    },

    # ── Stat: Son Anomali ───────────────────────────────
    {
      "id": 4, "type": "stat", "title": "Son Anomali Skoru",
      "gridPos": {"x": 18, "y": 0, "w": 6, "h": 4},
      "datasource": {"uid": "timescaledb"},
      "targets": [{"rawSql": """
        SELECT ROUND(CAST(anomaly_score AS NUMERIC), 3) as value
        FROM anomaly_logs ORDER BY time DESC LIMIT 1
      """, "format": "table"}],
      "fieldConfig": {"defaults": {"unit": "percentunit", "color": {"mode": "thresholds"},
        "thresholds": {"mode": "absolute", "steps": [
          {"color": "green", "value": None},
          {"color": "yellow", "value": 0.5},
          {"color": "red", "value": 0.8}
        ]}}}
    },

    # ── Timeseries: Konveyör Sıcaklık ──────────────────
    {
      "id": 5, "type": "timeseries", "title": "Konveyör 01 — Sıcaklık (°C)",
      "gridPos": {"x": 0, "y": 4, "w": 12, "h": 8},
      "datasource": {"uid": "timescaledb"},
      "targets": [
        {"rawSql": "SELECT time, temperature as \"Sıcaklık\" FROM sensor_readings WHERE equipment_id='conveyor_01' AND $__timeFilter(time) ORDER BY time", "format": "time_series"},
        {"rawSql": "SELECT time, temperature as \"Anomali\" FROM sensor_readings WHERE equipment_id='conveyor_01' AND is_anomaly=true AND $__timeFilter(time) ORDER BY time", "format": "time_series"},
      ],
      "fieldConfig": {"defaults": {"unit": "celsius", "color": {"mode": "palette-classic"},
        "custom": {"lineWidth": 2, "fillOpacity": 10},
        "thresholds": {"mode": "absolute", "steps": [
          {"color": "green", "value": None},
          {"color": "yellow", "value": 65},
          {"color": "red", "value": 80}
        ]}}},
      "options": {"tooltip": {"mode": "single"}, "legend": {"displayMode": "list", "placement": "bottom"}}
    },

    # ── Timeseries: Konveyör Titreşim ───────────────────
    {
      "id": 6, "type": "timeseries", "title": "Konveyör 01 — Titreşim (mm/s)",
      "gridPos": {"x": 12, "y": 4, "w": 12, "h": 8},
      "datasource": {"uid": "timescaledb"},
      "targets": [{"rawSql": "SELECT time, vibration as \"Titreşim\" FROM sensor_readings WHERE equipment_id='conveyor_01' AND $__timeFilter(time) ORDER BY time", "format": "time_series"}],
      "fieldConfig": {"defaults": {"unit": "velocityms", "color": {"fixedColor": "#8b5cf6", "mode": "fixed"},
        "custom": {"lineWidth": 2, "fillOpacity": 10},
        "thresholds": {"mode": "absolute", "steps": [
          {"color": "green", "value": None},
          {"color": "yellow", "value": 5},
          {"color": "red", "value": 8}
        ]}}}
    },

    # ── Timeseries: Pompa Basınç ────────────────────────
    {
      "id": 7, "type": "timeseries", "title": "Pompa 01 — Basınç (bar)",
      "gridPos": {"x": 0, "y": 12, "w": 8, "h": 8},
      "datasource": {"uid": "timescaledb"},
      "targets": [{"rawSql": "SELECT time, pressure as \"Basınç\" FROM sensor_readings WHERE equipment_id='pump_01' AND $__timeFilter(time) ORDER BY time", "format": "time_series"}],
      "fieldConfig": {"defaults": {"unit": "pressurembar", "color": {"fixedColor": "#06b6d4", "mode": "fixed"},
        "custom": {"lineWidth": 2, "fillOpacity": 10}}}
    },

    # ── Timeseries: Kırıcı Akım ─────────────────────────
    {
      "id": 8, "type": "timeseries", "title": "Kırıcı 01 — Akım (A)",
      "gridPos": {"x": 8, "y": 12, "w": 8, "h": 8},
      "datasource": {"uid": "timescaledb"},
      "targets": [{"rawSql": "SELECT time, current as \"Akım\" FROM sensor_readings WHERE equipment_id='crusher_01' AND $__timeFilter(time) ORDER BY time", "format": "time_series"}],
      "fieldConfig": {"defaults": {"unit": "amp", "color": {"fixedColor": "#ec4899", "mode": "fixed"},
        "custom": {"lineWidth": 2, "fillOpacity": 10}}}
    },

    # ── Timeseries: Anomali Skoru ───────────────────────
    {
      "id": 9, "type": "timeseries", "title": "Anomali Skoru — Tüm Ekipmanlar",
      "gridPos": {"x": 16, "y": 12, "w": 8, "h": 8},
      "datasource": {"uid": "timescaledb"},
      "targets": [
        {"rawSql": "SELECT time, anomaly_score as \"Konveyör\" FROM sensor_readings WHERE equipment_id='conveyor_01' AND $__timeFilter(time) ORDER BY time", "format": "time_series"},
        {"rawSql": "SELECT time, anomaly_score as \"Pompa\" FROM sensor_readings WHERE equipment_id='pump_01' AND $__timeFilter(time) ORDER BY time", "format": "time_series"},
        {"rawSql": "SELECT time, anomaly_score as \"Kırıcı\" FROM sensor_readings WHERE equipment_id='crusher_01' AND $__timeFilter(time) ORDER BY time", "format": "time_series"},
      ],
      "fieldConfig": {"defaults": {"unit": "percentunit", "min": 0, "max": 1,
        "custom": {"lineWidth": 2, "fillOpacity": 5},
        "thresholds": {"mode": "absolute", "steps": [
          {"color": "green", "value": None},
          {"color": "yellow", "value": 0.5},
          {"color": "red", "value": 0.8}
        ]}}},
      "options": {"tooltip": {"mode": "multi"}, "legend": {"displayMode": "list", "placement": "bottom"}}
    },

    # ── Table: Son Anomaliler ───────────────────────────
    {
      "id": 10, "type": "table", "title": "Son Anomali Kayıtları",
      "gridPos": {"x": 0, "y": 20, "w": 24, "h": 8},
      "datasource": {"uid": "timescaledb"},
      "targets": [{"rawSql": """
        SELECT
          time AS "Zaman",
          equipment_id AS "Ekipman",
          ROUND(CAST(anomaly_score AS NUMERIC), 3) AS "Anomali Skoru",
          description AS "Açıklama",
          CASE WHEN resolved THEN 'Çözüldü' ELSE 'Aktif' END AS "Durum"
        FROM anomaly_logs
        ORDER BY time DESC
        LIMIT 20
      """, "format": "table"}],
      "options": {"sortBy": [{"displayName": "Zaman", "desc": True}]},
      "fieldConfig": {"defaults": {"custom": {"displayMode": "auto"}},
        "overrides": [
          {"matcher": {"id": "byName", "options": "Anomali Skoru"},
           "properties": [{"id": "custom.displayMode", "value": "color-background"},
                          {"id": "thresholds", "value": {"mode": "absolute", "steps": [
                            {"color": "green", "value": None},
                            {"color": "yellow", "value": 0.5},
                            {"color": "red", "value": 0.8}]}}]},
          {"matcher": {"id": "byName", "options": "Durum"},
           "properties": [{"id": "custom.displayMode", "value": "color-background"},
                          {"id": "mappings", "value": [
                            {"type": "value", "options": {"Aktif": {"color": "red", "index": 0}}},
                            {"type": "value", "options": {"Çözüldü": {"color": "green", "index": 1}}}]}]}
        ]}
    },
  ]
}

payload = json.dumps({
    "dashboard": dashboard,
    "overwrite": True,
    "folderId": 0,
}).encode()

req = urllib.request.Request(
    f"{GRAFANA}/api/dashboards/db",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
import base64
cred = base64.b64encode(f"{AUTH[0]}:{AUTH[1]}".encode()).decode()
req.add_header("Authorization", f"Basic {cred}")

try:
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
        print(f"Dashboard yüklendi: {GRAFANA}{result.get('url', '')}")
except urllib.error.HTTPError as e:
    print(f"Hata: {e.code} — {e.read().decode()}")
