output "agent_registry_table_name" {
  description = "Name of the AgentRegistry DynamoDB table"
  value       = aws_dynamodb_table.agent_registry.name
}

output "agent_registry_table_arn" {
  description = "ARN of the AgentRegistry DynamoDB table"
  value       = aws_dynamodb_table.agent_registry.arn
}

output "permissions_table_name" {
  description = "Name of the Permissions DynamoDB table"
  value       = aws_dynamodb_table.permissions.name
}

output "permissions_table_arn" {
  description = "ARN of the Permissions DynamoDB table"
  value       = aws_dynamodb_table.permissions.arn
}
