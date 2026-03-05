variable "repository_name" {
  description = "Full name for the ECR repository"
  type        = string
}

variable "account_id" {
  description = "AWS account ID for repository policy"
  type        = string
}

variable "tags" {
  description = "Tags to apply to the repository"
  type        = map(string)
  default     = {}
}
