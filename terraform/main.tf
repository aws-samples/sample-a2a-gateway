# DynamoDB Tables
module "dynamodb" {
  source = "./modules/dynamodb"

  project_name = var.project_name
  environment  = var.environment
}

# Cognito User Pool
module "cognito" {
  source = "./modules/cognito"

  user_pool_name = var.cognito_user_pool_name
  project_name   = var.project_name
  environment    = var.environment
}

# Lambda Functions
module "lambda_functions" {
  source = "./modules/lambda-functions"

  project_name              = var.project_name
  environment               = var.environment
  agent_registry_table_name = module.dynamodb.agent_registry_table_name
  agent_registry_table_arn  = module.dynamodb.agent_registry_table_arn
  permissions_table_name    = module.dynamodb.permissions_table_name
  permissions_table_arn     = module.dynamodb.permissions_table_arn
  cognito_user_pool_id      = module.cognito.user_pool_id
  cognito_issuer_url        = module.cognito.issuer_url
  cognito_jwks_uri          = module.cognito.jwks_uri
  cognito_client_id         = module.cognito.client_id
  gateway_domain            = "PLACEHOLDER"  # Will be updated by null_resource after API Gateway is created
}

# API Gateway
module "api_gateway" {
  source = "./modules/api-gateway"

  project_name     = var.project_name
  environment      = var.environment
  stage_name       = "v1"

  authorizer_lambda_arn        = module.lambda_functions.authorizer_lambda_arn
  authorizer_lambda_invoke_arn = module.lambda_functions.authorizer_lambda_invoke_arn
  registry_lambda_name         = module.lambda_functions.registry_lambda_name
  registry_lambda_invoke_arn   = module.lambda_functions.registry_lambda_invoke_arn
  proxy_lambda_name            = module.lambda_functions.proxy_lambda_name
  proxy_lambda_invoke_arn      = module.lambda_functions.proxy_lambda_invoke_arn
  admin_lambda_name            = module.lambda_functions.admin_lambda_name
  admin_lambda_invoke_arn      = module.lambda_functions.admin_lambda_invoke_arn
}

# Extract gateway domain (without https://)
locals {
  gateway_domain = replace(module.api_gateway.api_endpoint, "https://", "")
}

# Update Registry Lambda with gateway domain
resource "null_resource" "update_registry_lambda" {
  triggers = {
    gateway_domain = local.gateway_domain
  }

  provisioner "local-exec" {
    command = <<-EOT
      aws lambda update-function-configuration \
        --function-name ${module.lambda_functions.registry_lambda_name} \
        --environment "Variables={AGENT_REGISTRY_TABLE=${module.dynamodb.agent_registry_table_name},PERMISSIONS_TABLE=${module.dynamodb.permissions_table_name},GATEWAY_DOMAIN=${local.gateway_domain},LOG_LEVEL=INFO}" \
        --region ${var.aws_region}
    EOT
  }

  depends_on = [module.api_gateway]
}

# Update Admin Lambda with gateway domain
resource "null_resource" "update_admin_lambda" {
  triggers = {
    gateway_domain = local.gateway_domain
  }

  provisioner "local-exec" {
    command = <<-EOT
      aws lambda update-function-configuration \
        --function-name ${module.lambda_functions.admin_lambda_name} \
        --environment "Variables={AGENT_REGISTRY_TABLE=${module.dynamodb.agent_registry_table_name},PERMISSIONS_TABLE=${module.dynamodb.permissions_table_name},GATEWAY_DOMAIN=${local.gateway_domain},LOG_LEVEL=INFO}" \
        --region ${var.aws_region}
    EOT
  }

  depends_on = [module.api_gateway]
}

# Update Proxy Lambda with gateway domain
resource "null_resource" "update_proxy_lambda" {
  triggers = {
    gateway_domain = local.gateway_domain
  }

  provisioner "local-exec" {
    command = <<-EOT
      aws lambda update-function-configuration \
        --function-name ${module.lambda_functions.proxy_lambda_name} \
        --environment "Variables={AGENT_REGISTRY_TABLE=${module.dynamodb.agent_registry_table_name},PERMISSIONS_TABLE=${module.dynamodb.permissions_table_name},GATEWAY_DOMAIN=${local.gateway_domain},LOG_LEVEL=INFO}" \
        --region ${var.aws_region}
    EOT
  }

  depends_on = [module.api_gateway]
}
