# Proxy Lambda Function

# IAM Role for Proxy Lambda
resource "aws_iam_role" "proxy" {
  name = "${var.project_name}-${var.environment}-proxy-role"

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
    Name = "${var.project_name}-${var.environment}-proxy-role"
  }
}

# Attach basic Lambda execution policy
resource "aws_iam_role_policy_attachment" "proxy_basic" {
  role       = aws_iam_role.proxy.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# DynamoDB and Secrets Manager permissions for Proxy Lambda
resource "aws_iam_role_policy" "proxy_permissions" {
  name = "${var.project_name}-${var.environment}-proxy-permissions"
  role = aws_iam_role.proxy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query"
        ]
        Resource = [
          var.agent_registry_table_arn,
          var.permissions_table_arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = "arn:aws:secretsmanager:*:*:secret:a2a-gateway/*"
      }
    ]
  })
}

# Lambda Function
resource "aws_lambda_function" "proxy" {
  filename         = "${path.module}/builds/lambda.zip"
  function_name    = "${var.project_name}-${var.environment}-proxy"
  role            = aws_iam_role.proxy.arn
  handler         = "proxy.handler.lambda_handler"
  source_code_hash = filebase64sha256("${path.module}/builds/lambda.zip")
  runtime         = "python3.12"
  timeout         = 900  # 15 minutes for streaming support
  memory_size     = 1024

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

  tags = {
    Name = "${var.project_name}-${var.environment}-proxy"
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "proxy" {
  name              = "/aws/lambda/${aws_lambda_function.proxy.function_name}"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-${var.environment}-proxy-logs"
  }
}
