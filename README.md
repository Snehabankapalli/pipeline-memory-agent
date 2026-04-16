# Pipeline Memory Agent

[![CI](https://github.com/Snehabankapalli/pipeline-memory-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Snehabankapalli/pipeline-memory-agent/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> A Claude-powered agent that builds persistent memory of your data pipelines, run history, anomaly patterns, and self-healing logic that gets smarter over time.

Most monitoring tools alert you when something breaks. This agent **remembers** why things broke, what fixed it, and gets better at predicting failures before they happen.

---

## What It Does

| Capability | Description |
|---|---|
| **Persistent Memory** | Stores 90 days of run history per pipeline in JSON — duration, row counts, credits, errors |
| **Baseline Learning** | Calculates P95 duration and average row count from successful runs automatically |
| **Anomaly Detection** | Claude compares each run against historical memory and flags outliers with root cause |
| **Pattern Recognition** | Remembers past failures — Claude uses healing log to avoid repeating wrong fixes |
| **Weekly Digest** | Generates a markdown health report across all pipelines from accumulated memory |
| **Self-Healing Log** | Records every auto-fix action and its outcome so Claude learns what works |

---

## How It Works

```
Pipeline Run
    │
    ▼
┌──────────────────────────────┐
│  Memory Store (JSON)         │
│  90-day run history          │
│  Per-pipeline baselines      │
│  Healing action log          │
└──────────┬───────────────────┘
           │ historical context
           ▼
┌──────────────────────────────┐
│  Claude Opus (adaptive think)│
│  Compares current vs history │
│  Identifies root cause       │
│  Recommends specific fix     │
│  Decides if safe to self-heal│
└──────────┬───────────────────┘
           │ analysis + action
           ▼
    Slack alert / auto-heal
```

---

## Install

```bash
git clone https://github.com/Snehabankapalli/pipeline-memory-agent
cd pipeline-memory-agent
pip install -r requirements.txt
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env
```

---

## Quick Start

```python
from src.memory_agent import PipelineMemoryAgent

agent = PipelineMemoryAgent()

# Record a pipeline run and check for anomalies
result = agent.run_check(
    pipeline_name="fct_credit_card_daily",
    current_stats={
        "status": "success",
        "duration_minutes": 94.7,   # 3x your normal 30 min
        "rows_processed": 580_000,  # 70% below your 2M average
        "credits_used": 2.8,        # 5x your normal 0.5
    }
)

print(result["severity"])           # "critical"
print(result["analysis"])           # "Duration is 3.1x above P95 baseline..."
print(result["root_cause_hypothesis"])  # "Full table scan — likely missing clustering key"
print(result["recommended_action"]) # "Add clustering key on event_date"
print(result["can_self_heal"])      # True/False
```

---

## Demo (No Airflow/Snowflake Needed)

```bash
python -m examples.demo
```

Simulates 30 days of pipeline history, then runs an anomaly check on a suspicious run and generates a weekly digest.

**Sample output:**

```
📚 Seeding 30 days of pipeline history...
✅ Seeded history for 'fct_credit_card_daily'
   Baseline P95 duration: 34.1 min
   Baseline avg rows:     2,012,445

======================================================
🚨 ANOMALY CHECK — Suspicious run detected
======================================================

CLAUDE'S ANALYSIS:
Is anomaly:   True
Severity:     CRITICAL

Analysis:
Duration at 94.7 minutes is 2.8x above the P95 baseline of 34.1 minutes.
Row count of 580K is 71% below the 2M average. This combination suggests
a partial data load, likely due to a full table scan on an unpartitioned
staging table — consistent with the Snowpipe stall failure 15 days ago.

Root cause:   Full table scan in stg_transactions — upstream schema change
              removed the clustering key on event_date

Action:       Re-cluster stg_transactions on event_date, re-run fct_credit_card_daily
Can heal:     True
Heal command: dbt run --select stg_transactions fct_credit_card_daily
```

---

## Integrate with Airflow

```python
from airflow.decorators import task
from src.memory_agent import PipelineMemoryAgent

@task
def check_pipeline_health(pipeline_name: str, run_stats: dict) -> dict:
    agent = PipelineMemoryAgent()
    result = agent.run_check(pipeline_name, run_stats)

    if result["is_anomaly"] and result["severity"] in ("high", "critical"):
        # Send to Slack, trigger PagerDuty, etc.
        raise ValueError(f"Pipeline anomaly: {result['analysis']}")

    return result
```

---

## Run Tests

```bash
python -m pytest tests/ -v
```

---

## Memory Schema

Memory is stored in `pipeline_memory.json`:

```json
{
  "pipelines": {
    "fct_credit_card_daily": {
      "runs": [
        {
          "timestamp": "2025-03-15T06:12:00",
          "status": "success",
          "duration_minutes": 31.2,
          "rows_processed": 2045120,
          "credits_used": 0.52
        }
      ],
      "baseline_duration_p95": 34.1,
      "baseline_row_count_avg": 2012445
    }
  },
  "healing_log": [
    {
      "timestamp": "2025-03-01T07:45:00",
      "pipeline": "fct_credit_card_daily",
      "action": "dbt run --select fct_credit_card_daily",
      "outcome": "success",
      "credits_saved": 0.3
    }
  ]
}
```

---

## 🛒 More Data Engineering Resources

| Product | What You Get | Price |
|---|---|---|
| [Data Engineering Claude Code Starter Kit](https://snehabank.gumroad.com/l/aaugjh) | 9 Claude Code slash commands — dbt, Snowflake, pipelines | $19 |
| [Snowflake Cost Optimization Playbook](https://snehabank.gumroad.com/l/kapqn) | 10 cost leaks + copy-paste SQL to detect and fix each one | $25 |
| [Data Engineering Interview Kit](https://snehabank.gumroad.com/l/qjfgjf) | 50 SQL questions + 10 system designs + 4 cheat sheets | $15 |

---

## Built By

**Sneha Bankapalli** — Senior Data Engineer at a fintech company.
Built from experience running production pipelines at 99.9% SLA across 100M+ daily events.

[![LinkedIn](https://img.shields.io/badge/LinkedIn-sneha2095-0077B5?style=flat&logo=linkedin)](https://www.linkedin.com/in/sneha2095/)
[![GitHub](https://img.shields.io/badge/GitHub-Snehabankapalli-181717?style=flat&logo=github)](https://github.com/Snehabankapalli)
