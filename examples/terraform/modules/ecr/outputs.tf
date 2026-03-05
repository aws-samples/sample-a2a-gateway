output "repository_url" {
  description = "URL of the ECR repository"
  value       = aws_ecr_repository.agent_repo.repository_url
}

output "repository_arn" {
  description = "ARN of the ECR repository"
  value       = aws_ecr_repository.agent_repo.arn
}

output "repository_name" {
  description = "Name of the ECR repository"
  value       = aws_ecr_repository.agent_repo.name
}

output "repository_id" {
  description = "ID of the ECR repository"
  value       = aws_ecr_repository.agent_repo.id
}
