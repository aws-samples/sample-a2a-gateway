#!/bin/bash
# Deploy the async test agent to AgentCore Runtime
# Prerequisites: AWS credentials for account 670015436176, Docker running

set -e

REGION="us-east-1"
ACCOUNT_ID="670015436176"
STACK_NAME="agentcore-a2a-sample"
AGENT_NAME="AsyncTestAgent"
ECR_REPO="${STACK_NAME}-a2a-agents-async"
IMAGE_TAG="latest"
RUNTIME_NAME="${STACK_NAME//-/_}_${AGENT_NAME}"

# Reuse the existing Cognito and IAM from the examples stack
# You'll need the discovery URL and an execution role ARN
DISCOVERY_URL="https://cognito-idp.us-east-1.amazonaws.com/us-east-1_BmN1yIHic/.well-known/openid-configuration"
COGNITO_CLIENT_ID="71fac62cqhok6an4spkv9e6t4j"

echo "=== Step 1: Create ECR repository ==="
aws ecr create-repository --repository-name "$ECR_REPO" --region "$REGION" 2>/dev/null || echo "Repository already exists"

echo ""
echo "=== Step 2: Build and push container ==="
ECR_URL="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
docker build -t "${ECR_URL}:${IMAGE_TAG}" "$SCRIPT_DIR"
docker push "${ECR_URL}:${IMAGE_TAG}"

echo ""
echo "=== Step 3: Create AgentCore Runtime ==="
echo "Runtime name: $RUNTIME_NAME"
echo "Container: ${ECR_URL}:${IMAGE_TAG}"
echo ""
echo "Use the existing execution role from the examples stack."
echo "Find it with:"
echo "  aws iam list-roles --query \"Roles[?contains(RoleName,'execution-role')].[RoleName,Arn]\" --output table"
echo ""
echo "Then create the runtime with:"
echo "  aws bedrock-agent-runtime create-agent-runtime \\"
echo "    --agent-runtime-name $RUNTIME_NAME \\"
echo "    --description 'Async test agent with task lifecycle support' \\"
echo "    --role-arn ROLE_ARN_HERE \\"
echo "    --agent-runtime-artifact '{\"containerConfiguration\":{\"containerUri\":\"${ECR_URL}:${IMAGE_TAG}\"}}' \\"
echo "    --network-configuration '{\"networkMode\":\"PUBLIC\"}' \\"
echo "    --protocol-configuration '{\"serverProtocol\":\"A2A\"}' \\"
echo "    --authorizer-configuration '{\"customJwtAuthorizer\":{\"discoveryUrl\":\"${DISCOVERY_URL}\",\"allowedClients\":[\"${COGNITO_CLIENT_ID}\"]}}' \\"
echo "    --region $REGION"
echo ""
echo "=== Step 4: Register with gateway ==="
echo "Once the runtime is created, get the runtime ARN and register with the gateway:"
echo ""
echo "  RUNTIME_ARN=\$(aws bedrock-agent-runtime get-agent-runtime --agent-runtime-name $RUNTIME_NAME --region $REGION --query 'agentRuntimeArn' --output text)"
echo "  BACKEND_URL=\"https://bedrock-agentcore.${REGION}.amazonaws.com/runtimes/\$(python3 -c \"import urllib.parse; print(urllib.parse.quote('\$RUNTIME_ARN', safe=''))\"/invocations\""
echo ""
echo "Then call the gateway admin API to register it."
