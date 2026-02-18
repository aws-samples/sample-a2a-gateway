# A2A Gateway

by Reilly Manton

A production-ready, serverless A2A gateway that provides the complete three-layer architecture required for enterprise agent deployments: management, control, and data layers.

## Why This Matters

Amazon Bedrock AgentCore provides a complete gateway solution for MCP (Model Context Protocol) with management, access control, and data proxying. However, AgentCore has no native support for A2A (Agent-to-Agent) protocol. Existing A2A solutions only implement a management layer (agent discovery/registry) but lack the control and data layers, rendering them ineffective for corporate environments where security, access control, and centralized routing are critical.

This gateway fills that gap by implementing all three layers:

### The Three-Layer Architecture

**Management Layer** - Agent Discovery & Registry
- Centralized agent registry with metadata and capabilities
- Dynamic agent card caching and URL rewriting
- Agent lifecycle management (register, sync, activate/deactivate)
- Multi-backend support (standard A2A + Bedrock AgentCore)

**Control Layer** - Fine-Grained Access Control (FGAC)
- JWT-based authentication via Cognito
- Scope-based permissions (who can access which agents)
- Lambda authorizer for request-level authorization
- Audit trail through CloudWatch logs

**Data Layer** - Centralized Request Proxying
- Single domain endpoint for all agents (`/agents/{agentId}`)
- OAuth 2.0 client credentials flow for backend authentication
- SSE streaming support for real-time responses
- Request/response transformation and validation

## What This Does

The gateway hosts multiple A2A agents at a single domain with path-based routing (`/agents/{agentId}`). Each path acts as an independent A2A server from the client's perspective - **standard A2A clients work without modification**.

**Key Features**:
- ✅ Fully A2A protocol compliant
- ✅ Fine-grained access control via Cognito JWT scopes
- ✅ SSE streaming support for `message:stream` operations
- ✅ OAuth 2.0 Client Credentials flow for backend authentication
- ✅ Serverless architecture (API Gateway + Lambda + DynamoDB)
- ✅ Native support for AWS Bedrock AgentCore Runtime backends
- ✅ Automatic protocol translation (HTTP A2A ↔ JSON-RPC for Bedrock)

## Architecture

```
┌─────────────────────────────────────────┐
│         A2A Clients                     │
│  (Standard A2A SDK or HTTP client)      │
└────────────┬────────────────────────────┘
             │ HTTPS + JWT Bearer
             │
┌────────────▼────────────────────────────┐
│    API Gateway (REST API)               │
│    + Lambda Authorizer                  │
│                                         │
│  GET  /agents          → Registry λ     │
│  ANY  /agents/{proxy+} → Proxy λ        │
│  POST /admin/*         → Admin λ        │
└────────────┬────────────────────────────┘
             │
      ┌──────┴──────┬──────────────┐
      │             │              │
┌─────▼─────┐ ┌────▼──────┐ ┌────▼──────┐
│ Registry  │ │  Proxy    │ │  Admin    │
│  Lambda   │ │  Lambda   │ │  Lambda   │
└─────┬─────┘ └────┬──────┘ └────┬──────┘
      │            │              │
      └────┬───────┴──────────────┘
           │
┌──────────▼──────────────────────────────┐
│         DynamoDB + Secrets Manager      │
└──────────┬──────────────────────────────┘
           │
┌──────────▼──────────────────────────────┐
│      Backend A2A Servers                │
└─────────────────────────────────────────┘
```

### Components

**API Gateway (REST API)**
- Two static routes that never change when agents are added/removed
- Lambda authorizer for JWT validation and FGAC
- Response streaming enabled for SSE support

**Lambda Functions**
- **Authorizer**: JWT validation, extracts user context (scopes, roles)
- **Registry**: Agent discovery with permission filtering
- **Proxy**: Routes A2A requests to backends with OAuth authentication
- **Admin**: Agent registration and management

**DynamoDB Tables**
- **AgentRegistry**: Maps agent IDs to backend URLs, auth configs, cached agent cards
- **Permissions**: Maps user scopes to allowed agents

**Secrets Manager**
- Stores OAuth client secrets for backend authentication
- Secrets referenced by ARN, never stored in DynamoDB

### A2A Operations Supported

All standard A2A operations work through the gateway:

