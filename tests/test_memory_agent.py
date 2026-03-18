"""
Unit tests for PipelineMemoryAgent.
Tests memory persistence, baseline calculation, and Claude integration.
"""

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.memory_agent import PipelineMemoryAgent

TEST_MEMORY_FILE = Path("test_memory.json")


class TestMemoryPersistence(unittest.TestCase):
    """Tests for memory load/save behavior."""

    def setUp(self):
        if TEST_MEMORY_FILE.exists():
            TEST_MEMORY_FILE.unlink()
        self.agent = PipelineMemoryAgent(memory_path=TEST_MEMORY_FILE)

    def tearDown(self):
        if TEST_MEMORY_FILE.exists():
            TEST_MEMORY_FILE.unlink()

    def test_fresh_memory_structure(self):
        """New memory should have the correct empty structure."""
        self.assertIn("pipelines", self.agent.memory)
        self.assertIn("anomaly_patterns", self.agent.memory)
        self.assertIn("healing_log", self.agent.memory)
        self.assertEqual(self.agent.memory["pipelines"], {})

    def test_pipeline_run_recorded(self):
        """Pipeline run should be persisted and reloadable."""
        self.agent.update_pipeline_run(
            pipeline_name="fct_transactions",
            status="success",
            duration_minutes=30.5,
            rows_processed=2_000_000,
            credits_used=0.5,
        )

        # Reload from disk
        reloaded = PipelineMemoryAgent(memory_path=TEST_MEMORY_FILE)
        self.assertIn("fct_transactions", reloaded.memory["pipelines"])
        runs = reloaded.memory["pipelines"]["fct_transactions"]["runs"]
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["status"], "success")
        self.assertEqual(runs[0]["duration_minutes"], 30.5)

    def test_multiple_runs_accumulate(self):
        """Multiple runs should all be recorded."""
        for i in range(5):
            self.agent.update_pipeline_run(
                pipeline_name="fct_transactions",
                status="success",
                duration_minutes=30 + i,
                rows_processed=2_000_000,
                credits_used=0.5,
            )
        runs = self.agent.memory["pipelines"]["fct_transactions"]["runs"]
        self.assertEqual(len(runs), 5)

    def test_healing_log_recorded(self):
        """Healing actions should be persisted."""
        self.agent.log_healing_action(
            pipeline_name="fct_transactions",
            action="trigger_dbt_run fct_transactions",
            outcome="success",
            credits_saved=0.2,
        )
        self.assertEqual(len(self.agent.memory["healing_log"]), 1)
        self.assertEqual(self.agent.memory["healing_log"][0]["outcome"], "success")


class TestBaselineCalculation(unittest.TestCase):
    """Tests for baseline statistics calculation."""

    def setUp(self):
        if TEST_MEMORY_FILE.exists():
            TEST_MEMORY_FILE.unlink()
        self.agent = PipelineMemoryAgent(memory_path=TEST_MEMORY_FILE)

    def tearDown(self):
        if TEST_MEMORY_FILE.exists():
            TEST_MEMORY_FILE.unlink()

    def test_baseline_not_set_with_few_runs(self):
        """Baseline should not be set with fewer than 5 runs."""
        for i in range(4):
            self.agent.update_pipeline_run(
                pipeline_name="fct_transactions",
                status="success",
                duration_minutes=30,
                rows_processed=2_000_000,
                credits_used=0.5,
            )
        baseline = self.agent.memory["pipelines"]["fct_transactions"]["baseline_duration_p95"]
        self.assertIsNone(baseline)

    def test_baseline_set_after_five_runs(self):
        """Baseline should be calculated after 5+ successful runs."""
        for duration in [28, 30, 32, 29, 31]:
            self.agent.update_pipeline_run(
                pipeline_name="fct_transactions",
                status="success",
                duration_minutes=duration,
                rows_processed=2_000_000,
                credits_used=0.5,
            )
        baseline = self.agent.memory["pipelines"]["fct_transactions"]["baseline_duration_p95"]
        self.assertIsNotNone(baseline)
        self.assertGreater(baseline, 28)

    def test_failed_runs_excluded_from_baseline(self):
        """Failed runs should not influence baseline duration."""
        for _ in range(4):
            self.agent.update_pipeline_run(
                pipeline_name="fct_transactions",
                status="success",
                duration_minutes=30,
                rows_processed=2_000_000,
                credits_used=0.5,
            )
        # Add a failure with very long duration
        self.agent.update_pipeline_run(
            pipeline_name="fct_transactions",
            status="failure",
            duration_minutes=300,
            rows_processed=0,
            credits_used=5.0,
            error_message="Timeout",
        )
        # Baseline should not be 300
        avg_rows = self.agent.memory["pipelines"]["fct_transactions"]["baseline_row_count_avg"]
        self.assertIsNone(avg_rows)  # Still < 5 successful runs


class TestClaudeIntegration(unittest.TestCase):
    """Tests for Claude API integration with mocked responses."""

    def setUp(self):
        if TEST_MEMORY_FILE.exists():
            TEST_MEMORY_FILE.unlink()
        self.agent = PipelineMemoryAgent(memory_path=TEST_MEMORY_FILE)

    def tearDown(self):
        if TEST_MEMORY_FILE.exists():
            TEST_MEMORY_FILE.unlink()

    @patch("src.memory_agent.anthropic.Anthropic")
    def test_analyze_anomaly_returns_structured_result(self, mock_anthropic_class):
        """analyze_anomaly should return parsed JSON from Claude."""
        mock_response = MagicMock()
        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = json.dumps({
            "is_anomaly": True,
            "severity": "high",
            "analysis": "Duration 3x above baseline.",
            "root_cause_hypothesis": "Full table scan on fct_transactions.",
            "recommended_action": "Add clustering key on event_date.",
            "can_self_heal": False,
            "healing_command": None,
        })
        mock_response.content = [mock_block]
        mock_anthropic_class.return_value.messages.create.return_value = mock_response

        agent = PipelineMemoryAgent(memory_path=TEST_MEMORY_FILE)

        result = agent.analyze_anomaly(
            pipeline_name="fct_transactions",
            current_run={
                "status": "success",
                "duration_minutes": 95,
                "rows_processed": 500_000,
                "credits_used": 2.8,
            },
        )

        self.assertTrue(result["is_anomaly"])
        self.assertEqual(result["severity"], "high")
        self.assertFalse(result["can_self_heal"])

    @patch("src.memory_agent.anthropic.Anthropic")
    def test_analyze_anomaly_handles_malformed_json(self, mock_anthropic_class):
        """analyze_anomaly should not crash on malformed Claude response."""
        mock_response = MagicMock()
        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = "This is not JSON"
        mock_response.content = [mock_block]
        mock_anthropic_class.return_value.messages.create.return_value = mock_response

        agent = PipelineMemoryAgent(memory_path=TEST_MEMORY_FILE)

        result = agent.analyze_anomaly(
            pipeline_name="fct_transactions",
            current_run={"status": "success", "duration_minutes": 30},
        )

        # Should return safe fallback
        self.assertIn("is_anomaly", result)
        self.assertFalse(result["is_anomaly"])


if __name__ == "__main__":
    unittest.main()
