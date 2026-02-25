output "vector_bucket_name" {
  description = "Name of the S3 vector bucket"
  value       = aws_s3vectors_vector_bucket.agents.vector_bucket_name
}

output "vector_bucket_arn" {
  description = "ARN of the S3 vector bucket"
  value       = aws_s3vectors_vector_bucket.agents.vector_bucket_arn
}

output "vector_index_name" {
  description = "Name of the vector index"
  value       = aws_s3vectors_index.agents.index_name
}

output "vector_index_arn" {
  description = "ARN of the vector index"
  value       = aws_s3vectors_index.agents.index_arn
}
