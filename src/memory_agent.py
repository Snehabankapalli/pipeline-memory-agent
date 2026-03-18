"""
Pipeline Memory Agent
---------------------
A Claude-powered agent that watches your data pipelines and builds persistent memory
of their behavior over time — run history, anomalies, cost patterns, and self-heals
common failures automatically.

Usage:
    from src.memory_agent import PipelineMemoryAgent
    agent = PipelineMemoryAgent()
    agent.run_check()
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import anthropic

MEMORY_FILE = Path("pipeline_memory.json")
MODEL = "claude-opus-4-6"


class PipelineMemoryAgent:
    """
    Monitors data pipelines and maintains persistent memory of their behavior.

    Memory tracks:
    - Run history (success/failure/duration per pipeline)
    - Anomaly patterns (when things typically break)
    - Cost trends (credits/compute over time)
    - Self-healing actions taken and their outcomes
    """

    def __init__(self, memory_path: Path = MEMORY_FILE):
        self.client = anthropic.Anthropic()
        self.memory_path = memory_path
        self.memory = self._load_memory()

    # ------------------------------------------------------------------ #
    # Memory persistence                                                   #
    # ------------------------------------------------------------------ #

    def _load_memory(self) -> dict:
        """Load persistent memory from disk. Returns empty structure if first run."""
        if self.memory_path.exists():
            with open(self.memory_path, "r") as f:
                return json.load(f)
        return {
            "pipelines": {},
            "anomaly_patterns": [],
            "cost_history": [],
            "healing_log": [],
            "last_updated": None,
        }

    def _save_memory(self) -> None:
        """Persist memory to disk."""
        self.memory["last_updated"] = datetime.utcnow().isoformat()
        with open(self.memory_path, "w") as f:
            json.dump(self.memory, f, indent=2, default=str)

    def update_pipeline_run(
        self,
        pipeline_name: str,
        status: str,
        duration_minutes: float,
        rows_processed: int,
        credits_used: float,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Record a pipeline run in memory.

        Args:
            pipeline_name: Name of the pipeline (e.g. 'fct_credit_card_daily')
            status: 'success' | 'failure' | 'warning'
            duration_minutes: How long the run took
            rows_processed: Row count processed in this run
            credits_used: Snowflake credits consumed
            error_message: Error message if status is failure
        """
        if pipeline_name not in self.memory["pipelines"]:
            self.memory["pipelines"][pipeline_name] = {
                "runs": [],
                "baseline_duration_p95": None,
                "baseline_row_count_avg": None,
                "failure_count_30d": 0,
            }

        run_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "status": status,
            "duration_minutes": duration_minutes,
            "rows_processed": rows_processed,
            "credits_used": credits_used,
            "error_message": error_message,
        }
        self.memory["pipelines"][pipeline_name]["runs"].append(run_record)

        # Keep only last 90 days of runs
        cutoff = datetime.utcnow() - timedelta(days=90)
        self.memory["pipelines"][pipeline_name]["runs"] = [
            r for r in self.memory["pipelines"][pipeline_name]["runs"]
            if datetime.fromisoformat(r["timestamp"]) > cutoff
        ]

        self._update_baselines(pipeline_name)
        self._save_memory()

    def _update_baselines(self, pipeline_name: str) -> None:
        """Recalculate baseline stats from recent run history."""
        runs = self.memory["pipelines"][pipeline_name]["runs"]
        successful_runs = [r for r in runs if r["status"] == "success"]

        if len(successful_runs) < 5:
            return  # Not enough data yet

        durations = sorted(r["duration_minutes"] for r in successful_runs)
        row_counts = [r["rows_processed"] for r in successful_runs]
        p95_idx = int(len(durations) * 0.95)

        self.memory["pipelines"][pipeline_name]["baseline_duration_p95"] = durations[p95_idx]
        self.memory["pipelines"][pipeline_name]["baseline_row_count_avg"] = (
            sum(row_counts) / len(row_counts)
        )

    # ------------------------------------------------------------------ #
    # Claude analysis                                                      #
    # ------------------------------------------------------------------ #

    def analyze_anomaly(
        self,
        pipeline_name: str,
        current_run: dict,
    ) -> dict:
        """
        Use Claude to analyze whether the current run is anomalous given memory.

        Args:
            pipeline_name: Pipeline to analyze
            current_run: Dict with current run stats

        Returns:
            Dict with: is_anomaly (bool), severity, analysis, recommended_action
        """
        pipeline_memory = self.memory["pipelines"].get(pipeline_name, {})
        recent_runs = pipeline_memory.get("runs", [])[-30:]  # Last 30 runs
        baseline_duration = pipeline_memory.get("baseline_duration_p95")
        baseline_rows = pipeline_memory.get("baseline_row_count_avg")
        past_healing = [
            h for h in self.memory["healing_log"]
            if h.get("pipeline") == pipeline_name
        ][-10:]

        prompt = f"""You are a data pipeline reliability engineer. Analyze this pipeline run
and determine if it's anomalous based on historical memory.

PIPELINE: {pipeline_name}
CURRENT RUN: {json.dumps(current_run, indent=2)}

HISTORICAL BASELINES:
- P95 duration: {baseline_duration} minutes
- Average row count: {baseline_rows}

LAST 30 RUNS (most recent first):
{json.dumps(list(reversed(recent_runs)), indent=2)}

PAST HEALING ACTIONS FOR THIS PIPELINE:
{json.dumps(past_healing, indent=2)}

Analyze and respond in this exact JSON format:
{{
  "is_anomaly": true/false,
  "severity": "low/medium/high/critical",
  "analysis": "2-3 sentence explanation of what you see and why it is or isn't anomalous",
  "root_cause_hypothesis": "Most likely cause based on patterns in memory",
  "recommended_action": "Specific action to take",
  "can_self_heal": true/false,
  "healing_command": "exact command or dbt model to run if can_self_heal is true, else null"
}}"""

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=1024,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract text content from response
        text_content = next(
            (b.text for b in response.content if b.type == "text"), "{}"
        )

        try:
            return json.loads(text_content)
        except json.JSONDecodeError:
            return {
                "is_anomaly": False,
                "severity": "low",
                "analysis": text_content,
                "root_cause_hypothesis": "Unable to parse structured response",
                "recommended_action": "Manual review required",
                "can_self_heal": False,
                "healing_command": None,
            }

    def generate_weekly_digest(self) -> str:
        """
        Ask Claude to generate a weekly digest of pipeline health from memory.

        Returns:
            Markdown-formatted weekly report
        """
        prompt = f"""You are a senior data engineer reviewing pipeline health for the week.
Based on this pipeline memory, write a concise weekly digest.

PIPELINE MEMORY:
{json.dumps(self.memory, indent=2, default=str)}

Write a weekly digest in markdown with these sections:
1. **Overall Health** — one sentence summary
2. **Pipeline Status** — table of each pipeline: name, success rate, avg duration, trend (↑↓→)
3. **Top Issues** — top 3 problems to address, with specific pipeline names
4. **Cost Trends** — credits used vs prior week if data available
5. **Recommended Actions** — top 3 actions ranked by impact

Keep it concise. A data eng manager should read this in 2 minutes."""

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=2048,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        )

        return next(
            (b.text for b in response.content if b.type == "text"),
            "Unable to generate digest."
        )

    def log_healing_action(
        self,
        pipeline_name: str,
        action: str,
        outcome: str,
        credits_saved: float = 0.0,
    ) -> None:
        """
        Record a self-healing action in memory so Claude learns what works.

        Args:
            pipeline_name: Pipeline that was healed
            action: What action was taken
            outcome: 'success' | 'failure' | 'partial'
            credits_saved: Estimated Snowflake credits saved
        """
        self.memory["healing_log"].append({
            "timestamp": datetime.utcnow().isoformat(),
            "pipeline": pipeline_name,
            "action": action,
            "outcome": outcome,
            "credits_saved": credits_saved,
        })
        # Keep last 200 healing actions
        self.memory["healing_log"] = self.memory["healing_log"][-200:]
        self._save_memory()

    def run_check(
        self,
        pipeline_name: str,
        current_stats: dict,
    ) -> dict:
        """
        Main entry point — record a run and analyze for anomalies.

        Args:
            pipeline_name: Name of the pipeline
            current_stats: Dict with duration_minutes, rows_processed,
                          credits_used, status, error_message (optional)

        Returns:
            Analysis result from Claude
        """
        self.update_pipeline_run(
            pipeline_name=pipeline_name,
            status=current_stats.get("status", "success"),
            duration_minutes=current_stats.get("duration_minutes", 0),
            rows_processed=current_stats.get("rows_processed", 0),
            credits_used=current_stats.get("credits_used", 0),
            error_message=current_stats.get("error_message"),
        )

        return self.analyze_anomaly(
            pipeline_name=pipeline_name,
            current_run=current_stats,
        )
