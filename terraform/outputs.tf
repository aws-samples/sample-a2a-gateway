# DynamoDB Outputs
output "agent_registry_table_name" {
  description = "Name of the AgentRegistry DynamoDB table"
  value       = module.dynamodb.agent_registry_table_name
}

output "permissions_table_name" {
  description = "Name of the Permissions DynamoDB table"
  value       = module.dynamodb.permissions_table_name
}

# Cognito Outputs
output "cognito_user_pool_id" {
  description = "ID of the Cognito User Pool"
  value       = module.cognito.user_pool_id
}

output "cognito_client_id" {
  description = "ID of the Cognito User Pool Client"
  value       = module.cognito.client_id
}

output "cognito_client_secret" {
  description = "Secret of the Cognito User Pool Client"
  value       = module.cognito.client_secret
  sensitive   = true
}

output "cognito_issuer_url" {
  description = "Cognito issuer URL for JWT validation"
  value       = module.cognito.issuer_url
}

output "cognito_jwks_uri" {
  description = "Cognito JWKS URI for JWT validation"
  value       = module.cognito.jwks_uri
}

output "cognito_token_endpoint" {
  description = "Cognito OAuth token endpoint"
  value       = module.cognito.token_endpoint
}

# Lambda Outputs
output "authorizer_lambda_arn" {
  description = "ARN of the Authorizer Lambda function"
  value       = module.lambda_functions.authorizer_lambda_arn
}

output "registry_lambda_arn" {
  description = "ARN of the Registry Lambda function"
  value       = module.lambda_functions.registry_lambda_arn
}

output "proxy_lambda_arn" {
  description = "ARN of the Proxy Lambda function"
  value       = module.lambda_functions.proxy_lambda_arn
}

output "admin_lambda_arn" {
  description = "ARN of the Admin Lambda function"
  value       = module.lambda_functions.admin_lambda_arn
}

# API Gateway Outputs
output "api_gateway_url" {
  description = "URL of the API Gateway"
  value       = module.api_gateway.api_endpoint
}

output "api_gateway_id" {
  description = "ID of the API Gateway"
  value       = module.api_gateway.api_id
}

# ECR Outputs
output "proxy_ecr_repository_url" {
  description = "URL of the Proxy Lambda ECR repository"
  value       = module.ecr.proxy_repository_url
}

output "proxy_ecr_repository_name" {
  description = "Name of the Proxy Lambda ECR repository"
  value       = module.ecr.proxy_repository_name
}

# VPC Outputs (private deployment only)
output "vpc_id" {
  description = "ID of the VPC (null when private deployment is disabled)"
  value       = var.enable_private_deployment ? local.vpc_id : null
}

output "private_subnet_ids" {
  description = "IDs of the private subnets (null when private deployment is disabled)"
  value       = var.enable_private_deployment ? local.subnet_ids : null
}

output "execute_api_vpc_endpoint_id" {
  description = "ID of the execute-api VPC endpoint (null when private deployment is disabled)"
  value       = var.enable_private_deployment ? module.vpc_endpoints[0].execute_api_vpc_endpoint_id : null
}
