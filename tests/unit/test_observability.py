"""Unit tests for observability module."""

import pytest
import json
import os
import time
from unittest.mock import patch

# Add src to path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/lambdas'))


class TestStructuredLogger:
    """Test StructuredLogger output format."""

    def test_info_emits_json_with_required_fields(self, capsys):
        """Should emit JSON with timestamp, level, and message."""
        from shared.observability import StructuredLogger

        logger = StructuredLogger("test")
        logger.info("hello world")

        output = json.loads(capsys.readouterr().err.strip())
        assert output["level"] == "INFO"
        assert output["message"] == "hello world"
        assert "timestamp" in output

    def test_error_level(self, capsys):
        from shared.observability import StructuredLogger

        logger = StructuredLogger("test")
        logger.error("boom", code=500)

        output = json.loads(capsys.readouterr().err.strip())
        assert output["level"] == "ERROR"
        assert output["code"] == 500

    def test_context_included_in_all_entries(self, capsys):
        """Context fields should appear in every subsequent log entry."""
        from shared.observability import StructuredLogger

        logger = StructuredLogger("test")
        logger.set_context(requestId="req-1", agentId="billing")
        logger.info("first")
        logger.warning("second")

        lines = capsys.readouterr().err.strip().split("\n")
        for line in lines:
            entry = json.loads(line)
            assert entry["requestId"] == "req-1"
            assert entry["agentId"] == "billing"

    def test_clear_context(self, capsys):
        from shared.observability import StructuredLogger

        logger = StructuredLogger("test")
        logger.set_context(requestId="req-1")
        logger.clear_context()
        logger.info("after clear")

        output = json.loads(capsys.readouterr().err.strip())
        assert "requestId" not in output

    def test_none_values_excluded(self, capsys):
        """None kwargs should be stripped from output."""
        from shared.observability import StructuredLogger

        logger = StructuredLogger("test")
        logger.info("test", agentId=None, statusCode=200)

        output = json.loads(capsys.readouterr().err.strip())
        assert "agentId" not in output
        assert output["statusCode"] == 200

    def test_kwargs_override_context(self, capsys):
        """Per-call kwargs should override context fields."""
        from shared.observability import StructuredLogger

        logger = StructuredLogger("test")
        logger.set_context(agentId="default")
        logger.info("test", agentId="override")

        output = json.loads(capsys.readouterr().err.strip())
        assert output["agentId"] == "override"


