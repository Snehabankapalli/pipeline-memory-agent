"""
Web dashboard for the Pipeline Memory Agent.

FastAPI application that reads the agent's persistent memory and exposes
a real-time view of pipeline health, run history, anomaly patterns,
and self-healing actions.

Run:
    uvicorn src.dashboard.app:app --host 0.0.0.0 --port 8080

Endpoints:
    GET  /                  → HTML dashboard (browser)
    GET  /api/health        → All pipeline health summaries
    GET  /api/pipeline/{id} → Single pipeline history and stats
    GET  /api/anomalies     → Recent anomalies across all pipelines
    GET  /api/heals         → Self-healing action log
    GET  /metrics           → Prometheus metrics
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse

MEMORY_FILE = Path(os.environ.get("PIPELINE_MEMORY_FILE", "pipeline_memory.json"))

app = FastAPI(
    title="Pipeline Memory Agent Dashboard",
    description="Persistent memory and health monitoring for AI-powered data pipelines",
    version="1.0.0",
)


# ──────────────────────────────────────────────
# Memory reader
# ──────────────────────────────────────────────

def _load_memory() -> dict:
    """Load agent memory from disk. Returns empty dict if not found."""
    if MEMORY_FILE.exists():
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    return {}


def _get_pipeline_health(pipeline_id: str, history: list[dict]) -> dict:
    """Compute health summary for a pipeline from its run history."""
    if not history:
        return {"status": "NO_DATA", "runs": 0}

    recent = history[-30:]   # Last 30 runs
    total = len(recent)
    failures = sum(1 for r in recent if r.get("status") == "failed")
    success_rate = round((total - failures) / total * 100, 1)

    durations = [r["duration_seconds"] for r in recent if r.get("duration_seconds")]
    avg_duration = round(sum(durations) / len(durations), 0) if durations else 0

    last_run = recent[-1]

    return {
        "pipeline_id": pipeline_id,
        "status": "HEALTHY" if success_rate >= 95 else ("WARNING" if success_rate >= 80 else "DEGRADED"),
        "success_rate_pct": success_rate,
        "total_runs": total,
        "failures": failures,
        "avg_duration_seconds": avg_duration,
        "last_run_status": last_run.get("status"),
        "last_run_at": last_run.get("timestamp"),
        "last_error": last_run.get("error") if last_run.get("status") == "failed" else None,
    }


# ──────────────────────────────────────────────
# API routes
# ──────────────────────────────────────────────

@app.get("/api/health")
async def get_all_health():
    """Health summary for all monitored pipelines."""
    memory = _load_memory()
    pipelines = memory.get("pipelines", {})
    results = []

    for pid, data in pipelines.items():
        history = data.get("run_history", [])
        results.append(_get_pipeline_health(pid, history))

    results.sort(key=lambda x: (
        {"DEGRADED": 0, "WARNING": 1, "HEALTHY": 2, "NO_DATA": 3}.get(x["status"], 3)
    ))

    overall = "HEALTHY"
    if any(r["status"] == "DEGRADED" for r in results):
        overall = "DEGRADED"
    elif any(r["status"] == "WARNING" for r in results):
        overall = "WARNING"

    return {
        "overall_status": overall,
        "pipeline_count": len(results),
        "pipelines": results,
        "memory_file": str(MEMORY_FILE),
        "last_checked": datetime.utcnow().isoformat(),
    }


@app.get("/api/pipeline/{pipeline_id}")
async def get_pipeline(pipeline_id: str, limit: int = 50):
    """Full run history and stats for a single pipeline."""
    memory = _load_memory()
    pipeline = memory.get("pipelines", {}).get(pipeline_id)

    if not pipeline:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}' not found in memory")

    history = pipeline.get("run_history", [])
    health = _get_pipeline_health(pipeline_id, history)

    return {
        "health": health,
        "baseline": pipeline.get("baseline", {}),
        "recent_runs": list(reversed(history))[:limit],
        "anomaly_count": len(pipeline.get("anomalies", [])),
        "heal_count": len(pipeline.get("healing_log", [])),
    }


@app.get("/api/anomalies")
async def get_anomalies(limit: int = 50):
    """Recent anomalies across all pipelines, newest first."""
    memory = _load_memory()
    all_anomalies = []

    for pid, data in memory.get("pipelines", {}).items():
        for anomaly in data.get("anomalies", []):
            all_anomalies.append({**anomaly, "pipeline_id": pid})

    all_anomalies.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return {
        "total": len(all_anomalies),
        "anomalies": all_anomalies[:limit],
    }


@app.get("/api/heals")
async def get_healing_log(limit: int = 50):
    """Self-healing actions taken across all pipelines."""
    memory = _load_memory()
    all_heals = []

    for pid, data in memory.get("pipelines", {}).items():
        for heal in data.get("healing_log", []):
            all_heals.append({**heal, "pipeline_id": pid})

    all_heals.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    success_count = sum(1 for h in all_heals if h.get("outcome") == "success")

    return {
        "total": len(all_heals),
        "success_rate_pct": round(success_count / max(len(all_heals), 1) * 100, 1),
        "heals": all_heals[:limit],
    }


@app.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    """Prometheus-format metrics for Grafana scraping."""
    memory = _load_memory()
    pipelines = memory.get("pipelines", {})

    total_runs = sum(len(d.get("run_history", [])) for d in pipelines.values())
    total_anomalies = sum(len(d.get("anomalies", [])) for d in pipelines.values())
    total_heals = sum(len(d.get("healing_log", [])) for d in pipelines.values())
    healthy = sum(
        1 for pid, d in pipelines.items()
        if _get_pipeline_health(pid, d.get("run_history", []))["status"] == "HEALTHY"
    )

    lines = [
        "# HELP pipeline_agent_pipelines_total Total pipelines in memory",
        f"pipeline_agent_pipelines_total {len(pipelines)}",
        "# HELP pipeline_agent_healthy_pipelines Pipelines with HEALTHY status",
        f"pipeline_agent_healthy_pipelines {healthy}",
        "# HELP pipeline_agent_runs_total Total pipeline runs recorded",
        f"pipeline_agent_runs_total {total_runs}",
        "# HELP pipeline_agent_anomalies_total Total anomalies detected",
        f"pipeline_agent_anomalies_total {total_anomalies}",
        "# HELP pipeline_agent_heals_total Total self-healing actions",
        f"pipeline_agent_heals_total {total_heals}",
    ]
    return "\n".join(lines)


# ──────────────────────────────────────────────
# HTML dashboard
# ──────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard():
    """Render the pipeline memory dashboard."""
    memory = _load_memory()
    pipelines = memory.get("pipelines", {})

    pipeline_cards = ""
    status_priority = {"DEGRADED": 0, "WARNING": 1, "HEALTHY": 2, "NO_DATA": 3}
    status_colors = {"HEALTHY": "#4caf50", "WARNING": "#ff9800", "DEGRADED": "#f44336", "NO_DATA": "#666"}

    sorted_pipelines = sorted(
        [(pid, data) for pid, data in pipelines.items()],
        key=lambda x: status_priority.get(
            _get_pipeline_health(x[0], x[1].get("run_history", []))["status"], 3
        )
    )

    for pid, data in sorted_pipelines:
        health = _get_pipeline_health(pid, data.get("run_history", []))
        color = status_colors.get(health["status"], "#666")
        anomaly_count = len(data.get("anomalies", []))
        heal_count = len(data.get("healing_log", []))
        last_run = health.get("last_run_at", "N/A")
        if last_run and len(last_run) > 19:
            last_run = last_run[:19]

        error_html = ""
        if health.get("last_error"):
            error_html = f'<div style="color:#f44336;font-size:0.8em;margin-top:8px">⚠ {health["last_error"][:100]}</div>'

        pipeline_cards += f"""
        <div class="pipeline-card">
            <div class="card-header">
                <span class="pipeline-name">{pid}</span>
                <span class="status-dot" style="background:{color}">{health['status']}</span>
            </div>
            <div class="card-stats">
                <div class="stat"><span class="stat-val">{health['success_rate_pct']}%</span><span class="stat-label">Success Rate</span></div>
                <div class="stat"><span class="stat-val">{health['total_runs']}</span><span class="stat-label">Total Runs</span></div>
                <div class="stat"><span class="stat-val">{health['avg_duration_seconds']}s</span><span class="stat-label">Avg Duration</span></div>
                <div class="stat"><span class="stat-val">{anomaly_count}</span><span class="stat-label">Anomalies</span></div>
                <div class="stat"><span class="stat-val">{heal_count}</span><span class="stat-label">Auto-Heals</span></div>
            </div>
            <div style="color:#8b949e;font-size:0.8em;margin-top:8px">Last run: {last_run}</div>
            {error_html}
        </div>
        """

    overall = "HEALTHY"
    for pid, data in pipelines.items():
        h = _get_pipeline_health(pid, data.get("run_history", []))
        if h["status"] == "DEGRADED":
            overall = "DEGRADED"
            break
        elif h["status"] == "WARNING":
            overall = "WARNING"

    overall_color = status_colors.get(overall, "#666")
    total_anomalies = sum(len(d.get("anomalies", [])) for d in pipelines.values())
    total_heals = sum(len(d.get("healing_log", [])) for d in pipelines.values())

    return f"""<!DOCTYPE html>
