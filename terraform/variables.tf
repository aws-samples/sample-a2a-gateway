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

variable "enable_private_deployment" {
  description = "Enable private deployment with VPC, private API Gateway, and Lambda VPC attachment"
  type        = bool
  default     = false
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC (only used when enable_private_deployment is true)"
  type        = string
  default     = "10.0.0.0/16"
}

variable "enable_bedrock_endpoint" {
  description = "Create a VPC endpoint for Bedrock Runtime (only used when enable_private_deployment is true)"
  type        = bool
  default     = true
}