- `POST /agents/{agentId}/message:send` - Send message (buffered)
- `POST /agents/{agentId}/message:stream` - Send message (SSE streaming)
- `GET /agents/{agentId}/.well-known/agent-card.json` - Get Agent Card
- `GET /agents/{agentId}/tasks` - List tasks
- `GET /agents/{agentId}/tasks/{taskId}` - Get task status
- `POST /agents/{agentId}/tasks/{taskId}:cancel` - Cancel task

### Backend Support

The gateway supports two types of A2A backends:

**Standard A2A Servers**

Standard HTTP-based A2A servers that implement the A2A protocol directly. The gateway forwards HTTP requests as-is with OAuth authentication.

**AWS Bedrock AgentCore Runtime**

The gateway provides native support for agents deployed on AWS Bedrock AgentCore Runtime. It automatically:

1. **Detects Bedrock backends** - Identifies backends by URL pattern (`bedrock-agentcore`)
2. **Protocol translation** - Converts HTTP A2A to JSON-RPC format:
   - `message:send` → `message/send` (colon to slash)
   - Wraps requests in JSON-RPC envelopes
3. **Format transformation** - Adapts A2A conventions to Bedrock format:
   - `ROLE_USER` → `user`
   - `ROLE_AGENT` → `agent`
4. **Session management** - Adds required `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` headers
5. **Endpoint routing** - Routes all operations to `/invocations` endpoint

This means standard A2A clients can seamlessly interact with Bedrock AgentCore agents through the gateway without any client-side changes.

## Quick Start

### Prerequisites

- Terraform >= 1.5.0
- Python 3.12
- AWS CLI configured
- S3 bucket for Terraform state

### 1. Configure Terraform Backend (for remote tfstate)

Edit `terraform/backend.tf` - uncomment and set your S3 bucket:

```hcl
terraform {
  backend "s3" {
    bucket         = "your-terraform-state-bucket"
    key            = "a2a-gateway/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
  }
}
```

### 2. Set Variables

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` (set your region and naming preferences):
```hcl
aws_region   = "us-east-1"  # or your preferred region
project_name = "a2a-gateway"
environment  = "poc"
```

### 3. Deploy (Single Step!)

```bash
terraform init
terraform plan  # Review what will be created
terraform apply
```

This creates everything in one go:
- DynamoDB tables (AgentRegistry, Permissions)
- Cognito User Pool
- 4 Lambda functions (Authorizer, Registry, Proxy, Admin)
- API Gateway with Lambda Authorizer
- IAM roles and policies
- Secrets Manager setup
- Automatically updates Lambda env vars with the API Gateway URL

### 4. (Optional) Seed Example Permissions

```bash
cd ..
python3 scripts/seed_permissions.py <permissions-table-name> us-east-1
```

Get the table name from Terraform outputs: `terraform output permissions_table_name`

## Using the Gateway

### 1. Get Authentication Token

Export your gateway URL and obtain a JWT token:

```bash
# Get gateway configuration
GATEWAY_URL=$(cd terraform && terraform output -raw api_gateway_url)
TOKEN_ENDPOINT=$(cd terraform && terraform output -raw cognito_token_endpoint)
CLIENT_ID=$(cd terraform && terraform output -raw cognito_client_id)
CLIENT_SECRET=$(cd terraform && terraform output -raw cognito_client_secret)

# Obtain JWT with required scopes
TOKEN_RESPONSE=$(curl -s -X POST $TOKEN_ENDPOINT \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=$CLIENT_ID&client_secret=$CLIENT_SECRET&scope=a2a-gateway/gateway:admin a2a-gateway/billing:read")

export JWT=$(echo $TOKEN_RESPONSE | jq -r .access_token)
echo "JWT obtained: ${JWT:0:50}..."
```

### 2. Register Backend Agents

The gateway supports two types of A2A backends:

#### Standard A2A Server

```bash
curl -X POST $GATEWAY_URL/admin/agents/register \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "agentId": "my-agent",
    "name": "My Custom Agent",
    "backendUrl": "https://your-backend.example.com",
    "agentCardUrl": "https://your-backend.example.com/.well-known/agent-card.json",
    "authConfig": {
      "type": "oauth2_client_credentials",
      "tokenUrl": "https://your-auth.example.com/oauth/token",
      "clientId": "your-client-id",
      "clientSecret": "your-client-secret",
      "scopes": ["agent:invoke"]
    }
  }'
