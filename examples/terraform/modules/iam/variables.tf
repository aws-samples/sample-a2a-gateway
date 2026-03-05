variable "role_name" {
  description = "Name for the IAM execution role"
  type        = string
}

variable "account_id" {
  description = "AWS account ID"
  type        = string
}

variable "region" {
  description = "AWS region"
  type        = string
}

variable "ecr_repository_arn" {
  description = "ARN of the ECR repository this role needs access to"
  type        = string
}

variable "tags" {
  description = "Tags to apply to the role"
  type        = map(string)
  default     = {}
}
