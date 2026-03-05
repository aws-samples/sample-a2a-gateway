data "aws_region" "current" {}

resource "aws_cognito_user_pool" "agent_users" {
  name = "${var.stack_name}-agent-users"

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
    require_uppercase = true
  }

  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true
  }

  auto_verified_attributes = ["email"]

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  tags = { Name = "${var.stack_name}-agent-users" }
}

resource "aws_cognito_resource_server" "a2a_gateway" {
  identifier   = "a2a-gateway"
  name         = "A2A Gateway Agents"
  user_pool_id = aws_cognito_user_pool.agent_users.id

  dynamic "scope" {
    for_each = var.oauth_scopes
    content {
      scope_name        = scope.value.scope_name
      scope_description = scope.value.scope_description
    }
  }
}

resource "aws_cognito_user_pool_client" "gateway_client" {
  name         = "${var.stack_name}-gateway-client"
  user_pool_id = aws_cognito_user_pool.agent_users.id

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["client_credentials"]
  allowed_oauth_scopes                 = aws_cognito_resource_server.a2a_gateway.scope_identifiers

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  generate_secret = true

  explicit_auth_flows = [
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_USER_SRP_AUTH"
  ]
}

resource "random_string" "cognito_domain_suffix" {
  length  = 8
  special = false
  upper   = false
}

resource "aws_cognito_user_pool_domain" "agent_pool" {
  domain       = "${var.stack_name}-${var.environment}-${random_string.cognito_domain_suffix.result}"
  user_pool_id = aws_cognito_user_pool.agent_users.id
}