class TestMetricsRecorder:
    """Test MetricsRecorder EMF output."""

    def test_no_output_when_disabled(self, capsys):
        """Should emit nothing when ENABLE_METRICS is false."""
        with patch.dict(os.environ, {"ENABLE_METRICS": "false"}):
            # Re-import to pick up env change
            import importlib
            import shared.observability as obs
            importlib.reload(obs)

            m = obs.MetricsRecorder()
            m.record("RequestCount", 1, "Count")
            m.flush()

            assert capsys.readouterr().err == ""

            # Restore
            importlib.reload(obs)

    def test_emf_structure_when_enabled(self, capsys):
        """Should emit valid EMF blob with correct structure."""
        with patch.dict(os.environ, {"ENABLE_METRICS": "true"}):
            import importlib
            import shared.observability as obs
            importlib.reload(obs)

            m = obs.MetricsRecorder(namespace="TestNS")
            m.set_dimensions(AgentId="billing-agent")
            m.record("RequestCount", 1, "Count")
            m.record("RequestLatency", 234.5, "Milliseconds")
            m.flush()

            output = json.loads(capsys.readouterr().err.strip())

            # Verify EMF metadata
            aws = output["_aws"]
            assert "Timestamp" in aws
            cw = aws["CloudWatchMetrics"][0]
            assert cw["Namespace"] == "TestNS"
            assert cw["Dimensions"] == [["AgentId"], []]
            metric_names = {m["Name"] for m in cw["Metrics"]}
            assert metric_names == {"RequestCount", "RequestLatency"}

            # Verify top-level values
            assert output["AgentId"] == "billing-agent"
            assert output["RequestCount"] == 1
            assert output["RequestLatency"] == 234.5

            importlib.reload(obs)

    def test_duplicate_metric_names_are_aggregated(self, capsys):
        """Recording the same metric name twice should sum values, not overwrite."""
        with patch.dict(os.environ, {"ENABLE_METRICS": "true"}):
            import importlib
            import shared.observability as obs
            importlib.reload(obs)

            m = obs.MetricsRecorder()
            m.record("ErrorCount", 1, "Count")
            m.record("ErrorCount", 1, "Count")
            m.record("RequestCount", 1, "Count")
            m.flush()

            output = json.loads(capsys.readouterr().err.strip())

            # ErrorCount should be 2, not 1
            assert output["ErrorCount"] == 2
            assert output["RequestCount"] == 1

            # Should only have 2 metric definitions, not 3
            metrics = output["_aws"]["CloudWatchMetrics"][0]["Metrics"]
            assert len(metrics) == 2

            importlib.reload(obs)

    def test_flush_clears_metrics(self, capsys):
        """After flush, a second flush should emit nothing."""
        with patch.dict(os.environ, {"ENABLE_METRICS": "true"}):
            import importlib
            import shared.observability as obs
            importlib.reload(obs)

            m = obs.MetricsRecorder()
            m.record("RequestCount", 1, "Count")
            m.flush()
            capsys.readouterr()  # consume first output

            m.flush()
            assert capsys.readouterr().err == ""

            importlib.reload(obs)

    def test_no_dimensions_emits_empty_dimension_set(self, capsys):
        """EMF blob without dimensions should have empty dimension array."""
        with patch.dict(os.environ, {"ENABLE_METRICS": "true"}):
            import importlib
            import shared.observability as obs
            importlib.reload(obs)

            m = obs.MetricsRecorder()
            m.record("SearchCount", 1, "Count")
            m.flush()

            output = json.loads(capsys.readouterr().err.strip())
            assert output["_aws"]["CloudWatchMetrics"][0]["Dimensions"] == [[]]

            importlib.reload(obs)

    def test_properties_included_in_emf(self, capsys):
        """Custom properties should appear in EMF blob."""
        with patch.dict(os.environ, {"ENABLE_METRICS": "true"}):
            import importlib
            import shared.observability as obs
            importlib.reload(obs)

            m = obs.MetricsRecorder()
            m.set_property("requestId", "req-123")
            m.record("RequestCount", 1, "Count")
            m.flush()

            output = json.loads(capsys.readouterr().err.strip())
            assert output["requestId"] == "req-123"

            importlib.reload(obs)


class TestEmitMetric:
    """Test the emit_metric convenience function."""

    def test_emit_metric_produces_isolated_emf(self, capsys):
        """Each emit_metric call should produce its own EMF blob with a single dimension."""
        with patch.dict(os.environ, {"ENABLE_METRICS": "true"}):
            import importlib
            import shared.observability as obs
            importlib.reload(obs)

            obs.emit_metric("AuthFailures", 1, "Count", Reason="EXPIRED_JWT")
            obs.emit_metric("ErrorCount", 1, "Count", ErrorCode="BACKEND_UNREACHABLE")
            obs.emit_metric("ErrorCount", 1, "Count", AgentId="billing")

            lines = capsys.readouterr().err.strip().split("\n")
            assert len(lines) == 3

            blob1 = json.loads(lines[0])
            assert blob1["AuthFailures"] == 1
            assert blob1["Reason"] == "EXPIRED_JWT"
            dims1 = blob1["_aws"]["CloudWatchMetrics"][0]["Dimensions"]
            assert dims1 == [["Reason"], []]
            # Should NOT have AgentId or ErrorCode from other calls
            assert "AgentId" not in blob1
            assert "ErrorCode" not in blob1

            blob2 = json.loads(lines[1])
            assert blob2["ErrorCount"] == 1
            assert blob2["ErrorCode"] == "BACKEND_UNREACHABLE"
            dims2 = blob2["_aws"]["CloudWatchMetrics"][0]["Dimensions"]
            assert dims2 == [["ErrorCode"], []]
            # Should NOT have AgentId or Reason
            assert "AgentId" not in blob2
            assert "Reason" not in blob2

            blob3 = json.loads(lines[2])
            assert blob3["ErrorCount"] == 1
            assert blob3["AgentId"] == "billing"
            dims3 = blob3["_aws"]["CloudWatchMetrics"][0]["Dimensions"]
            assert dims3 == [["AgentId"], []]
            assert "ErrorCode" not in blob3

            importlib.reload(obs)

    def test_emit_metric_noop_when_disabled(self, capsys):
        with patch.dict(os.environ, {"ENABLE_METRICS": "false"}):
            import importlib
            import shared.observability as obs
            importlib.reload(obs)

            obs.emit_metric("AuthFailures", 1, "Count", Reason="test")
            assert capsys.readouterr().err == ""

            importlib.reload(obs)


