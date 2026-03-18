"""
Demo — Pipeline Memory Agent
-----------------------------
Simulates 30 days of pipeline history, then runs an anomaly check
on a suspicious run. No Snowflake or Airflow connection required.

Run:
    python -m examples.demo
"""

import sys
import json
import random
from pathlib import Path
from datetime import datetime, timedelta

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.memory_agent import PipelineMemoryAgent

DEMO_MEMORY_FILE = Path("demo_pipeline_memory.json")


def simulate_history(agent: PipelineMemoryAgent) -> None:
    """Seed 30 days of normal pipeline history into memory."""
    print("📚 Seeding 30 days of pipeline history...\n")

    pipeline_name = "fct_credit_card_daily"

    for day in range(30, 0, -1):
        # Normal run — 25–35 min, 1.8M–2.2M rows, 0.4–0.6 credits
        duration = random.uniform(25, 35)
        rows = random.randint(1_800_000, 2_200_000)
        credits = random.uniform(0.4, 0.6)

        # Simulate one failure 2 weeks ago
        status = "failure" if day == 15 else "success"
        error = "Snowpipe stalled: upstream payment API timeout" if status == "failure" else None

        agent.update_pipeline_run(
            pipeline_name=pipeline_name,
            status=status,
            duration_minutes=duration,
            rows_processed=rows,
            credits_used=credits,
            error_message=error,
        )

    print(f"✅ Seeded history for '{pipeline_name}'\n")
    print(f"   Baseline P95 duration: "
          f"{agent.memory['pipelines'][pipeline_name].get('baseline_duration_p95', 'N/A')} min")
    print(f"   Baseline avg rows:     "
          f"{agent.memory['pipelines'][pipeline_name].get('baseline_row_count_avg', 'N/A'):,.0f}\n")


def run_anomaly_demo(agent: PipelineMemoryAgent) -> None:
    """Simulate an anomalous run and get Claude's analysis."""
    print("=" * 60)
    print("🚨 ANOMALY CHECK — Suspicious run detected")
    print("=" * 60)

    suspicious_run = {
        "status": "success",
        "duration_minutes": 94.7,    # 3x normal
        "rows_processed": 580_000,   # 70% fewer rows than normal
        "credits_used": 2.8,         # 5x normal
        "error_message": None,
    }

    print("\nCurrent run stats:")
    for k, v in suspicious_run.items():
        print(f"  {k}: {v}")

    print("\n🤖 Asking Claude to analyze with memory context...\n")

    result = agent.analyze_anomaly(
        pipeline_name="fct_credit_card_daily",
        current_run=suspicious_run,
    )

    print("CLAUDE'S ANALYSIS:")
    print("-" * 40)
    print(f"Is anomaly:   {result.get('is_anomaly')}")
    print(f"Severity:     {result.get('severity', '').upper()}")
    print(f"\nAnalysis:\n{result.get('analysis')}")
    print(f"\nRoot cause:   {result.get('root_cause_hypothesis')}")
    print(f"\nAction:       {result.get('recommended_action')}")
    print(f"Can heal:     {result.get('can_self_heal')}")
    if result.get("healing_command"):
        print(f"Heal command: {result.get('healing_command')}")


def run_digest_demo(agent: PipelineMemoryAgent) -> None:
    """Generate a weekly digest from memory."""
    print("\n" + "=" * 60)
    print("📊 WEEKLY PIPELINE DIGEST")
    print("=" * 60 + "\n")

    digest = agent.generate_weekly_digest()
    print(digest)


def main() -> None:
    print("\n" + "=" * 60)
    print("  Pipeline Memory Agent — Demo")
    print("=" * 60 + "\n")

    agent = PipelineMemoryAgent(memory_path=DEMO_MEMORY_FILE)

    # Seed 30 days of history
    simulate_history(agent)

    # Analyze a suspicious run
    run_anomaly_demo(agent)

    # Generate weekly digest
    run_digest_demo(agent)

    print(f"\n💾 Memory saved to: {DEMO_MEMORY_FILE}")
    print("   Run again to see how Claude uses accumulated memory.")


if __name__ == "__main__":
    main()
