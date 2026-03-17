# Observability Module Outputs

output "dashboard_name" {
  description = "Name of the CloudWatch dashboard"
  value       = aws_cloudwatch_dashboard.gateway.dashboard_name
}

output "dashboard_url" {
  description = "URL to the CloudWatch dashboard"
  value       = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${aws_cloudwatch_dashboard.gateway.dashboard_name}"
}

output "sns_topic_arn" {
  description = "ARN of the SNS topic for alarm notifications (if enabled)"
  value       = var.enable_alarms_sns ? aws_sns_topic.alarms[0].arn : null
}

output "alarm_arns" {
  description = "ARNs of all CloudWatch alarms"
  value = {
    high_error_rate      = aws_cloudwatch_metric_alarm.high_error_rate.arn
    high_latency         = aws_cloudwatch_metric_alarm.high_latency.arn
    backend_unreachable  = aws_cloudwatch_metric_alarm.backend_unreachable.arn
    auth_failure_spike   = aws_cloudwatch_metric_alarm.auth_failure_spike.arn
    rate_limit_exhaustion = aws_cloudwatch_metric_alarm.rate_limit_exhaustion.arn
    proxy_lambda_errors  = aws_cloudwatch_metric_alarm.proxy_lambda_errors.arn
    authorizer_lambda_errors = aws_cloudwatch_metric_alarm.authorizer_lambda_errors.arn
  }
}
