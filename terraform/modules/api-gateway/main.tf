# API Gateway REST API for A2A Gateway

# REST API
resource "aws_api_gateway_rest_api" "main" {
  name        = "${var.project_name}-${var.environment}"
  description = "A2A Gateway REST API"

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-api"
  }
}

# Lambda Authorizer
resource "aws_api_gateway_authorizer" "lambda" {
  name                   = "${var.project_name}-${var.environment}-authorizer"
  rest_api_id            = aws_api_gateway_rest_api.main.id
  authorizer_uri         = var.authorizer_lambda_invoke_arn
  authorizer_credentials = aws_iam_role.authorizer_invocation.arn
  type                   = "REQUEST"
  identity_source        = "method.request.header.Authorization"
  
  # Cache authorizer results for 5 minutes
  authorizer_result_ttl_in_seconds = 300
}

# IAM role for API Gateway to invoke authorizer
resource "aws_iam_role" "authorizer_invocation" {
  name = "${var.project_name}-${var.environment}-apigw-auth-invocation"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "apigateway.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "authorizer_invocation" {
  name = "lambda-invoke"
  role = aws_iam_role.authorizer_invocation.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = "lambda:InvokeFunction"
        Effect   = "Allow"
        Resource = var.authorizer_lambda_arn
      }
    ]
  })
}

# /agents resource
resource "aws_api_gateway_resource" "agents" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "agents"
}

# /agents/{proxy+} resource (greedy path parameter)
resource "aws_api_gateway_resource" "agents_proxy" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.agents.id
  path_part   = "{proxy+}"
}

# /admin resource
resource "aws_api_gateway_resource" "admin" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "admin"
}

# /admin/agents resource
resource "aws_api_gateway_resource" "admin_agents" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.admin.id
  path_part   = "agents"
}

# /admin/agents/register resource
resource "aws_api_gateway_resource" "admin_agents_register" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.admin_agents.id
  path_part   = "register"
}

# /admin/agents/{agentId} resource
resource "aws_api_gateway_resource" "admin_agents_id" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.admin_agents.id
  path_part   = "{agentId}"
}

# /admin/agents/{agentId}/sync resource
resource "aws_api_gateway_resource" "admin_agents_sync" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.admin_agents_id.id
  path_part   = "sync"
}

# /admin/agents/{agentId}/status resource
resource "aws_api_gateway_resource" "admin_agents_status" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.admin_agents_id.id
  path_part   = "status"
}

# GET /agents - Registry Lambda
resource "aws_api_gateway_method" "agents_get" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.agents.id
  http_method   = "GET"
  authorization = "CUSTOM"
  authorizer_id = aws_api_gateway_authorizer.lambda.id
}

resource "aws_api_gateway_integration" "agents_get" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.agents.id
  http_method             = aws_api_gateway_method.agents_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.registry_lambda_invoke_arn
}

# ANY /agents/{proxy+} - Proxy Lambda
resource "aws_api_gateway_method" "agents_proxy_any" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.agents_proxy.id
  http_method   = "ANY"
  authorization = "CUSTOM"
  authorizer_id = aws_api_gateway_authorizer.lambda.id

  request_parameters = {
    "method.request.path.proxy" = true
  }
}

resource "aws_api_gateway_integration" "agents_proxy_any" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.agents_proxy.id
  http_method             = aws_api_gateway_method.agents_proxy_any.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.proxy_lambda_invoke_arn
}

# POST /admin/agents/register - Admin Lambda
resource "aws_api_gateway_method" "admin_register" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.admin_agents_register.id
  http_method   = "POST"
  authorization = "CUSTOM"
  authorizer_id = aws_api_gateway_authorizer.lambda.id
}

resource "aws_api_gateway_integration" "admin_register" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.admin_agents_register.id
  http_method             = aws_api_gateway_method.admin_register.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.admin_lambda_invoke_arn
}

# POST /admin/agents/{agentId}/sync - Admin Lambda
resource "aws_api_gateway_method" "admin_sync" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.admin_agents_sync.id
  http_method   = "POST"
  authorization = "CUSTOM"
  authorizer_id = aws_api_gateway_authorizer.lambda.id
}

resource "aws_api_gateway_integration" "admin_sync" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.admin_agents_sync.id
  http_method             = aws_api_gateway_method.admin_sync.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.admin_lambda_invoke_arn
}

# PATCH /admin/agents/{agentId}/status - Admin Lambda
resource "aws_api_gateway_method" "admin_status" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.admin_agents_status.id
  http_method   = "PATCH"
  authorization = "CUSTOM"
  authorizer_id = aws_api_gateway_authorizer.lambda.id
}

resource "aws_api_gateway_integration" "admin_status" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.admin_agents_status.id
  http_method             = aws_api_gateway_method.admin_status.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.admin_lambda_invoke_arn
}

# Lambda permissions for API Gateway
resource "aws_lambda_permission" "registry" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.registry_lambda_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

resource "aws_lambda_permission" "proxy" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.proxy_lambda_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

resource "aws_lambda_permission" "admin" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.admin_lambda_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

# Deployment
resource "aws_api_gateway_deployment" "main" {
  rest_api_id = aws_api_gateway_rest_api.main.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.agents.id,
      aws_api_gateway_resource.agents_proxy.id,
      aws_api_gateway_method.agents_get.id,
      aws_api_gateway_method.agents_proxy_any.id,
      aws_api_gateway_integration.agents_get.id,
      aws_api_gateway_integration.agents_proxy_any.id,
      aws_api_gateway_method.admin_register.id,
      aws_api_gateway_method.admin_sync.id,
      aws_api_gateway_method.admin_status.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_integration.agents_get,
    aws_api_gateway_integration.agents_proxy_any,
    aws_api_gateway_integration.admin_register,
    aws_api_gateway_integration.admin_sync,
    aws_api_gateway_integration.admin_status,
  ]
}

# Stage
resource "aws_api_gateway_stage" "main" {
  deployment_id = aws_api_gateway_deployment.main.id
  rest_api_id   = aws_api_gateway_rest_api.main.id
  stage_name    = var.stage_name

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      caller         = "$context.identity.caller"
      user           = "$context.identity.user"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      resourcePath   = "$context.resourcePath"
      status         = "$context.status"
      protocol       = "$context.protocol"
      responseLength = "$context.responseLength"
    })
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-${var.stage_name}"
  }
}

# CloudWatch Log Group for API Gateway
resource "aws_cloudwatch_log_group" "api_gateway" {
  name              = "/aws/apigateway/${var.project_name}-${var.environment}"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-${var.environment}-api-logs"
  }
}

# Enable CORS for all methods
resource "aws_api_gateway_method" "agents_options" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.agents.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "agents_options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.agents.id
  http_method = aws_api_gateway_method.agents_options.http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "agents_options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.agents.id
  http_method = aws_api_gateway_method.agents_options.http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "agents_options" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.agents.id
  http_method = aws_api_gateway_method.agents_options.http_method
  status_code = aws_api_gateway_method_response.agents_options.status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Authorization,Content-Type'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,POST,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }
}