```

#### AWS Bedrock AgentCore Runtime

```bash
# URL-encode your agent ARN
AGENT_ARN="arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/my-agent-xyz"
ENCODED_ARN=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$AGENT_ARN', safe=''))")

curl -X POST $GATEWAY_URL/admin/agents/register \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d "{
    \"agentId\": \"bedrock-agent\",
    \"name\": \"Bedrock Calculator Agent\",
    \"backendUrl\": \"https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/${ENCODED_ARN}/invocations\",
    \"agentCardUrl\": \"https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/${ENCODED_ARN}/invocations/.well-known/agent-card.json\",
    \"authConfig\": {
      \"type\": \"oauth2_client_credentials\",
      \"tokenUrl\": \"https://your-cognito-domain.auth.us-east-1.amazoncognito.com/oauth2/token\",
      \"clientId\": \"your-bedrock-client-id\",
      \"clientSecret\": \"your-bedrock-client-secret\",
      \"scopes\": [\"your-resource-server/read\", \"your-resource-server/write\"]
    }
  }"
```

**Note**: The gateway automatically detects Bedrock AgentCore backends and handles protocol translation transparently.

### 3. Discover Agents

List all agents you have access to:

```bash
curl $GATEWAY_URL/agents \
  -H "Authorization: Bearer $JWT" | jq .
```

Example response:
```json
[
  {
    "name": "Calculator Agent",
    "description": "A calculator agent that can perform basic arithmetic operations.",
    "url": "https://your-gateway.execute-api.us-east-1.amazonaws.com/v1/agents/bedrock-agent",
    "protocolVersion": "0.3.0",
    "skills": [
      {
        "id": "calculator",
        "name": "calculator",
        "description": "Calculator powered by SymPy..."
      }
    ],
    "capabilities": {
      "streaming": true
    }
  }
]
```

### 4. Get Agent Card

Fetch a specific agent's capabilities:

```bash
curl $GATEWAY_URL/agents/bedrock-agent/.well-known/agent-card.json \
  -H "Authorization: Bearer $JWT" | jq .
```

### 5. Send Messages to Agents

Send a message to an agent (buffered response):

```bash
curl -X POST $GATEWAY_URL/agents/bedrock-agent/message:send \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "messageId": "msg-123",
      "role": "ROLE_USER",
      "parts": [{"text": "Calculate 2 + 2"}]
    }
  }' | jq .
```

Example response (streaming chunks from Bedrock AgentCore):
```json
[
  {
    "contextId": "a1a7915d-078b-478c-a7b5-9c23a4883a8c",
    "kind": "message",
    "messageId": "b8f185a5-fecd-4736-be3c-4d48806e66c2",
    "parts": [{"kind": "text", "text": "The result of"}],
    "role": "agent",
    "taskId": "5be2cf00-6c20-4e2f-a4d4-7e0f90f47c8f"
  },
  {
    "contextId": "a1a7915d-078b-478c-a7b5-9c23a4883a8c",
    "kind": "message",
    "messageId": "fbb7e32e-bfee-439b-8bca-9b2f50f227ad",
    "parts": [{"kind": "text", "text": " 2 + 2 is"}],
    "role": "agent",
    "taskId": "5be2cf00-6c20-4e2f-a4d4-7e0f90f47c8f"
  },
  {
    "contextId": "a1a7915d-078b-478c-a7b5-9c23a4883a8c",
    "kind": "message",
    "messageId": "ad214099-d7d2-4b3e-931b-e363a4edde84",
    "parts": [{"kind": "text", "text": " **4**."}],
    "role": "agent",
    "taskId": "5be2cf00-6c20-4e2f-a4d4-7e0f90f47c8f"
  }
]
```

### 6. Stream Responses

For streaming responses (SSE):

```bash
curl -X POST $GATEWAY_URL/agents/bedrock-agent/message:stream \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "messageId": "msg-456",
      "role": "ROLE_USER",
      "parts": [{"text": "What is 101 * 11?"}]
    }
  }'
