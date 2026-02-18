# AgentRegistry Table
resource "aws_dynamodb_table" "agent_registry" {
  name           = "${var.project_name}-${var.environment}-agent-registry"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "agentId"

  attribute {
    name = "agentId"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-agent-registry"
  }
}

# Permissions Table
resource "aws_dynamodb_table" "permissions" {
  name           = "${var.project_name}-${var.environment}-permissions"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "scope"

  attribute {
    name = "scope"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-permissions"
  }
}
