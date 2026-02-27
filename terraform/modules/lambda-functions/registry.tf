# Registry Lambda Function

# IAM Role for Registry Lambda
resource "aws_iam_role" "registry" {
  name = "${var.project_name}-${var.environment}-registry-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-${var.environment}-registry-role"
  }
}

# Attach execution policy — VPC-aware when private deployment is enabled
resource "aws_iam_role_policy_attachment" "registry_basic" {
  role       = aws_iam_role.registry.name
  policy_arn = var.enable_vpc ? "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole" : "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# DynamoDB read permissions for Registry Lambda
resource "aws_iam_role_policy" "registry_dynamodb" {
  name = "${var.project_name}-${var.environment}-registry-dynamodb"
  role = aws_iam_role.registry.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Scan",
          "dynamodb:Query"
        ]
        Resource = [
          var.agent_registry_table_arn,
          var.permissions_table_arn
        ]
      }
    ]
  })
}

# Lambda Function
resource "aws_lambda_function" "registry" {
  filename         = "${path.module}/builds/lambda.zip"
  function_name    = "${var.project_name}-${var.environment}-registry"
  role            = aws_iam_role.registry.arn
  handler         = "registry.handler.lambda_handler"
  source_code_hash = filebase64sha256("${path.module}/builds/lambda.zip")
  runtime         = "python3.12"
  timeout         = 30
  memory_size     = 512

  environment {
    variables = {
      AGENT_REGISTRY_TABLE = var.agent_registry_table_name
      PERMISSIONS_TABLE    = var.permissions_table_name
      GATEWAY_DOMAIN       = var.gateway_domain
      LOG_LEVEL            = "INFO"
    }
  }

  # Ignore changes to environment variables since they're updated by null_resource
  lifecycle {
    ignore_changes = [environment]
  }

  dynamic "vpc_config" {
    for_each = var.enable_vpc ? [1] : []
    content {
      subnet_ids         = var.vpc_subnet_ids
      security_group_ids = var.vpc_security_group_ids
    }
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-registry"
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "registry" {
  name              = "/aws/lambda/${aws_lambda_function.registry.function_name}"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-${var.environment}-registry-logs"
  }
}
