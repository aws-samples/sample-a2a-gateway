"""
Observability utilities for A2A Gateway.

Provides:
- Structured logging (human-readable JSON)
- CloudWatch metrics via EMF (Embedded Metric Format)
- Request context tracking

Metrics are opt-in via ENABLE_METRICS environment variable.
"""

import os
import sys
import json
import time
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from contextlib import contextmanager


# Check if metrics are enabled
METRICS_ENABLED = os.environ.get('ENABLE_METRICS', 'false').lower() == 'true'
METRICS_NAMESPACE = os.environ.get('METRICS_NAMESPACE', 'A2AGateway')


class StructuredLogger:
    """
    Human-readable structured logger.
    
    Outputs JSON logs that are easy to read and query in CloudWatch Logs Insights.
    """
    
    def __init__(self, name: str, level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        self._context: Dict[str, Any] = {}
    
    def set_context(self, **kwargs) -> None:
        """Set persistent context fields included in all log entries."""
        self._context.update(kwargs)
    
    def clear_context(self) -> None:
        """Clear all context fields."""
        self._context = {}
    
    def _log(self, level: str, message: str, **kwargs) -> None:
        """Internal log method."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
            **self._context,
            **kwargs
        }
        # Remove None values for cleaner output
        entry = {k: v for k, v in entry.items() if v is not None}
        print(json.dumps(entry), file=sys.stderr, flush=True)
    
    def info(self, message: str, **kwargs) -> None:
        self._log("INFO", message, **kwargs)
    
    def warning(self, message: str, **kwargs) -> None:
        self._log("WARNING", message, **kwargs)
    
    def error(self, message: str, **kwargs) -> None:
        self._log("ERROR", message, **kwargs)
    
    def debug(self, message: str, **kwargs) -> None:
        self._log("DEBUG", message, **kwargs)


class MetricsRecorder:
    """
    CloudWatch metrics recorder using EMF (Embedded Metric Format).
    
    Collects metrics during a request and flushes them as a single EMF blob.
    This keeps logs readable while still getting CloudWatch metrics.
    
    IMPORTANT: Each recorder should carry at most ONE dimension to maintain
    the single-dimension invariant. Use separate recorders (or emit_metric
    calls) for different dimensions.
    
    Usage:
        metrics = MetricsRecorder()
        metrics.set_dimensions(AgentId="my-agent")
        metrics.record("RequestLatency", 234, "Milliseconds")
        metrics.record("RequestCount", 1, "Count")
        metrics.flush()  # Emits EMF to CloudWatch
    """
    
    def __init__(self, namespace: str = None):
        self.namespace = namespace or METRICS_NAMESPACE
        self._dimensions: Dict[str, str] = {}
        self._metrics: List[Dict[str, Any]] = []
        self._properties: Dict[str, Any] = {}
    
    def set_dimensions(self, **kwargs) -> None:
        """Set dimensions for all metrics in this batch."""
        self._dimensions.update({k: str(v) for k, v in kwargs.items() if v is not None})
    
    def set_property(self, key: str, value: Any) -> None:
        """Set a property (non-metric data) to include in the EMF blob."""
        self._properties[key] = value
    
    def record(self, name: str, value: float, unit: str = "Count") -> None:
        """
        Record a metric value.
        
        Args:
            name: Metric name
            value: Metric value
            unit: CloudWatch unit (Count, Milliseconds, Seconds, Bytes, etc.)
        """
        if not METRICS_ENABLED:
            return
        
        self._metrics.append({
            "Name": name,
            "Value": value,
            "Unit": unit
        })
    
    def flush(self, include_dimensionless: bool = True) -> None:
        """
        Flush all recorded metrics as an EMF blob.

        This prints a specially formatted JSON that CloudWatch automatically
        parses into metrics. Called once at the end of a request.

        Metrics with the same name are aggregated (summed) to avoid
        duplicate top-level keys overwriting each other in the EMF blob.

        Emits metrics under both the dimensioned set AND a dimensionless set
        so that CloudWatch alarms (which can't use SEARCH) can query the
        aggregate metrics directly.

        Args:
            include_dimensionless: If True (default), emit both dimensioned
                and dimensionless metric entries. Set to False when another
                code path already produces the dimensionless copy and a
                duplicate would inflate alarm counts.
        """
        if not METRICS_ENABLED or not self._metrics:
            return

        # Aggregate metrics with the same name (sum values, keep last unit)
        aggregated: Dict[str, Dict[str, Any]] = {}
        for m in self._metrics:
            name = m["Name"]
            if name in aggregated:
                aggregated[name]["Value"] += m["Value"]
            else:
                aggregated[name] = {"Name": name, "Value": m["Value"], "Unit": m["Unit"]}

        metrics_list = list(aggregated.values())

        # Build dimension keys list
        dimension_keys = list(self._dimensions.keys()) if self._dimensions else []

        # Build EMF Dimensions array.
        # When include_dimensionless is True (default): include both the
        # dimensioned set and an empty set [] so CloudWatch creates both
        # dimensioned and dimensionless metric entries from a single blob.
        # When False: only emit the dimensioned set (no dimensionless copy).
        if dimension_keys and include_dimensionless:
            dimension_sets = [dimension_keys, []]
        elif dimension_keys:
            dimension_sets = [dimension_keys]
        else:
            dimension_sets = [[]]

        # Build EMF structure
        emf = {
            "_aws": {
                "Timestamp": int(time.time() * 1000),
                "CloudWatchMetrics": [{
                    "Namespace": self.namespace,
                    "Dimensions": dimension_sets,
                    "Metrics": [{"Name": m["Name"], "Unit": m["Unit"]} for m in metrics_list]
                }]
            }
        }

        # Add dimensions as top-level properties (required by EMF)
        emf.update(self._dimensions)

        # Add metric values as top-level properties
        for metric in metrics_list:
            emf[metric["Name"]] = metric["Value"]

        # Add custom properties
        emf.update(self._properties)

        # Emit EMF blob
        print(json.dumps(emf), file=sys.stderr, flush=True)

        # Clear for next batch
        self._metrics = []
        self._properties = {}


class RequestTracker:
    """
    Tracks request timing and emits metrics.
    
    Emits separate EMF blobs per dimension to avoid multi-dimension pollution.
    
    Usage:
        tracker = RequestTracker("proxy")
        tracker.start_request(agent_id="my-agent", operation="message:send", user_id="user-123")
        
        # ... do work ...
        tracker.record_backend_latency(150)
        
        tracker.end_request(status_code=200)  # Automatically emits metrics
    """
    
    def __init__(self, lambda_name: str):
        self.lambda_name = lambda_name
        self.logger = StructuredLogger(lambda_name)
        self.metrics = MetricsRecorder()
        self._start_time: Optional[float] = None
        self._agent_id: Optional[str] = None
        self._operation: Optional[str] = None
        self._user_id: Optional[str] = None
        self._backend_latency_ms: Optional[float] = None
        self._is_streaming: bool = False
    
    def start_request(
        self,
        agent_id: str = None,
        operation: str = None,
        user_id: str = None,
        request_id: str = None,
        is_streaming: bool = False
    ) -> None:
        """Start tracking a request."""
        self._start_time = time.time()
        self._agent_id = agent_id
        self._operation = operation
        self._user_id = user_id
        self._is_streaming = is_streaming
        
        # Set logger context
        self.logger.set_context(
            requestId=request_id,
            agentId=agent_id,
            operation=operation,
            userId=user_id
        )
        
        # Only set a single dimension on the shared recorder.
        # If both agent_id and operation are present, we emit
        # the operation dimension via a separate emit_metric call
        # in end_request to keep each EMF blob single-dimensioned.
        if agent_id:
            self.metrics.set_dimensions(AgentId=agent_id)
        elif operation:
            self.metrics.set_dimensions(Operation=operation)
        
        self.logger.info(
            f"Request started: {operation or 'unknown'}",
            isStreaming=is_streaming
        )
    
    def record_backend_latency(self, latency_ms: float) -> None:
        """Record backend call latency (stored, emitted in end_request)."""
        self._backend_latency_ms = latency_ms
    
    def record_error(self, error_code: str, message: str = None) -> None:
        """Record an error occurrence. Emits in isolated metrics to avoid dimension pollution."""
        self.logger.error(f"Request error: {error_code}", errorCode=error_code, errorMessage=message)
        # ErrorCode emit suppresses dimensionless — the AgentId emit (or
        # end_request's flush) provides the dimensionless copy.
        emit_metric("ErrorCount", 1, "Count",
                     include_dimensionless=False, ErrorCode=error_code)
        if self._agent_id:
            emit_metric("ErrorCount", 1, "Count", AgentId=self._agent_id)
    
    def record_rate_limit_hit(self) -> None:
        """Record a rate limit hit. Emits in isolated metrics to avoid dimension pollution."""
        self.logger.warning("Rate limit exceeded", userId=self._user_id, agentId=self._agent_id)
        # UserId emit keeps dimensionless (alarm source).
        # AgentId emit suppresses it to avoid double-counting.
        emit_metric("RateLimitExceeded", 1, "Count",
                     UserId=self._user_id or "unknown")
        if self._agent_id:
            emit_metric("RateLimitExceeded", 1, "Count",
                         include_dimensionless=False,
                         AgentId=self._agent_id)
    
    def record_auth_failure(self, reason: str) -> None:
        """Record an authentication failure. Emits in an isolated metric to avoid dimension pollution."""
        self.logger.warning(f"Auth failure: {reason}", reason=reason)
        emit_metric("AuthFailures", 1, "Count", Reason=reason)
    
    def end_request(self, status_code: int = 200, error: bool = False) -> None:
        """
        End request tracking and emit metrics.
        
        Emits separate EMF blobs per dimension to maintain single-dimension
        invariant. The shared self.metrics recorder carries at most one
        dimension (AgentId). If an Operation was also provided, a second
        blob is emitted via emit_metric.
        
        Args:
            status_code: HTTP status code
            error: Whether the request resulted in an error
        """
        if self._start_time is None:
            return
        
        latency_ms = (time.time() - self._start_time) * 1000
        
        # Log completion
        self.logger.info(
            f"Request completed: {status_code}",
            statusCode=status_code,
            latencyMs=round(latency_ms, 2),
            backendLatencyMs=round(self._backend_latency_ms, 2) if self._backend_latency_ms else None,
            isStreaming=self._is_streaming
        )
        
        # Record metrics on the shared recorder (single dimension: AgentId or Operation or none)
        self.metrics.record("RequestCount", 1, "Count")
        self.metrics.record("RequestLatency", latency_ms, "Milliseconds")
        
        if self._backend_latency_ms is not None:
            self.metrics.record("BackendLatency", self._backend_latency_ms, "Milliseconds")
        
        if self._is_streaming:
            self.metrics.record("StreamingRequests", 1, "Count")
            self.metrics.record("StreamDuration", latency_ms / 1000, "Seconds")
        
        if error:
            self.metrics.record("ErrorCount", 1, "Count")
        
        # Flush the primary blob (AgentId dimension, or Operation if no AgentId, or dimensionless)
        self.metrics.flush()
        
        # If both AgentId and Operation were provided, emit a second blob for Operation
        if self._agent_id and self._operation:
            op_metrics = MetricsRecorder()
            op_metrics.set_dimensions(Operation=self._operation)
            op_metrics.record("RequestCount", 1, "Count")
            op_metrics.record("RequestLatency", latency_ms, "Milliseconds")
            if self._is_streaming:
                op_metrics.record("StreamingRequests", 1, "Count")
                op_metrics.record("StreamDuration", latency_ms / 1000, "Seconds")
            if error:
                op_metrics.record("ErrorCount", 1, "Count")
            op_metrics.flush()
        
        # Clear state
        self._start_time = None
        self.logger.clear_context()


@contextmanager
def track_request(
    lambda_name: str,
    agent_id: str = None,
    operation: str = None,
    user_id: str = None,
    request_id: str = None,
    is_streaming: bool = False
):
    """
    Context manager for request tracking.
    
    Usage:
        with track_request("proxy", agent_id="my-agent", operation="message:send") as tracker:
            # ... do work ...
            tracker.record_backend_latency(150)
        # Metrics automatically emitted on exit
    """
    tracker = RequestTracker(lambda_name)
    tracker.start_request(
        agent_id=agent_id,
        operation=operation,
        user_id=user_id,
        request_id=request_id,
        is_streaming=is_streaming
    )
    
    error = False
    status_code = 200
    
    try:
        yield tracker
    except Exception as e:
        error = True
        status_code = 500
        tracker.record_error("INTERNAL_ERROR", str(e))
        raise
    finally:
        tracker.end_request(status_code=status_code, error=error)


# Convenience functions for simple metric recording
def emit_metric(name: str, value: float, unit: str = "Count",
                include_dimensionless: bool = True, **dimensions) -> None:
    """
    Emit a single metric immediately.
    
    For one-off metrics outside of request tracking.

    Args:
        name: Metric name
        value: Metric value
        unit: CloudWatch unit
        include_dimensionless: If True (default), the EMF blob includes a
            dimensionless copy alongside the dimensioned entry. Set to False
            when another code path already produces the dimensionless copy.
    """
    if not METRICS_ENABLED:
        return
    
    metrics = MetricsRecorder()
    metrics.set_dimensions(**dimensions)
    metrics.record(name, value, unit)
    metrics.flush(include_dimensionless=include_dimensionless)


def log_info(message: str, **kwargs) -> None:
    """Simple structured log helper."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": "INFO",
        "message": message,
        **kwargs
    }
    print(json.dumps(entry), file=sys.stderr, flush=True)


def log_error(message: str, **kwargs) -> None:
    """Simple structured error log helper."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": "ERROR",
        "message": message,
        **kwargs
    }
    print(json.dumps(entry), file=sys.stderr, flush=True)
