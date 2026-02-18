# Cognito User Pool
resource "aws_cognito_user_pool" "main" {
  name = var.user_pool_name

  # Password policy
  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
    require_uppercase = true
  }

  # User attributes
  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true
  }

  # Auto-verified attributes
  auto_verified_attributes = ["email"]

  # Account recovery
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  tags = {
    Name = var.user_pool_name
  }
}

# App Client for the gateway
resource "aws_cognito_user_pool_client" "gateway_client" {
  name         = "${var.user_pool_name}-client"
  user_pool_id = aws_cognito_user_pool.main.id

  # OAuth flows
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["client_credentials"]
  allowed_oauth_scopes                 = aws_cognito_resource_server.gateway.scope_identifiers

  # Token validity
  access_token_validity  = 60  # minutes
  id_token_validity      = 60  # minutes
  refresh_token_validity = 30  # days

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  # Prevent secret rotation issues
  generate_secret = true

  explicit_auth_flows = [
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_USER_SRP_AUTH"
  ]
}

# Resource Server for custom scopes
resource "aws_cognito_resource_server" "gateway" {
  identifier   = "a2a-gateway"
  name         = "A2A Gateway"
  user_pool_id = aws_cognito_user_pool.main.id

  scope {
    scope_name        = "billing:read"
    scope_description = "Read access to billing agent"
  }

  scope {
    scope_name        = "billing:write"
    scope_description = "Write access to billing agent"
  }

  scope {
    scope_name        = "search:read"
    scope_description = "Read access to search agent"
  }

  scope {
    scope_name        = "gateway:admin"
    scope_description = "Admin access to gateway management"
  }
}

# User Pool Domain (for OAuth endpoints)
resource "aws_cognito_user_pool_domain" "main" {
  domain       = "${var.project_name}-${var.environment}-${random_string.domain_suffix.result}"
  user_pool_id = aws_cognito_user_pool.main.id
}

# Random suffix for unique domain
resource "random_string" "domain_suffix" {
  length  = 8
  special = false
  upper   = false
}
