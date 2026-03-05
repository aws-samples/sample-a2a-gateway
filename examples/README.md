# AgentCore A2A Example Agents

This example deploys two AI agents to Amazon Bedrock AgentCore Runtime using the A2A (Agent-to-Agent) protocol with Cognito OAuth authentication, managed entirely with Terraform. Use these agents to test the full A2A Gateway flow end-to-end.

## Overview

### Agents

| Agent | Description | Skill |
|-------|-------------|-------|
| **Weather Agent** | Answers weather-related questions using a custom weather tool | `weather` — returns mock weather data for any city |
| **Calculator Agent** | Performs arithmetic operations | `calculator` — evaluates math expressions via SymPy |

Both agents use the [Strands Agents SDK](https://github.com/strands-agents/strands-agents-python) with `BedrockAgentCoreApp` and are deployed as ARM64 containers to AgentCore Runtime.

### Terraform Modules

The Terraform configuration uses reusable modules under `terraform/modules/`:

| Module | Resources | Purpose |
|--------|-----------|---------|
| `modules/ecr` | ECR repository, lifecycle policy, repository policy | Container image storage (instantiated per agent) |
| `modules/iam` | IAM execution role + inline policy, managed policy attachment | AgentCore runtime permissions (instantiated per agent) |
| `modules/cognito` | User Pool, Resource Server, App Client, Domain | OAuth 2.0 `client_credentials` flow for machine-to-machine auth |
| `modules/agent-runtime` | `aws_bedrockagentcore_agent_runtime` | A2A agent runtime with JWT authorizer (instantiated per agent) |

Root-level files:

| File | Purpose |
|------|---------|
| `main.tf` | Wires modules together, container image build triggers (Docker) |
| `outputs.tf` | Runtime ARNs, Cognito credentials, backend URLs, test commands |
| `variables.tf` | Input variables |
| `versions.tf` | Provider versions (aws ~> 6.21) |


OAuth scopes:
- `a2a-gateway/weather:read` / `a2a-gateway/weather:write`
- `a2a-gateway/calculator:read` / `a2a-gateway/calculator:write`
- `a2a-gateway/gateway:admin`

## Prerequisites

- Terraform >= 1.6
- AWS CLI configured with credentials
- [Docker](https://www.docker.com/) installed (container runtime for building images)
- Access to Amazon Bedrock AgentCore (request access if needed)
- Python 3.11+ (for local testing)

## Step 1: Deploy the Agents

```bash
cd examples/terraform

# Configure variables
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars — set your region and preferences
```

Key variables in `terraform.tfvars`:

```hcl
aws_region            = "us-east-1"     # Your preferred region
stack_name            = "agentcore-a2a-sample"
weather_agent_name    = "WeatherAgent"
calculator_agent_name = "CalculatorAgent"
network_mode          = "PUBLIC"
image_tag             = "latest"
```

Deploy:

```bash
terraform init
terraform plan    # Review the resources
terraform apply   # Deploys ECR, builds images, creates runtimes + Cognito
```

Terraform will:
1. Create ECR repositories for both agents
2. Build ARM64 container images locally via Docker
3. Push images to ECR
4. Deploy AgentCore runtimes with A2A protocol and JWT authorization
5. Create a Cognito User Pool with OAuth scopes for access control

## Step 2: Verify the Deployment

After `terraform apply` completes, grab the key outputs:

```bash
# Agent runtime ARNs
terraform output weather_agent_runtime_arn
terraform output calculator_agent_runtime_arn

# OAuth credentials (needed for gateway registration)
terraform output cognito_client_id
terraform output -raw cognito_client_secret
terraform output cognito_token_endpoint
terraform output cognito_discovery_url
```

## Step 3: Invoke Agents Directly via A2A Protocol

You can invoke the deployed agents directly using the A2A protocol with your Cognito OAuth token — no gateway required.

### 3a. Get a Bearer Token from Cognito

```bash
TOKEN_ENDPOINT=$(terraform output -raw cognito_token_endpoint)
CLIENT_ID=$(terraform output -raw cognito_client_id)
CLIENT_SECRET=$(terraform output -raw cognito_client_secret)

TOKEN=$(curl -s -X POST "$TOKEN_ENDPOINT" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -u "$CLIENT_ID:$CLIENT_SECRET" \
  -d "grant_type=client_credentials&scope=a2a-gateway/weather:read a2a-gateway/weather:write" \
  | jq -r '.access_token')
```

### 3b. Retrieve the Agent Card (Optional)

Agent Cards describe the agent's identity, capabilities, and endpoint. You can fetch one to verify your agent is reachable:

```bash
WEATHER_ARN=$(terraform output -raw weather_agent_runtime_arn)
ENCODED_ARN=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$WEATHER_ARN', safe=''))")

curl -s "https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/$ENCODED_ARN/invocations/.well-known/agent-card.json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: $(uuidgen)" | jq .
```

### 3c. Send an A2A Message

Invoke the weather agent using the A2A JSON-RPC protocol:

```bash
curl -s -X POST \
  "https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/$ENCODED_ARN/invocations/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: $(uuidgen)" \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-001",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "What is the weather in Seattle?"}],
        "messageId": "12345678-1234-1234-1234-123456789012"
      }
    }
  }' | jq .
```

Key details:
- The endpoint format is `https://bedrock-agentcore.<REGION>.amazonaws.com/runtimes/<URL_ENCODED_ARN>/invocations/`
- The `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` header is required for session isolation — use a unique UUID per session
- The payload follows the [A2A JSON-RPC 2.0 specification](https://a2a-protocol.org/latest/specification/)

## Step 4: Wire into the A2A Gateway

With the agents deployed, register them with your existing A2A Gateway instance.

### 4a. Get Gateway Credentials

From the gateway's Terraform directory:

```bash
cd ../../terraform   # Back to the gateway terraform root

GATEWAY_URL=$(terraform output -raw api_gateway_url)
TOKEN_ENDPOINT=$(terraform output -raw cognito_token_endpoint)
CLIENT_ID=$(terraform output -raw cognito_client_id)
CLIENT_SECRET=$(terraform output -raw cognito_client_secret)

# Get an admin JWT
TOKEN_RESPONSE=$(curl -s -X POST "$TOKEN_ENDPOINT" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=$CLIENT_ID&client_secret=$CLIENT_SECRET&scope=a2a-gateway/gateway:admin")

export JWT=$(echo "$TOKEN_RESPONSE" | jq -r .access_token)
```

### 4b. Get Agent Outputs

From the example agents' Terraform directory:

```bash
cd ../examples/terraform

# Agent backend URLs (AgentCore invocation endpoints)
WEATHER_BACKEND=$(terraform output -raw weather_agent_backend_url)
WEATHER_CARD=$(terraform output -raw weather_agent_card_url)
CALC_BACKEND=$(terraform output -raw calculator_agent_backend_url)
CALC_CARD=$(terraform output -raw calculator_agent_card_url)

# Agent OAuth credentials (for the gateway to authenticate with agents)
AGENT_TOKEN_ENDPOINT=$(terraform output -raw cognito_token_endpoint)
AGENT_CLIENT_ID=$(terraform output -raw cognito_client_id)
AGENT_CLIENT_SECRET=$(terraform output -raw cognito_client_secret)
```

### 4c. Register the Weather Agent

```bash
curl -X POST "$GATEWAY_URL/admin/agents/register" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d "{
    \"agentId\": \"weather-agent\",
    \"name\": \"Weather Agent\",
    \"backendUrl\": \"$WEATHER_BACKEND\",
    \"agentCardUrl\": \"$WEATHER_CARD\",
    \"authConfig\": {
      \"type\": \"oauth2_client_credentials\",
      \"tokenUrl\": \"$AGENT_TOKEN_ENDPOINT\",
      \"clientId\": \"$AGENT_CLIENT_ID\",
      \"clientSecret\": \"$AGENT_CLIENT_SECRET\",
      \"scopes\": [\"a2a-gateway/weather:read\"]
    }
  }"
```

### 4d. Register the Calculator Agent

```bash
curl -X POST "$GATEWAY_URL/admin/agents/register" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d "{
    \"agentId\": \"calculator-agent\",
    \"name\": \"Calculator Agent\",
    \"backendUrl\": \"$CALC_BACKEND\",
    \"agentCardUrl\": \"$CALC_CARD\",
    \"authConfig\": {
      \"type\": \"oauth2_client_credentials\",
      \"tokenUrl\": \"$AGENT_TOKEN_ENDPOINT\",
      \"clientId\": \"$AGENT_CLIENT_ID\",
      \"clientSecret\": \"$AGENT_CLIENT_SECRET\",
      \"scopes\": [\"a2a-gateway/calculator:read\"]
    }
  }"
```

### 4e. Update Gateway Permissions

After registering the agents, you must add their IDs to the gateway's DynamoDB permissions table. Without this, the gateway's authorizer will deny access to the new agents.

The permissions table name follows the pattern `{project_name}-{environment}-permissions` (as defined in the gateway's Terraform). It uses `scope` as the partition key and stores an `allowedAgents` list of agent ID strings.

Add `weather-agent` and `calculator-agent` to the `allowedAgents` list for the scope your JWT token carries. If you used the `gateway:admin` scope in Step 4a, update that entry:

```bash
# From the gateway terraform directory
cd ../../terraform

PERMISSIONS_TABLE="$(terraform output -raw permissions_table_name)"

aws dynamodb put-item \
  --table-name "$PERMISSIONS_TABLE" \
  --item '{
    "scope": {"S": "gateway:admin"},
    "allowedAgents": {"L": [{"S": "weather-agent"}, {"S": "calculator-agent"}]},
    "description": {"S": "Admin scope with access to all agents"}
  }'
```

> You can also update the item directly in the [DynamoDB console](https://console.aws.amazon.com/dynamodbv2/) — find the permissions table, locate the `gateway:admin` item, and edit the `allowedAgents` list.

### 4f. Test Through the Gateway

```bash
# Discover registered agents
curl "$GATEWAY_URL/agents" \
  -H "Authorization: Bearer $JWT" | jq '.[].name'

# Send a message to the weather agent via the gateway
curl -X POST "$GATEWAY_URL/agents/weather-agent/message:send" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "messageId": "test-001",
      "role": "ROLE_USER",
      "parts": [{"text": "What is the weather in New York?"}]
    }
  }' | jq .

# Send a message to the calculator agent
curl -X POST "$GATEWAY_URL/agents/calculator-agent/message:send" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "messageId": "test-002",
      "role": "ROLE_USER",
      "parts": [{"text": "What is 256 * 37?"}]
    }
  }' | jq .
```

## Cleanup

Destroy the example agents (does not affect the gateway):

```bash
cd examples/terraform
terraform destroy
```

## File Structure

```
examples/
├── agent-weather-code/          # Weather agent source
│   ├── agent.py                 # Strands agent with weather tool
│   ├── Dockerfile
│   └── requirements.txt
├── agent-calculator-code/       # Calculator agent source
│   ├── agent.py                 # Strands agent with calculator tool
│   ├── Dockerfile
│   └── requirements.txt
└── terraform/
    ├── main.tf                  # Module wiring + build triggers (Docker)
    ├── outputs.tf               # Runtime ARNs, Cognito creds, test commands
    ├── variables.tf             # Input variables
    ├── versions.tf              # Provider versions (aws ~> 6.21)
    ├── terraform.tfvars         # Your configuration
    ├── terraform.tfvars.example # Example configuration template
    ├── modules/
    │   ├── cognito/             # User Pool + OAuth client_credentials config
    │   │   ├── main.tf
    │   │   ├── variables.tf
    │   │   └── outputs.tf
    │   ├── ecr/                 # ECR repository (per agent)
    │   │   ├── main.tf
    │   │   ├── variables.tf
    │   │   └── outputs.tf
    │   ├── iam/                 # Execution role (per agent)
    │   │   ├── main.tf
    │   │   ├── variables.tf
    │   │   └── outputs.tf
    │   └── agent-runtime/       # AgentCore A2A runtime (per agent)
    │       ├── main.tf
    │       ├── variables.tf
    │       └── outputs.tf
    └── scripts/
        └── build-image.sh       # Docker build + ECR push script
```
