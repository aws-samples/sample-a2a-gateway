# Search Lambda Function

# IAM Role for Search Lambda
resource "aws_iam_role" "search" {
  name = "${var.project_name}-${var.environment}-search-role"

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
    Name = "${var.project_name}-${var.environment}-search-role"
  }
}

# Attach basic Lambda execution policy
resource "aws_iam_role_policy_attachment" "search_basic" {
  role       = aws_iam_role.search.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# DynamoDB, S3 Vectors, and Bedrock permissions for Search Lambda
resource "aws_iam_role_policy" "search_permissions" {
  name = "${var.project_name}-${var.environment}-search-permissions"
  role = aws_iam_role.search.id

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
      },
      {
        Effect = "Allow"
        Action = [
          "s3vectors:QueryVectors",
          "s3vectors:GetVectors"
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
resource "aws_lambda_function" "search" {
  filename         = "${path.module}/builds/lambda.zip"
  function_name    = "${var.project_name}-${var.environment}-search"
  role             = aws_iam_role.search.arn
  handler          = "search.handler.lambda_handler"
  source_code_hash = filebase64sha256("${path.module}/builds/lambda.zip")
  runtime          = "python3.12"
  timeout          = 30
  memory_size      = 512

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

  tags = {
    Name = "${var.project_name}-${var.environment}-search"
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "search" {
  name              = "/aws/lambda/${aws_lambda_function.search.function_name}"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-${var.environment}-search-logs"
  }
}
