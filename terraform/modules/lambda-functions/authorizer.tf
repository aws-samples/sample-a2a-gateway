# Lambda Authorizer Function

# IAM Role for Authorizer Lambda
resource "aws_iam_role" "authorizer" {
  name = "${var.project_name}-${var.environment}-authorizer-role"

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
    Name = "${var.project_name}-${var.environment}-authorizer-role"
  }
}

# Attach basic Lambda execution policy
resource "aws_iam_role_policy_attachment" "authorizer_basic" {
  role       = aws_iam_role.authorizer.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Lambda Function
# Note: Run scripts/build_lambda_package.sh before terraform apply
resource "aws_lambda_function" "authorizer" {
  filename         = "${path.module}/builds/lambda.zip"
  function_name    = "${var.project_name}-${var.environment}-authorizer"
  role            = aws_iam_role.authorizer.arn
  handler         = "authorizer.handler.lambda_handler"
  source_code_hash = filebase64sha256("${path.module}/builds/lambda.zip")
  runtime         = "python3.12"
  timeout         = 10
  memory_size     = 256

  environment {
    variables = {
      COGNITO_JWKS_URI    = var.cognito_jwks_uri
      COGNITO_ISSUER_URL  = var.cognito_issuer_url
      COGNITO_CLIENT_ID   = var.cognito_client_id
      LOG_LEVEL           = "INFO"
    }
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-authorizer"
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "authorizer" {
  name              = "/aws/lambda/${aws_lambda_function.authorizer.function_name}"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-${var.environment}-authorizer-logs"
  }
}