<html>
<head>
    <title>Pipeline Memory Agent</title>
    <meta http-equiv="refresh" content="30">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               background: #0d1117; color: #e6edf3; margin: 0; padding: 24px; }}
        .header {{ display: flex; align-items: center; gap: 16px; margin-bottom: 28px; }}
        .header h1 {{ margin: 0; font-size: 1.6em; }}
        .status-badge {{ padding: 6px 16px; border-radius: 20px; font-weight: bold;
                        font-size: 0.85em; background: {overall_color}; color: white; }}
        .summary-cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 28px; }}
        .summary-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; }}
        .summary-card h3 {{ margin: 0 0 8px; font-size: 0.8em; color: #8b949e; text-transform: uppercase; }}
        .summary-card .val {{ font-size: 2.2em; font-weight: bold; }}
        h2 {{ margin: 0 0 16px; color: #e6edf3; }}
        .pipeline-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 16px; }}
        .pipeline-card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }}
        .pipeline-name {{ font-weight: bold; font-size: 1em; color: #58a6ff; }}
        .status-dot {{ padding: 3px 10px; border-radius: 12px; font-size: 0.75em;
                      font-weight: bold; color: white; }}
        .card-stats {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; }}
        .stat {{ text-align: center; }}
        .stat-val {{ display: block; font-size: 1.2em; font-weight: bold; color: #e6edf3; }}
        .stat-label {{ display: block; font-size: 0.7em; color: #8b949e; margin-top: 2px; }}
        footer {{ margin-top: 24px; color: #8b949e; font-size: 0.8em; }}
        a {{ color: #58a6ff; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🧠 Pipeline Memory Agent</h1>
        <span class="status-badge">{overall}</span>
        <span style="color:#8b949e;font-size:0.85em">Auto-refreshes every 30s</span>
    </div>

    <div class="summary-cards">
        <div class="summary-card">
            <h3>Pipelines</h3>
            <div class="val">{len(pipelines)}</div>
        </div>
        <div class="summary-card">
            <h3>Total Anomalies</h3>
            <div class="val" style="color:#ff9800">{total_anomalies}</div>
        </div>
        <div class="summary-card">
            <h3>Auto-Heals</h3>
            <div class="val" style="color:#4caf50">{total_heals}</div>
        </div>
        <div class="summary-card">
            <h3>Memory File</h3>
            <div style="font-size:0.85em;color:#8b949e;margin-top:8px;word-break:break-all">{MEMORY_FILE}</div>
        </div>
    </div>

    <h2>Pipeline Health</h2>
    <div class="pipeline-grid">
        {pipeline_cards if pipeline_cards else '<div style="color:#8b949e">No pipelines in memory yet. Run the agent to start collecting data.</div>'}
    </div>

    <footer>
        API: <a href="/docs">/docs</a> ·
        Metrics: <a href="/metrics">/metrics</a> ·
        Anomalies: <a href="/api/anomalies">/api/anomalies</a> ·
        Heals: <a href="/api/heals">/api/heals</a> ·
        Updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
    </footer>
</body>
</html>"""
