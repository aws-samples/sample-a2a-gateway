variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "stage_name" {
  description = "API Gateway stage name"
  type        = string
  default     = "v1"
}

variable "authorizer_lambda_arn" {
  description = "ARN of the Authorizer Lambda function"
  type        = string
}

variable "authorizer_lambda_invoke_arn" {
  description = "Invoke ARN of the Authorizer Lambda function"
  type        = string
}

variable "registry_lambda_name" {
  description = "Name of the Registry Lambda function"
  type        = string
}

variable "registry_lambda_invoke_arn" {
  description = "Invoke ARN of the Registry Lambda function"
  type        = string
}

variable "proxy_lambda_name" {
  description = "Name of the Proxy Lambda function"
  type        = string
}

variable "proxy_lambda_invoke_arn" {
  description = "Invoke ARN of the Proxy Lambda function"
  type        = string
}

variable "proxy_lambda_arn" {
  description = "ARN of the Proxy Lambda function"
  type        = string
}

variable "admin_lambda_name" {
  description = "Name of the Admin Lambda function"
  type        = string
}

variable "admin_lambda_invoke_arn" {
  description = "Invoke ARN of the Admin Lambda function"
  type        = string
}

variable "search_lambda_name" {
  description = "Name of the Search Lambda function"
  type        = string
}

variable "search_lambda_invoke_arn" {
  description = "Invoke ARN of the Search Lambda function"
  type        = string
}
