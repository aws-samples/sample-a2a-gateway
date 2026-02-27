# Admin Lambda Function

# IAM Role for Admin Lambda
resource "aws_iam_role" "admin" {
  name = "${var.project_name}-${var.environment}-admin-role"

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
    Name = "${var.project_name}-${var.environment}-admin-role"
  }
}

# Attach execution policy — VPC-aware when private deployment is enabled
resource "aws_iam_role_policy_attachment" "admin_basic" {
  role       = aws_iam_role.admin.name
  policy_arn = var.enable_vpc ? "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole" : "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# DynamoDB, Secrets Manager, S3 Vectors, and Bedrock permissions for Admin Lambda
resource "aws_iam_role_policy" "admin_permissions" {
  name = "${var.project_name}-${var.environment}-admin-permissions"
  role = aws_iam_role.admin.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem"
        ]
        Resource = [
          var.agent_registry_table_arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:CreateSecret",
          "secretsmanager:PutSecretValue",
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = "arn:aws:secretsmanager:*:*:secret:a2a-gateway/*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3vectors:PutVectors",
          "s3vectors:DeleteVectors"
        ]
        Resource = var.vector_bucket_arn != "" ? [
          var.vector_bucket_arn,
          "${var.vector_bucket_arn}/*"
        ] : ["arn:aws:s3vectors:*:*:bucket/*"]
      },
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = [
          "arn:aws:bedrock:*::foundation-model/amazon.titan-embed-text-v2:0"
        ]
      }
    ]
  })
}

# Lambda Function
resource "aws_lambda_function" "admin" {
  filename         = "${path.module}/builds/lambda.zip"
  function_name    = "${var.project_name}-${var.environment}-admin"
  role            = aws_iam_role.admin.arn
  handler         = "admin.handler.lambda_handler"
  source_code_hash = filebase64sha256("${path.module}/builds/lambda.zip")
  runtime         = "python3.12"
  timeout         = 60
  memory_size     = 512

  environment {
    variables = {
      AGENT_REGISTRY_TABLE = var.agent_registry_table_name
      PERMISSIONS_TABLE    = var.permissions_table_name
      GATEWAY_DOMAIN       = var.gateway_domain
      VECTOR_BUCKET_NAME   = var.vector_bucket_name
      VECTOR_INDEX_NAME    = var.vector_index_name
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
    Name = "${var.project_name}-${var.environment}-admin"
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "admin" {
  name              = "/aws/lambda/${aws_lambda_function.admin.function_name}"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-${var.environment}-admin-logs"
  }
}
