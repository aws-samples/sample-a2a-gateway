variable "stack_name" {
  description = "Stack name used for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "oauth_scopes" {
  description = "List of OAuth scope definitions for the resource server"
  type = list(object({
    scope_name        = string
    scope_description = string
  }))
}
