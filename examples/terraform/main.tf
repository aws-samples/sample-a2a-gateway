data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# ============================================================================
# Cognito — OAuth 2.0 for A2A agent authentication
# ============================================================================

module "cognito" {
  source = "./modules/cognito"

  stack_name  = var.stack_name
  environment = var.environment

  oauth_scopes = [
    { scope_name = "weather:read", scope_description = "Read access to weather agent" },
    { scope_name = "weather:write", scope_description = "Write access to weather agent" },
    { scope_name = "calculator:read", scope_description = "Read access to calculator agent" },
    { scope_name = "calculator:write", scope_description = "Write access to calculator agent" },
    { scope_name = "gateway:admin", scope_description = "Admin access to gateway management" },
  ]
}

# ============================================================================
# ECR Repositories — one per agent
# ============================================================================

module "ecr_weather" {
  source = "./modules/ecr"

  repository_name = "${var.stack_name}-${var.ecr_repository_name}-weather"
  account_id      = data.aws_caller_identity.current.id
  tags            = { Name = "${var.stack_name}-weather-ecr" }
}

module "ecr_calculator" {
  source = "./modules/ecr"

  repository_name = "${var.stack_name}-${var.ecr_repository_name}-calculator"
  account_id      = data.aws_caller_identity.current.id
  tags            = { Name = "${var.stack_name}-calculator-ecr" }
}

# ============================================================================
# IAM Execution Roles — one per agent
# ============================================================================

module "iam_weather" {
  source = "./modules/iam"

  role_name          = "${var.stack_name}-weather-execution-role"
  account_id         = data.aws_caller_identity.current.id
  region             = data.aws_region.current.id
  ecr_repository_arn = module.ecr_weather.repository_arn
  tags               = { Name = "${var.stack_name}-weather-execution-role" }
}

module "iam_calculator" {
  source = "./modules/iam"

  role_name          = "${var.stack_name}-calculator-execution-role"
  account_id         = data.aws_caller_identity.current.id
  region             = data.aws_region.current.id
  ecr_repository_arn = module.ecr_calculator.repository_arn
  tags               = { Name = "${var.stack_name}-calculator-execution-role" }
}

# ============================================================================
# Container Image Builds — wait for IAM, then build in parallel
# ============================================================================

resource "time_sleep" "wait_for_iam" {
  depends_on      = [module.iam_weather, module.iam_calculator]
  create_duration = "10s"
}

resource "null_resource" "build_weather" {
  triggers = {
    image_tag       = var.image_tag
    ecr_repository  = module.ecr_weather.repository_id
    source_code_md5 = md5(join("", [for f in fileset("${path.module}/../agent-weather-code", "**") : filemd5("${path.module}/../agent-weather-code/${f}")]))
  }

  provisioner "local-exec" {
    command = "${path.module}/scripts/build-image.sh \"${data.aws_region.current.id}\" \"${module.ecr_weather.repository_url}\" \"${var.image_tag}\" \"${path.module}/../agent-weather-code\""
  }

  depends_on = [module.ecr_weather, time_sleep.wait_for_iam]
}

resource "null_resource" "build_calculator" {
  triggers = {
    image_tag       = var.image_tag
    ecr_repository  = module.ecr_calculator.repository_id
    source_code_md5 = md5(join("", [for f in fileset("${path.module}/../agent-calculator-code", "**") : filemd5("${path.module}/../agent-calculator-code/${f}")]))
  }

  provisioner "local-exec" {
    command = "${path.module}/scripts/build-image.sh \"${data.aws_region.current.id}\" \"${module.ecr_calculator.repository_url}\" \"${var.image_tag}\" \"${path.module}/../agent-calculator-code\""
  }

  depends_on = [module.ecr_calculator, time_sleep.wait_for_iam]
}

# ============================================================================
# Agent Runtimes — A2A protocol with Cognito JWT auth
# ============================================================================

module "weather_runtime" {
  source = "./modules/agent-runtime"

  agent_runtime_name = "${replace(var.stack_name, "-", "_")}_${var.weather_agent_name}"
  description        = "Weather agent with A2A protocol for ${var.stack_name}"
  role_arn           = module.iam_weather.role_arn
  container_uri      = "${module.ecr_weather.repository_url}:${var.image_tag}"
  network_mode       = var.network_mode
  discovery_url      = module.cognito.discovery_url
  allowed_clients    = [module.cognito.client_id]
  region             = data.aws_region.current.id

  tags = {
    Name  = "${var.stack_name}-weather-runtime"
    Agent = "Weather"
  }

  depends_on = [null_resource.build_weather, module.cognito]
}

module "calculator_runtime" {
  source = "./modules/agent-runtime"

  agent_runtime_name = "${replace(var.stack_name, "-", "_")}_${var.calculator_agent_name}"
  description        = "Calculator agent with A2A protocol for ${var.stack_name}"
  role_arn           = module.iam_calculator.role_arn
  container_uri      = "${module.ecr_calculator.repository_url}:${var.image_tag}"
  network_mode       = var.network_mode
  discovery_url      = module.cognito.discovery_url
  allowed_clients    = [module.cognito.client_id]
  region             = data.aws_region.current.id

  tags = {
    Name  = "${var.stack_name}-calculator-runtime"
    Agent = "Calculator"
  }

  depends_on = [null_resource.build_calculator, module.cognito]
}
