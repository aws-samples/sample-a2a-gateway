output "execute_api_vpc_endpoint_id" {
  description = "ID of the execute-api VPC endpoint (needed for private API Gateway)"
  value       = aws_vpc_endpoint.execute_api.id
}

output "dynamodb_endpoint_prefix_list_id" {
  description = "Prefix list ID for the DynamoDB Gateway endpoint (needed for Lambda SG egress rules)"
  value       = aws_vpc_endpoint.dynamodb.prefix_list_id
}

output "s3_endpoint_prefix_list_id" {
  description = "Prefix list ID for the S3 Gateway endpoint (needed for Lambda SG egress rules)"
  value       = aws_vpc_endpoint.s3.prefix_list_id
}