class TestDimensionIsolation:
    """Test that error-path metrics don't pollute request-level metrics.

    This validates the fix for issue #2: record_error, record_rate_limit_hit,
    and record_auth_failure should emit via isolated emit_metric calls,
    not add dimensions to the shared MetricsRecorder.
    """

    def test_record_error_does_not_pollute_shared_metrics(self, capsys):
        """ErrorCode dimension from record_error should not appear on RequestCount."""
        with patch.dict(os.environ, {"ENABLE_METRICS": "true"}):
            import importlib
            import shared.observability as obs
            importlib.reload(obs)

            tracker = obs.RequestTracker("proxy")
            tracker.start_request(agent_id="billing", operation="message:send")
            tracker.record_error("BACKEND_UNREACHABLE", "connection refused")
            tracker.end_request(status_code=502, error=True)

            lines = capsys.readouterr().err.strip().split("\n")

            # Separate log lines (JSON without _aws) from EMF blobs (JSON with _aws)
            emf_blobs = []
            for line in lines:
                parsed = json.loads(line)
                if "_aws" in parsed:
                    emf_blobs.append(parsed)

            # Should have 4 EMF blobs:
            #   1. ErrorCount by ErrorCode (from record_error)
            #   2. ErrorCount by AgentId (from record_error)
            #   3. end_request by AgentId (primary flush)
            #   4. end_request by Operation (second blob)
            assert len(emf_blobs) == 4

            # Find the end_request blob by AgentId (has RequestCount + AgentId)
            request_blob = next(b for b in emf_blobs if "RequestCount" in b and b.get("AgentId") == "billing")
            # It should NOT have ErrorCode or Operation dimension
            assert "ErrorCode" not in request_blob
            dims = request_blob["_aws"]["CloudWatchMetrics"][0]["Dimensions"]
            assert dims == [["AgentId"], []]

            # Find the end_request blob by Operation
            op_blob = next(b for b in emf_blobs if "RequestCount" in b and b.get("Operation") == "message:send")
            assert "ErrorCode" not in op_blob
            assert "AgentId" not in op_blob
            dims_op = op_blob["_aws"]["CloudWatchMetrics"][0]["Dimensions"]
            assert dims_op == [["Operation"], []]

            # Find the record_error blob by ErrorCode
            error_code_blob = next(b for b in emf_blobs if b.get("ErrorCode") == "BACKEND_UNREACHABLE")
            assert error_code_blob["ErrorCount"] == 1
            assert "AgentId" not in error_code_blob
            # ErrorCode emit suppresses dimensionless to avoid inflating
            # the error-rate alarm (the AgentId emit provides the
            # dimensionless copy instead).
            dims_ec = error_code_blob["_aws"]["CloudWatchMetrics"][0]["Dimensions"]
            assert dims_ec == [["ErrorCode"]]

            # Find the record_error blob by AgentId (ErrorCount only, no RequestCount)
            error_agent_blob = next(b for b in emf_blobs if "ErrorCount" in b and b.get("AgentId") == "billing" and "RequestCount" not in b)
            assert error_agent_blob["ErrorCount"] == 1
            assert "ErrorCode" not in error_agent_blob
            # AgentId emit keeps dimensionless (primary source for alarm)
            dims_ea = error_agent_blob["_aws"]["CloudWatchMetrics"][0]["Dimensions"]
            assert dims_ea == [["AgentId"], []]

            importlib.reload(obs)

    def test_record_rate_limit_does_not_pollute_shared_metrics(self, capsys):
        """UserId dimension from record_rate_limit_hit should not appear on RequestCount."""
        with patch.dict(os.environ, {"ENABLE_METRICS": "true"}):
            import importlib
            import shared.observability as obs
            importlib.reload(obs)

            tracker = obs.RequestTracker("proxy")
            tracker.start_request(agent_id="billing", user_id="user-123")
            tracker.record_rate_limit_hit()

            lines = capsys.readouterr().err.strip().split("\n")
            emf_blobs = [json.loads(l) for l in lines if "_aws" in l]

            # Should have 2 separate rate limit blobs: one by UserId, one by AgentId
            rl_user_blob = next(b for b in emf_blobs if "RateLimitExceeded" in b and "UserId" in b)
            assert rl_user_blob["UserId"] == "user-123"
            assert "AgentId" not in rl_user_blob
            # UserId emit keeps dimensionless (alarm source)
            dims_user = rl_user_blob["_aws"]["CloudWatchMetrics"][0]["Dimensions"]
            assert dims_user == [["UserId"], []]

            rl_agent_blob = next(b for b in emf_blobs if "RateLimitExceeded" in b and "AgentId" in b)
            assert rl_agent_blob["AgentId"] == "billing"
            assert "UserId" not in rl_agent_blob
            # AgentId emit suppresses dimensionless to avoid double-counting
            dims_agent = rl_agent_blob["_aws"]["CloudWatchMetrics"][0]["Dimensions"]
            assert dims_agent == [["AgentId"]]

            # Shared recorder should NOT have UserId or extra dimensions
            assert "UserId" not in tracker.metrics._dimensions

            importlib.reload(obs)

    def test_record_auth_failure_does_not_pollute_shared_metrics(self, capsys):
        """Reason dimension from record_auth_failure should not appear on RequestCount."""
        with patch.dict(os.environ, {"ENABLE_METRICS": "true"}):
            import importlib
            import shared.observability as obs
            importlib.reload(obs)

            tracker = obs.RequestTracker("authorizer")
            tracker.start_request()
            tracker.record_auth_failure("EXPIRED_JWT")

            lines = capsys.readouterr().err.strip().split("\n")
            emf_blobs = [json.loads(l) for l in lines if "_aws" in l]

            auth_blob = next(b for b in emf_blobs if "AuthFailures" in b)
            assert auth_blob["Reason"] == "EXPIRED_JWT"

            # Shared recorder should NOT have Reason
            assert "Reason" not in tracker.metrics._dimensions

            importlib.reload(obs)


class TestLogHelpers:
    """Test log_info and log_error helpers."""

    def test_log_info_format(self, capsys):
        from shared.observability import log_info

        log_info("discovery complete", agentCount=5)

        output = json.loads(capsys.readouterr().err.strip())
        assert output["level"] == "INFO"
        assert output["message"] == "discovery complete"
        assert output["agentCount"] == 5

    def test_log_error_format(self, capsys):
        from shared.observability import log_error

        log_error("something broke", errorCode="INTERNAL_ERROR")

        output = json.loads(capsys.readouterr().err.strip())
        assert output["level"] == "ERROR"
        assert output["errorCode"] == "INTERNAL_ERROR"
