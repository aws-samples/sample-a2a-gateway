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

# S3 Vectors for semantic search
module "s3_vectors" {
  source = "./modules/s3-vectors"

  project_name = var.project_name
  environment  = var.environment
}

# ECR Repository for Proxy Lambda container
module "ecr" {
  source = "./modules/ecr"

  project_name = var.project_name
  environment  = var.environment
}

# Build and push proxy container image
resource "null_resource" "build_proxy_container" {
  triggers = {
    # Rebuild when source files change
    dockerfile_hash = filemd5("${path.module}/../src/lambdas/proxy_container/Dockerfile")
    main_hash       = filemd5("${path.module}/../src/lambdas/proxy_container/app/main.py")
    requirements_hash = filemd5("${path.module}/../src/lambdas/proxy_container/app/requirements.txt")
    shared_hash     = md5(join("", [
      filemd5("${path.module}/../src/lambdas/shared/dynamodb_client.py"),
      filemd5("${path.module}/../src/lambdas/shared/errors.py"),
      filemd5("${path.module}/../src/lambdas/shared/oauth_client.py"),
      filemd5("${path.module}/../src/lambdas/shared/url_rewriter.py")
    ]))
    ecr_repo        = module.ecr.proxy_repository_url
  }

  provisioner "local-exec" {
    command = <<-EOT
      # Login to ECR
      ECR_REGISTRY=$(echo "${module.ecr.proxy_repository_url}" | cut -d'/' -f1)
      aws ecr get-login-password --region ${var.aws_region} | \
        docker login --username AWS --password-stdin $ECR_REGISTRY
      
      # Build container
      cd ${path.module}/../src/lambdas
      docker build \
        -t ${module.ecr.proxy_repository_url}:latest \
        -f proxy_container/Dockerfile \
        --platform linux/amd64 \
        --provenance=false \
        .
      
      # Push to ECR
      docker push ${module.ecr.proxy_repository_url}:latest
    EOT
  }

  depends_on = [module.ecr]
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
  proxy_ecr_repository_url  = module.ecr.proxy_repository_url
  vector_bucket_name        = module.s3_vectors.vector_bucket_name
  vector_bucket_arn         = module.s3_vectors.vector_bucket_arn
  vector_index_name         = module.s3_vectors.vector_index_name

  depends_on = [null_resource.build_proxy_container]
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
  proxy_lambda_arn             = module.lambda_functions.proxy_lambda_arn
  admin_lambda_name            = module.lambda_functions.admin_lambda_name
  admin_lambda_invoke_arn      = module.lambda_functions.admin_lambda_invoke_arn
  search_lambda_name           = module.lambda_functions.search_lambda_name
  search_lambda_invoke_arn     = module.lambda_functions.search_lambda_invoke_arn
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
    gateway_domain     = local.gateway_domain
    vector_bucket_name = module.s3_vectors.vector_bucket_name
    vector_index_name  = module.s3_vectors.vector_index_name
  }

  provisioner "local-exec" {
    command = <<-EOT
      aws lambda update-function-configuration \
        --function-name ${module.lambda_functions.admin_lambda_name} \
        --environment "Variables={AGENT_REGISTRY_TABLE=${module.dynamodb.agent_registry_table_name},PERMISSIONS_TABLE=${module.dynamodb.permissions_table_name},GATEWAY_DOMAIN=${local.gateway_domain},VECTOR_BUCKET_NAME=${module.s3_vectors.vector_bucket_name},VECTOR_INDEX_NAME=${module.s3_vectors.vector_index_name},LOG_LEVEL=INFO}" \
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

# Update Search Lambda with gateway domain
resource "null_resource" "update_search_lambda" {
  triggers = {
    gateway_domain = local.gateway_domain
  }

  provisioner "local-exec" {
    command = <<-EOT
      aws lambda update-function-configuration \
        --function-name ${module.lambda_functions.search_lambda_name} \
        --environment "Variables={AGENT_REGISTRY_TABLE=${module.dynamodb.agent_registry_table_name},PERMISSIONS_TABLE=${module.dynamodb.permissions_table_name},GATEWAY_DOMAIN=${local.gateway_domain},VECTOR_BUCKET_NAME=${module.s3_vectors.vector_bucket_name},VECTOR_INDEX_NAME=${module.s3_vectors.vector_index_name},LOG_LEVEL=INFO}" \
        --region ${var.aws_region}
    EOT
  }

  depends_on = [module.api_gateway]
}
