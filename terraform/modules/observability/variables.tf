# Observability Module Variables

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment (e.g., poc, dev, prod)"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

# Lambda function names for log group references
variable "authorizer_lambda_name" {
  description = "Name of the authorizer Lambda function"
  type        = string
}

variable "registry_lambda_name" {
  description = "Name of the registry Lambda function"
  type        = string
}

variable "proxy_lambda_name" {
  description = "Name of the proxy Lambda function"
  type        = string
}

variable "admin_lambda_name" {
  description = "Name of the admin Lambda function"
  type        = string
}

variable "search_lambda_name" {
  description = "Name of the search Lambda function"
  type        = string
}

# SNS Configuration
variable "enable_alarms_sns" {
  description = "Enable SNS topic for alarm notifications"
  type        = bool
  default     = false
}

variable "alarm_email" {
  description = "Email address for alarm notifications (only used if enable_alarms_sns is true)"
  type        = string
  default     = ""
}

# Alarm Thresholds
variable "error_rate_threshold_percent" {
  description = "Error rate threshold percentage for alarm"
  type        = number
  default     = 5
}

variable "latency_threshold_ms" {
  description = "P95 latency threshold in milliseconds for alarm"
  type        = number
  default     = 10000
}

variable "auth_failure_threshold" {
  description = "Number of auth failures in 5 minutes to trigger alarm"
  type        = number
  default     = 50
}

variable "rate_limit_threshold" {
  description = "Number of rate limit hits in 5 minutes to trigger alarm"
  type        = number
  default     = 100
}

variable "backend_error_threshold" {
  description = "Number of backend unreachable errors in 5 minutes to trigger alarm"
  type        = number
  default     = 5
}

# Metrics namespace
variable "metrics_namespace" {
  description = "CloudWatch metrics namespace"
  type        = string
  default     = "A2AGateway"
}
