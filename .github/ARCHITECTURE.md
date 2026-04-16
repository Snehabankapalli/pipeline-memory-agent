# Pipeline Memory Agent — Architecture

Claude-powered agent with persistent pipeline memory, anomaly detection, and self-healing.

## System Flow

```mermaid
graph LR
    P["🔧 Pipeline Run<br/>Airflow / dbt / Glue"]
    W["🪝 Webhook<br/>on_complete"]
    A["🧠 Memory Agent<br/>Claude Sonnet 4.6"]
    M["💾 Memory Store<br/>pipeline_memory.json"]
    D["📊 Dashboard<br/>FastAPI + dark UI"]
    S["💬 Slack<br/>anomaly alerts"]
    H["🩹 Self-Heal<br/>retry / scale / skip"]

    P -->|run metrics| W
    W -->|ingest| A
    A <-->|read/write| M
    A -->|severity>P2| S
    A -->|auto-fix| H
    M -->|read| D

    style A fill:#f3e5f5
    style M fill:#e8f5e9
    style D fill:#fff3e0
```

## Memory Model

```mermaid
graph TB
    subgraph "Per Pipeline"
        R["runs[] (90 days)<br/>- duration_s<br/>- rows_out<br/>- credits<br/>- status<br/>- error_msg"]
        B["baseline<br/>- p95_duration<br/>- avg_rows<br/>- typical_credits"]
        AN["anomalies[]<br/>- detected_at<br/>- severity<br/>- root_cause<br/>- resolution"]
        HL["healing_log[]<br/>- action<br/>- outcome<br/>- success_rate"]
    end

    R -->|recompute on write| B
    R -->|compare vs| AN
    AN -->|Claude picks fix| HL
    HL -->|feedback loop| AN

    style B fill:#e1f5ff
    style HL fill:#fce4ec
```

## Agent Decision Loop

```mermaid
sequenceDiagram
    participant P as Pipeline
    participant A as Memory Agent
    participant C as Claude
    participant M as Memory Store
    participant S as Slack
    participant H as Healer

    P->>A: run_complete(metrics)
    A->>M: load(pipeline_id)
    M-->>A: history + baseline + healing_log
    A->>C: analyze(run, history, past_fixes)
    C-->>A: {is_anomaly, severity, root_cause, suggested_fix}
    alt is_anomaly && severity >= P2
        A->>S: post alert
    end
    alt suggested_fix && confidence > 0.7
        A->>H: execute(fix)
        H-->>A: outcome
        A->>M: append healing_log
    end
    A->>M: persist run + anomaly
```

## Dashboard Routes

| Route | Purpose |
|-------|---------|
| `GET /` | HTML dashboard with pipeline health cards |
| `GET /api/health` | Service health check |
| `GET /api/pipeline/{id}` | Run history + baseline for one pipeline |
| `GET /api/anomalies` | All detected anomalies across pipelines |
| `GET /api/heals` | Self-healing action log |
| `GET /metrics` | Prometheus metrics for scraping |

## Tech Stack

| Layer | Technology |
|-------|------------|
| LLM | Anthropic Claude Sonnet 4.6 |
| Storage | JSON (append-only per pipeline) |
| API | FastAPI, Pydantic v2 |
| UI | Server-rendered HTML + Tailwind-like dark theme |
| Metrics | prometheus-client |
| Testing | pytest, pytest-asyncio |

## Why JSON (not a database)?

- **Portability** — zero infra, single file per deployment
- **Git-diffable** — memory changes are reviewable in PRs
- **Fast enough** — <10K runs per pipeline fits in memory
- **Easy migration** — swap to SQLite/Postgres later behind `MemoryStore` interface
