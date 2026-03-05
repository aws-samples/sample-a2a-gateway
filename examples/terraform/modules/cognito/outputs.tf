output "user_pool_id" {
  description = "ID of the Cognito User Pool"
  value       = aws_cognito_user_pool.agent_users.id
}

output "user_pool_arn" {
  description = "ARN of the Cognito User Pool"
  value       = aws_cognito_user_pool.agent_users.arn
}

output "client_id" {
  description = "Cognito App Client ID"
  value       = aws_cognito_user_pool_client.gateway_client.id
}

output "client_secret" {
  description = "Cognito App Client Secret"
  value       = aws_cognito_user_pool_client.gateway_client.client_secret
  sensitive   = true
}

output "issuer_url" {
  description = "Cognito issuer URL for JWT validation"
  value       = "https://cognito-idp.${data.aws_region.current.id}.amazonaws.com/${aws_cognito_user_pool.agent_users.id}"
}

output "discovery_url" {
  description = "OIDC discovery URL"
  value       = "https://cognito-idp.${data.aws_region.current.id}.amazonaws.com/${aws_cognito_user_pool.agent_users.id}/.well-known/openid-configuration"
}

output "jwks_uri" {
  description = "JWKS URI for JWT signature verification"
  value       = "https://cognito-idp.${data.aws_region.current.id}.amazonaws.com/${aws_cognito_user_pool.agent_users.id}/.well-known/jwks.json"
}

output "token_endpoint" {
  description = "OAuth token endpoint"
  value       = "https://${aws_cognito_user_pool_domain.agent_pool.domain}.auth.${data.aws_region.current.id}.amazoncognito.com/oauth2/token"
}

output "scope_identifiers" {
  description = "All OAuth scope identifiers"
  value       = aws_cognito_resource_server.a2a_gateway.scope_identifiers
}
