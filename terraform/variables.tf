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

# ─── Private Deployment ─────────────────────────────────────────────────────────

variable "enable_private_deployment" {
  description = "Enable private deployment with VPC, private API Gateway, and Lambda VPC attachment"
  type        = bool
  default     = false
}

variable "enable_bedrock_endpoint" {
  description = "Create a VPC endpoint for Bedrock Runtime (only used when enable_private_deployment is true)"
  type        = bool
  default     = true
}

# ─── VPC Configuration (mutually exclusive: create new OR bring your own) ──────

variable "vpc_cidr" {
  description = "CIDR block for the VPC (only used when creating a new VPC, i.e. existing_vpc_id is not set)"
  type        = string
  default     = "10.0.0.0/16"
}

variable "existing_vpc_id" {
  description = "ID of an existing VPC. When set, the gateway skips VPC creation and deploys into this VPC."
  type        = string
  default     = ""
}

variable "existing_subnet_ids" {
  description = "List of existing private subnet IDs. Required when existing_vpc_id is set."
  type        = list(string)
  default     = []
}

variable "existing_route_table_ids" {
  description = "List of route table IDs associated with the existing subnets. Required when existing_vpc_id is set (needed for Gateway VPC endpoints)."
  type        = list(string)
  default     = []
}

variable "existing_lambda_security_group_id" {
  description = "Existing security group ID for Lambda functions. Required when existing_vpc_id is set."
  type        = string
  default     = ""
}

variable "existing_vpc_endpoint_security_group_id" {
  description = "Existing security group ID for VPC endpoints. Required when existing_vpc_id is set."
  type        = string
  default     = ""
}