```

### Complete Workflow Example

```bash
# 1. Get JWT
TOKEN_RESPONSE=$(curl -s -X POST $TOKEN_ENDPOINT \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=$CLIENT_ID&client_secret=$CLIENT_SECRET&scope=a2a-gateway/gateway:admin a2a-gateway/billing:read")
export JWT=$(echo $TOKEN_RESPONSE | jq -r .access_token)

# 2. Discover agents
curl $GATEWAY_URL/agents -H "Authorization: Bearer $JWT" | jq '.[].name'

# 3. Get agent card
curl $GATEWAY_URL/agents/bedrock-agent/.well-known/agent-card.json \
  -H "Authorization: Bearer $JWT" | jq '.skills[].name'

# 4. Send message
curl -X POST $GATEWAY_URL/agents/bedrock-agent/message:send \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "messageId": "msg-001",
      "role": "ROLE_USER",
      "parts": [{"text": "Calculate the square root of 144"}]
    }
  }' | jq '.[].parts[].text' | tr -d '\n' && echo
```

## Running Tests

```bash
# Install dependencies
pip install -r src/requirements.txt

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src/lambdas --cov-report=html

# Run only unit tests
pytest tests/unit/ -v

# Run only property tests
pytest tests/property/ -v -m property_test
```

## Admin Operations

- `POST /admin/agents/register` - Register new backend agent
- `POST /admin/agents/{agentId}/sync` - Refresh Agent Card cache
- `PATCH /admin/agents/{agentId}/status` - Set agent active/inactive

## A2A Protocol Compliance

This gateway implements core A2A messaging operations. Below is the full compliance status:

| Operation | Endpoint | Status | Notes |
|-----------|----------|--------|-------|
| **Agent Discovery** | `GET /agents` | ✅ Supported | Registry with permission filtering |
| **Get Agent Card** | `GET /agents/{id}/.well-known/agent-card.json` | ✅ Supported | Cached with URL rewriting |
| **Send Message** | `POST /agents/{id}/message:send` | ✅ Supported | Buffered response |
| **Stream Message** | `POST /agents/{id}/message:stream` | ⚠️ Buffered | SSE supported but buffered, not real-time |
| **Get Task** | `GET /tasks/{id}` | ❌ Not Implemented | |
| **List Tasks** | `GET /tasks` | ❌ Not Implemented | |
| **Cancel Task** | `POST /tasks/{id}:cancel` | ❌ Not Implemented | |
| **Subscribe to Task** | `POST /tasks/{id}:subscribe` | ❌ Not Implemented | |
| **Push Notifications** | `POST /tasks/{id}/pushNotificationConfigs` | ❌ Not Implemented | Webhook-based async updates |
| **Extended Agent Card** | `GET /extendedAgentCard` | ❌ Not Implemented | User-specific capabilities |

### Known Limitations

**Streaming Response Buffering**: The `message:stream` endpoint buffers the complete SSE stream from backends before returning all events at once. True streaming requires Lambda response streaming with `streamifyResponse` wrapper. For production real-time streaming, consider WebSocket API or EC2/ECS proxying.

**Task Management**: Task lifecycle operations (get, list, cancel, subscribe) are not implemented. The gateway focuses on stateless message proxying rather than task state management.

## Troubleshooting

**"Unauthorized" errors**: Check your JWT is valid and not expired. Tokens expire after 60 minutes.

**"Permission denied"**: Make sure you've seeded permissions and your JWT has the right scopes. Check with:
```bash
echo $JWT | cut -d. -f2 | base64 -d | jq .
```

**Agent not found**: Verify the agent is registered and status is "active":
```bash
aws dynamodb get-item \
  --table-name <agent-registry-table> \
  --key '{"agentId": {"S": "test-agent"}}'
```

**Backend connection fails**: Check CloudWatch logs for the Proxy Lambda. Verify OAuth credentials are correct.

## Project Structure

```
/terraform          - Infrastructure as Code
  /modules
    /dynamodb       - Tables
    /cognito        - Auth
    /lambda-functions - All Lambdas
    /api-gateway    - REST API
/src/lambdas
  /authorizer       - JWT validation
  /registry         - Agent discovery
  /proxy            - A2A routing (THE CRITICAL ONE)
  /admin            - Agent management
  /shared           - Common utilities
/tests
  /unit             - Unit tests
  /property         - Property-based tests
/scripts            - Helper scripts
```

## Clean Up

```bash
cd terraform
terraform destroy
```

Note: You may need to manually delete secrets from Secrets Manager if they're not fully deleted.

## License

MIT
