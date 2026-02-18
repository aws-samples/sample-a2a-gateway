variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "a2a-gateway"
}

variable "environment" {
  description = "Environment name (e.g., dev, poc)"
  type        = string
  default     = "poc"
}

variable "cognito_user_pool_name" {
  description = "Name for the Cognito User Pool"
  type        = string
  default     = "a2a-gateway-users"
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default     = {}
}
