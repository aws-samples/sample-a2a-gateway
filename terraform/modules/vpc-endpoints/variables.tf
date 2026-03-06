variable "vpc_id" {
  description = "The ID of the VPC in which the endpoints will be created"
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs for Interface VPC endpoints"
  type        = list(string)
}

variable "route_table_ids" {
  description = "Route table IDs for Gateway VPC endpoints (DynamoDB, S3)"
  type        = list(string)
}

variable "security_group_ids" {
  description = "Security group IDs to associate with Interface VPC endpoints"
  type        = list(string)
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "enable_bedrock_endpoint" {
  description = "Create a VPC endpoint for Bedrock Runtime"
  type        = bool
  default     = true
}
