terraform {
  # Uncomment and configure the S3 backend for remote state storage:
  # backend "s3" {
  #   bucket         = "your-terraform-state-bucket"
  #   key            = "a2a-gateway/terraform.tfstate"
  #   region         = "us-east-1"
  #   # dynamodb_table = "terraform-state-lock"  # Optional: only needed for team collaboration
  #   encrypt        = true
  # }

  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.33"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = merge(
      {
        Project     = var.project_name
        Environment = var.environment
        ManagedBy   = "Terraform"
      },
      var.tags
    )
  }
}
