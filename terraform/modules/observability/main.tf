# A2A Gateway Observability Module
#
# Creates CloudWatch dashboard and alarms for monitoring the gateway.
# Metrics are emitted by Lambda functions using EMF (Embedded Metric Format).

locals {
  namespace = var.metrics_namespace
  
  # Common alarm dimensions
  alarm_actions = var.enable_alarms_sns ? [aws_sns_topic.alarms[0].arn] : []
}

# ─────────────────────────────────────────────────────────────────────────────
# SNS Topic for Alarms (Optional)
# ─────────────────────────────────────────────────────────────────────────────

resource "aws_sns_topic" "alarms" {
  count = var.enable_alarms_sns ? 1 : 0
  name  = "${var.project_name}-${var.environment}-alarms"
}

resource "aws_sns_topic_subscription" "alarm_email" {
  count     = var.enable_alarms_sns && var.alarm_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alarms[0].arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

# ─────────────────────────────────────────────────────────────────────────────
# CloudWatch Dashboard
# ─────────────────────────────────────────────────────────────────────────────

resource "aws_cloudwatch_dashboard" "gateway" {
  dashboard_name = "${var.project_name}-${var.environment}"
  
  dashboard_body = jsonencode({
    widgets = [
      # ─── Row 1: Health Overview ───────────────────────────────────────────
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 6
        height = 4
        properties = {
          title  = "Total Requests"
          region = var.aws_region
          stat   = "Sum"
          metrics = [
            [local.namespace, "RequestCount", { label = "Requests" }]
          ]
          view = "singleValue"
          setPeriodToTimeRange = true
        }
      },
      {
        type   = "metric"
        x      = 6
        y      = 0
        width  = 6
        height = 4
        properties = {
          title  = "Error Rate %"
          region = var.aws_region
          period = 300
          metrics = [
            [{ expression = "IF(requests > 0, errors / requests * 100, 0)", label = "Error Rate", id = "rate" }],
            [{ expression = "SUM(SEARCH('{${local.namespace},AgentId} MetricName=\"ErrorCount\"', 'Sum', 300))", id = "errors", visible = false }],
            [{ expression = "SUM(SEARCH('{${local.namespace},AgentId} MetricName=\"RequestCount\"', 'Sum', 300))", id = "requests", visible = false }]
          ]
          view = "singleValue"
          yAxis = {
            left = { min = 0, max = 100 }
          }
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 6
        height = 4
        properties = {
          title  = "Avg Latency (ms)"
          region = var.aws_region
          stat   = "Average"
          metrics = [
            [local.namespace, "RequestLatency", { label = "Avg" }]
          ]
          view = "singleValue"
          setPeriodToTimeRange = true
        }
      },
      {
        type   = "metric"
        x      = 18
        y      = 0
        width  = 6
        height = 4
        properties = {
          title  = "Active Alarms"
          region = var.aws_region
          metrics = [
            ["AWS/CloudWatch", "NumberOfAlarmsInAlarmState", { label = "In Alarm" }]
          ]
          view = "singleValue"
          period = 60
        }
      },

      # ─── Row 2: Request Volume & Latency ──────────────────────────────────
      {
        type   = "metric"
        x      = 0
        y      = 4
        width  = 12
        height = 6
        properties = {
          title  = "Requests by Agent"
          region = var.aws_region
          period = 60
          metrics = [
            [{ expression = "SEARCH('{${local.namespace},AgentId} MetricName=\"RequestCount\"', 'Sum', 60)", id = "req" }]
          ]
          view = "timeSeries"
          stacked = true
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 4
        width  = 12
        height = 6
        properties = {
          title  = "Latency Percentiles"
          region = var.aws_region
          period = 60
          metrics = [
            [{ expression = "AVG(SEARCH('{${local.namespace},AgentId} MetricName=\"RequestLatency\"', 'p50', 60))", label = "P50", id = "p50" }],
            [{ expression = "AVG(SEARCH('{${local.namespace},AgentId} MetricName=\"RequestLatency\"', 'p95', 60))", label = "P95", id = "p95" }],
            [{ expression = "AVG(SEARCH('{${local.namespace},AgentId} MetricName=\"RequestLatency\"', 'p99', 60))", label = "P99", id = "p99" }]
          ]
          view = "timeSeries"
          yAxis = {
            left = { label = "Milliseconds", min = 0 }
          }
        }
      },

      # ─── Row 3: Errors ────────────────────────────────────────────────────
      {
        type   = "metric"
        x      = 0
        y      = 10
        width  = 12
        height = 6
        properties = {
          title  = "Errors by Agent"
          region = var.aws_region
          period = 60
          metrics = [
            [{ expression = "SEARCH('{${local.namespace},AgentId} MetricName=\"ErrorCount\"', 'Sum', 60)", id = "err" }]
          ]
          view = "timeSeries"
          stacked = true
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 10
        width  = 12
        height = 6
        properties = {
          title  = "Errors by Type"
          region = var.aws_region
          period = 60
          metrics = [
            [{ expression = "SEARCH('{${local.namespace},ErrorCode} MetricName=\"ErrorCount\"', 'Sum', 60)", id = "errtype" }]
          ]
          view = "timeSeries"
          stacked = true
        }
      },

      # ─── Row 4: Backend Performance ───────────────────────────────────────
      {
        type   = "metric"
        x      = 0
        y      = 16
        width  = 12
        height = 6
        properties = {
          title  = "Backend Latency by Agent"
          region = var.aws_region
          period = 60
          metrics = [
            [{ expression = "SEARCH('{${local.namespace},AgentId} MetricName=\"BackendLatency\"', 'p95', 60)", id = "bl" }]
          ]
          view = "timeSeries"
          yAxis = {
            left = { label = "Milliseconds", min = 0 }
          }
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 16
        width  = 12
        height = 6
        properties = {
          title  = "Gateway vs Backend Latency"
          region = var.aws_region
          period = 60
          metrics = [
            [{ expression = "AVG(SEARCH('{${local.namespace},AgentId} MetricName=\"RequestLatency\"', 'p95', 60))", label = "Total (Gateway)", id = "gateway" }],
            [{ expression = "AVG(SEARCH('{${local.namespace},AgentId} MetricName=\"BackendLatency\"', 'p95', 60))", label = "Backend Only", id = "backend" }]
          ]
          view = "timeSeries"
          yAxis = {
            left = { label = "Milliseconds", min = 0 }
          }
        }
      },

      # ─── Row 5: Rate Limiting & Auth ──────────────────────────────────────
      {
        type   = "metric"
        x      = 0
        y      = 22
        width  = 12
        height = 6
        properties = {
          title  = "Rate Limit Hits"
          region = var.aws_region
          period = 60
          metrics = [
            [{ expression = "SEARCH('{${local.namespace},UserId} MetricName=\"RateLimitExceeded\"', 'Sum', 60)", id = "rl" }]
          ]
          view = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 22
        width  = 12
        height = 6
        properties = {
          title  = "Auth Failures"
          region = var.aws_region
          stat   = "Sum"
          period = 60
          metrics = [
            [local.namespace, "AuthFailures", { label = "Total" }],
            [{ expression = "SEARCH('{${local.namespace},Reason} MetricName=\"AuthFailures\"', 'Sum', 60)", id = "af" }]
          ]
          view = "timeSeries"
        }
      },

      # ─── Row 6: Operations Breakdown ──────────────────────────────────────
      {
        type   = "metric"
        x      = 0
        y      = 28
        width  = 8
        height = 6
        properties = {
          title  = "Streaming vs Buffered"
          region = var.aws_region
          period = 60
          metrics = [
            [{ expression = "SUM(SEARCH('{${local.namespace},AgentId} MetricName=\"RequestCount\"', 'Sum', 60))", label = "Total Proxied", id = "total" }],
            [{ expression = "SUM(SEARCH('{${local.namespace},AgentId} MetricName=\"StreamingRequests\"', 'Sum', 60))", label = "Streaming", id = "streaming" }],
            [{ expression = "total - streaming", label = "Buffered", id = "buffered" }]
          ]
          view = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 8
        y      = 28
        width  = 8
        height = 6
        properties = {
          title  = "Discovery & Search"
          region = var.aws_region
          stat   = "Sum"
          period = 60
          metrics = [
            [local.namespace, "AgentDiscoveryCount", { label = "Discovery" }],
            [local.namespace, "SearchCount", { label = "Search" }]
          ]
          view = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 16
        y      = 28
        width  = 8
        height = 6
        properties = {
          title  = "Admin Operations"
          region = var.aws_region
          period = 300
          metrics = [
            [{ expression = "SEARCH('{${local.namespace},Operation} MetricName=\"AdminOperations\"', 'Sum', 300)", id = "admin" }]
          ]
          view = "timeSeries"
        }
      },

      # ─── Row 7: Lambda Insights ───────────────────────────────────────────
      {
        type   = "metric"
        x      = 0
        y      = 34
        width  = 12
        height = 6
        properties = {
          title  = "Lambda Invocations"
          region = var.aws_region
          stat   = "Sum"
          period = 60
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", var.proxy_lambda_name, { label = "Proxy" }],
            ["AWS/Lambda", "Invocations", "FunctionName", var.authorizer_lambda_name, { label = "Authorizer" }],
            ["AWS/Lambda", "Invocations", "FunctionName", var.registry_lambda_name, { label = "Registry" }],
            ["AWS/Lambda", "Invocations", "FunctionName", var.search_lambda_name, { label = "Search" }],
            ["AWS/Lambda", "Invocations", "FunctionName", var.admin_lambda_name, { label = "Admin" }]
          ]
          view = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 34
        width  = 12
        height = 6
        properties = {
          title  = "Lambda Errors"
          region = var.aws_region
          stat   = "Sum"
          period = 60
          metrics = [
            ["AWS/Lambda", "Errors", "FunctionName", var.proxy_lambda_name, { label = "Proxy" }],
            ["AWS/Lambda", "Errors", "FunctionName", var.authorizer_lambda_name, { label = "Authorizer" }],
            ["AWS/Lambda", "Errors", "FunctionName", var.registry_lambda_name, { label = "Registry" }],
            ["AWS/Lambda", "Errors", "FunctionName", var.search_lambda_name, { label = "Search" }],
            ["AWS/Lambda", "Errors", "FunctionName", var.admin_lambda_name, { label = "Admin" }]
          ]
          view = "timeSeries"
        }
      }
    ]
  })
}


# ─────────────────────────────────────────────────────────────────────────────
# CloudWatch Alarms
# ─────────────────────────────────────────────────────────────────────────────

# High Error Rate Alarm
resource "aws_cloudwatch_metric_alarm" "high_error_rate" {
  alarm_name          = "${var.project_name}-${var.environment}-high-error-rate"
  alarm_description   = "Error rate exceeds ${var.error_rate_threshold_percent}%"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  threshold           = var.error_rate_threshold_percent
  treat_missing_data  = "notBreaching"
  
  metric_query {
    id          = "error_rate"
    expression  = "IF(requests > 0, (errors / requests) * 100, 0)"
    label       = "Error Rate %"
    return_data = true
  }
  
  metric_query {
    id = "errors"
    metric {
      metric_name = "ErrorCount"
      namespace   = local.namespace
      period      = 300
      stat        = "Sum"
    }
  }
  
  metric_query {
    id = "requests"
    metric {
      metric_name = "RequestCount"
      namespace   = local.namespace
      period      = 300
      stat        = "Sum"
    }
  }
  
  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

# High Latency Alarm
resource "aws_cloudwatch_metric_alarm" "high_latency" {
  alarm_name          = "${var.project_name}-${var.environment}-high-latency"
  alarm_description   = "P95 latency exceeds ${var.latency_threshold_ms}ms"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "RequestLatency"
  namespace           = local.namespace
  period              = 300
  extended_statistic  = "p95"
  threshold           = var.latency_threshold_ms
  treat_missing_data  = "notBreaching"
  
  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

# Backend Unreachable Alarm
resource "aws_cloudwatch_metric_alarm" "backend_unreachable" {
  alarm_name          = "${var.project_name}-${var.environment}-backend-unreachable"
  alarm_description   = "Backend unreachable errors exceed ${var.backend_error_threshold} in 5 minutes"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ErrorCount"
  namespace           = local.namespace
  period              = 300
  statistic           = "Sum"
  threshold           = var.backend_error_threshold
  treat_missing_data  = "notBreaching"
  
  dimensions = {
    ErrorCode = "BACKEND_UNREACHABLE"
  }
  
  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

# Auth Failure Spike Alarm
resource "aws_cloudwatch_metric_alarm" "auth_failure_spike" {
  alarm_name          = "${var.project_name}-${var.environment}-auth-failure-spike"
  alarm_description   = "Auth failures exceed ${var.auth_failure_threshold} in 5 minutes"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "AuthFailures"
  namespace           = local.namespace
  period              = 300
  statistic           = "Sum"
  threshold           = var.auth_failure_threshold
  treat_missing_data  = "notBreaching"
  
  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

# Rate Limit Exhaustion Alarm
resource "aws_cloudwatch_metric_alarm" "rate_limit_exhaustion" {
  alarm_name          = "${var.project_name}-${var.environment}-rate-limit-exhaustion"
  alarm_description   = "Rate limit hits exceed ${var.rate_limit_threshold} in 5 minutes"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "RateLimitExceeded"
  namespace           = local.namespace
  period              = 300
  statistic           = "Sum"
  threshold           = var.rate_limit_threshold
  treat_missing_data  = "notBreaching"
  
  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

# Proxy Lambda Errors Alarm
resource "aws_cloudwatch_metric_alarm" "proxy_lambda_errors" {
  alarm_name          = "${var.project_name}-${var.environment}-proxy-lambda-errors"
  alarm_description   = "Proxy Lambda is throwing errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  treat_missing_data  = "notBreaching"
  
  dimensions = {
    FunctionName = var.proxy_lambda_name
  }
  
  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}

# Authorizer Lambda Errors Alarm
resource "aws_cloudwatch_metric_alarm" "authorizer_lambda_errors" {
  alarm_name          = "${var.project_name}-${var.environment}-authorizer-lambda-errors"
  alarm_description   = "Authorizer Lambda is throwing errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  treat_missing_data  = "notBreaching"
  
  dimensions = {
    FunctionName = var.authorizer_lambda_name
  }
  
  alarm_actions = local.alarm_actions
  ok_actions    = local.alarm_actions
}
