variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "agent_registry_table_name" {
  description = "Name of the AgentRegistry DynamoDB table"
  type        = string
}

variable "agent_registry_table_arn" {
  description = "ARN of the AgentRegistry DynamoDB table"
  type        = string
}

variable "permissions_table_name" {
  description = "Name of the Permissions DynamoDB table"
  type        = string
}

variable "permissions_table_arn" {
  description = "ARN of the Permissions DynamoDB table"
  type        = string
}

variable "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  type        = string
}

variable "cognito_issuer_url" {
  description = "Cognito issuer URL for JWT validation"
  type        = string
}

variable "cognito_jwks_uri" {
  description = "Cognito JWKS URI for JWT validation"
  type        = string
}

variable "cognito_client_id" {
  description = "Cognito client ID"
  type        = string
}

variable "gateway_domain" {
  description = "Gateway domain for URL rewriting"
  type        = string
}

variable "proxy_ecr_repository_url" {
  description = "ECR repository URL for proxy Lambda container"
  type        = string
}

variable "vector_bucket_name" {
  description = "Name of the S3 vector bucket for semantic search"
  type        = string
  default     = ""
}

variable "vector_bucket_arn" {
  description = "ARN of the S3 vector bucket for semantic search"
  type        = string
  default     = ""
}

variable "vector_index_name" {
  description = "Name of the vector index for semantic search"
  type        = string
  default     = ""
}
