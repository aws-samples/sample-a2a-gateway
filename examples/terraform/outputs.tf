# ============================================================================
# Weather Agent Outputs
# ============================================================================

output "weather_agent_runtime_id" {
  description = "ID of the weather agent runtime"
  value       = module.weather_runtime.agent_runtime_id
}

output "weather_agent_runtime_arn" {
  description = "ARN of the weather agent runtime"
  value       = module.weather_runtime.agent_runtime_arn
}

output "weather_ecr_repository_url" {
  description = "ECR repository URL for the weather agent"
  value       = module.ecr_weather.repository_url
}

# ============================================================================
# Calculator Agent Outputs
# ============================================================================

output "calculator_agent_runtime_id" {
  description = "ID of the calculator agent runtime"
  value       = module.calculator_runtime.agent_runtime_id
}

output "calculator_agent_runtime_arn" {
  description = "ARN of the calculator agent runtime"
  value       = module.calculator_runtime.agent_runtime_arn
}

output "calculator_ecr_repository_url" {
  description = "ECR repository URL for the calculator agent"
  value       = module.ecr_calculator.repository_url
}

# ============================================================================
# Cognito / OAuth Outputs
# ============================================================================

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  value       = module.cognito.user_pool_id
}

output "cognito_client_id" {
  description = "Cognito App Client ID"
  value       = module.cognito.client_id
}

output "cognito_client_secret" {
  description = "Cognito App Client Secret"
  value       = module.cognito.client_secret
  sensitive   = true
}

output "cognito_issuer_url" {
  description = "Cognito issuer URL for JWT validation"
  value       = module.cognito.issuer_url
}

output "cognito_discovery_url" {
  description = "OIDC discovery URL configured on agent runtimes"
  value       = module.cognito.discovery_url
}

output "cognito_jwks_uri" {
  description = "JWKS URI for JWT signature verification"
  value       = module.cognito.jwks_uri
}

output "cognito_token_endpoint" {
  description = "OAuth token endpoint for client_credentials flow"
  value       = module.cognito.token_endpoint
}

output "cognito_scopes" {
  description = "Available OAuth scopes"
  value       = module.cognito.scope_identifiers
}

# ============================================================================
# AgentCore Runtime URLs
# ============================================================================

output "weather_agent_backend_url" {
  description = "Backend URL for the weather agent"
  value       = module.weather_runtime.backend_url
}

output "weather_agent_card_url" {
  description = "Agent Card URL for the weather agent"
  value       = module.weather_runtime.agent_card_url
}

output "calculator_agent_backend_url" {
  description = "Backend URL for the calculator agent"
  value       = module.calculator_runtime.backend_url
}

output "calculator_agent_card_url" {
  description = "Agent Card URL for the calculator agent"
  value       = module.calculator_runtime.agent_card_url
}

# ============================================================================
# Test Commands
# ============================================================================

output "test_get_token_command" {
  description = "Command to obtain an OAuth token"
  value       = "curl -X POST '${module.cognito.token_endpoint}' -H 'Content-Type: application/x-www-form-urlencoded' -d 'grant_type=client_credentials&client_id=${module.cognito.client_id}&client_secret=<CLIENT_SECRET>&scope=a2a-gateway/weather:read a2a-gateway/calculator:read'"
}

output "test_weather_command" {
  description = "AWS CLI command to test the weather agent"
  value       = "aws bedrock-agentcore invoke-agent-runtime --agent-runtime-arn ${module.weather_runtime.agent_runtime_arn} --qualifier DEFAULT --payload '{\"prompt\": \"What is the weather in Seattle?\"}' --region ${data.aws_region.current.id} response.json"
}

output "test_calculator_command" {
  description = "AWS CLI command to test the calculator agent"
  value       = "aws bedrock-agentcore invoke-agent-runtime --agent-runtime-arn ${module.calculator_runtime.agent_runtime_arn} --qualifier DEFAULT --payload '{\"prompt\": \"What is 42 * 17?\"}' --region ${data.aws_region.current.id} response.json"
}