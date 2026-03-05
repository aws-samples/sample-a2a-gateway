output "role_arn" {
  description = "ARN of the execution role"
  value       = aws_iam_role.agent_execution.arn
}

output "role_name" {
  description = "Name of the execution role"
  value       = aws_iam_role.agent_execution.name
}

output "policy_name" {
  description = "Name of the inline execution policy"
  value       = aws_iam_role_policy.execution.name
}
