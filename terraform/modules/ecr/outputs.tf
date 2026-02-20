output "proxy_repository_url" {
  description = "URL of the proxy ECR repository"
  value       = aws_ecr_repository.proxy.repository_url
}

output "proxy_repository_arn" {
  description = "ARN of the proxy ECR repository"
  value       = aws_ecr_repository.proxy.arn
}

output "proxy_repository_name" {
  description = "Name of the proxy ECR repository"
  value       = aws_ecr_repository.proxy.name
}
