output "agent_runtime_id" {
  description = "ID of the agent runtime"
  value       = aws_bedrockagentcore_agent_runtime.a2a_agent.agent_runtime_id
}

output "agent_runtime_arn" {
  description = "ARN of the agent runtime"
  value       = aws_bedrockagentcore_agent_runtime.a2a_agent.agent_runtime_arn
}

output "backend_url" {
  description = "AgentCore runtime invocations endpoint"
  value       = local.base_url
}

output "agent_card_url" {
  description = "Agent Card URL for A2A discovery"
  value       = "${local.base_url}/.well-known/agent-card.json"
}
