output "authorizer_lambda_arn" {
  description = "ARN of the Authorizer Lambda function"
  value       = aws_lambda_function.authorizer.arn
}

output "authorizer_lambda_invoke_arn" {
  description = "Invoke ARN of the Authorizer Lambda function"
  value       = aws_lambda_function.authorizer.invoke_arn
}

output "authorizer_lambda_name" {
  description = "Name of the Authorizer Lambda function"
  value       = aws_lambda_function.authorizer.function_name
}

output "registry_lambda_arn" {
  description = "ARN of the Registry Lambda function"
  value       = aws_lambda_function.registry.arn
}

output "registry_lambda_invoke_arn" {
  description = "Invoke ARN of the Registry Lambda function"
  value       = aws_lambda_function.registry.invoke_arn
}

output "registry_lambda_name" {
  description = "Name of the Registry Lambda function"
  value       = aws_lambda_function.registry.function_name
}

output "proxy_lambda_arn" {
  description = "ARN of the Proxy Lambda function"
  value       = aws_lambda_function.proxy.arn
}

output "proxy_lambda_invoke_arn" {
  description = "Invoke ARN of the Proxy Lambda function"
  value       = aws_lambda_function.proxy.invoke_arn
}

output "proxy_lambda_name" {
  description = "Name of the Proxy Lambda function"
  value       = aws_lambda_function.proxy.function_name
}

output "admin_lambda_arn" {
  description = "ARN of the Admin Lambda function"
  value       = aws_lambda_function.admin.arn
}

output "admin_lambda_invoke_arn" {
  description = "Invoke ARN of the Admin Lambda function"
  value       = aws_lambda_function.admin.invoke_arn
}

output "admin_lambda_name" {
  description = "Name of the Admin Lambda function"
  value       = aws_lambda_function.admin.function_name
}
