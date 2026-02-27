# Proxy Lambda Function (Container-based with streaming support)

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

# Attach execution policy — VPC-aware when private deployment is enabled
resource "aws_iam_role_policy_attachment" "proxy_basic" {
  role       = aws_iam_role.proxy.name
  policy_arn = var.enable_vpc ? "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole" : "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
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

# Lambda Function (Container Image)
resource "aws_lambda_function" "proxy" {
  function_name = "${var.project_name}-${var.environment}-proxy"
  role          = aws_iam_role.proxy.arn
  package_type  = "Image"
  image_uri     = "${var.proxy_ecr_repository_url}:latest"
  timeout       = 900  # 15 minutes for streaming support
  memory_size   = 1024

  environment {
    variables = {
      AGENT_REGISTRY_TABLE = var.agent_registry_table_name
      PERMISSIONS_TABLE    = var.permissions_table_name
      GATEWAY_DOMAIN       = var.gateway_domain
      LOG_LEVEL            = "INFO"
    }
  }

  # Ignore changes to image_uri since it's updated by CI/CD
  lifecycle {
    ignore_changes = [image_uri, environment]
  }

  dynamic "vpc_config" {
    for_each = var.enable_vpc ? [1] : []
    content {
      subnet_ids         = var.vpc_subnet_ids
      security_group_ids = var.vpc_security_group_ids
    }
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
