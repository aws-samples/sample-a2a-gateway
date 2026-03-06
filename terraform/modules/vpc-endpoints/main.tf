# VPC Endpoints for A2A Gateway
# Standalone module following the terraform-aws-modules/vpc//modules/vpc-endpoints
# composition pattern. Accepts vpc_id, subnet_ids, etc. from any source — works
# with both the gateway's own VPC module and user-provided (BYOVPC) infrastructure.

data "aws_region" "current" {}

# ─── Gateway Endpoints (free, route-table based) ───────────────────────────────

resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id            = var.vpc_id
  service_name      = "com.amazonaws.${data.aws_region.current.name}.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = var.route_table_ids

  tags = { Name = "${var.project_name}-${var.environment}-dynamodb-vpce" }
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = var.vpc_id
  service_name      = "com.amazonaws.${data.aws_region.current.name}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = var.route_table_ids

  tags = { Name = "${var.project_name}-${var.environment}-s3-vpce" }
}

# ─── Interface Endpoints ───────────────────────────────────────────────────────

resource "aws_vpc_endpoint" "secretsmanager" {
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.secretsmanager"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.subnet_ids
  security_group_ids  = var.security_group_ids
  private_dns_enabled = true

  tags = { Name = "${var.project_name}-${var.environment}-secretsmanager-vpce" }
}

resource "aws_vpc_endpoint" "execute_api" {
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.execute-api"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.subnet_ids
  security_group_ids  = var.security_group_ids
  private_dns_enabled = true

  tags = { Name = "${var.project_name}-${var.environment}-execute-api-vpce" }
}

resource "aws_vpc_endpoint" "logs" {
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.logs"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.subnet_ids
  security_group_ids  = var.security_group_ids
  private_dns_enabled = true

  tags = { Name = "${var.project_name}-${var.environment}-logs-vpce" }
}

resource "aws_vpc_endpoint" "ecr_api" {
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.ecr.api"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.subnet_ids
  security_group_ids  = var.security_group_ids
  private_dns_enabled = true

  tags = { Name = "${var.project_name}-${var.environment}-ecr-api-vpce" }
}

resource "aws_vpc_endpoint" "ecr_dkr" {
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.ecr.dkr"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.subnet_ids
  security_group_ids  = var.security_group_ids
  private_dns_enabled = true

  tags = { Name = "${var.project_name}-${var.environment}-ecr-dkr-vpce" }
}

resource "aws_vpc_endpoint" "s3vectors" {
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.s3vectors"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.subnet_ids
  security_group_ids  = var.security_group_ids
  private_dns_enabled = true

  tags = { Name = "${var.project_name}-${var.environment}-s3vectors-vpce" }
}

resource "aws_vpc_endpoint" "bedrock_runtime" {
  count               = var.enable_bedrock_endpoint ? 1 : 0
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.bedrock-runtime"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.subnet_ids
  security_group_ids  = var.security_group_ids
  private_dns_enabled = true

  tags = { Name = "${var.project_name}-${var.environment}-bedrock-runtime-vpce" }
}
