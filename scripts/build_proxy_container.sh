#!/bin/bash
# Build the A2A Proxy container using Finch
#
# Usage:
#   ./scripts/build_proxy_container.sh [--push]
#
# Options:
#   --push    Push to ECR after building

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Configuration
IMAGE_NAME="a2a-gateway-proxy"
IMAGE_TAG="${IMAGE_TAG:-latest}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Building A2A Proxy Container${NC}"
echo "================================"

# Check if finch is available
if ! command -v finch &> /dev/null; then
    echo -e "${RED}Error: finch is not installed${NC}"
    echo "Install finch: https://github.com/runfinch/finch"
    exit 1
fi

# Build the container
echo -e "\n${YELLOW}Building container image...${NC}"
cd "$PROJECT_ROOT/src/lambdas"

finch build \
    -t "${IMAGE_NAME}:${IMAGE_TAG}" \
    -f proxy_container/Dockerfile \
    --platform linux/amd64 \
    .

echo -e "\n${GREEN}✓ Build successful${NC}"
echo "Image: ${IMAGE_NAME}:${IMAGE_TAG}"

# Test the container locally
echo -e "\n${YELLOW}Testing container locally...${NC}"

# Start container in background
CONTAINER_ID=$(finch run -d \
    -p 8080:8080 \
    -e AGENT_REGISTRY_TABLE=test-table \
    -e PERMISSIONS_TABLE=test-permissions \
    -e GATEWAY_DOMAIN=test.example.com \
    -e AWS_ACCESS_KEY_ID=test \
    -e AWS_SECRET_ACCESS_KEY=test \
    -e AWS_DEFAULT_REGION=us-east-1 \
    "${IMAGE_NAME}:${IMAGE_TAG}")

echo "Container started: $CONTAINER_ID"

# Wait for container to be ready
echo "Waiting for container to be ready..."
sleep 3

# Test health endpoint
echo "Testing health endpoint..."
HEALTH_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/health 2>/dev/null || echo "000")

if [ "$HEALTH_RESPONSE" = "200" ]; then
    echo -e "${GREEN}✓ Health check passed${NC}"
else
    echo -e "${RED}✗ Health check failed (HTTP $HEALTH_RESPONSE)${NC}"
    echo "Container logs:"
    finch logs "$CONTAINER_ID"
fi

# Stop and remove container
echo "Cleaning up test container..."
finch stop "$CONTAINER_ID" > /dev/null 2>&1 || true
finch rm "$CONTAINER_ID" > /dev/null 2>&1 || true

# Push to ECR if requested
if [ "$1" = "--push" ]; then
    echo -e "\n${YELLOW}Pushing to ECR...${NC}"
    
    # Get AWS account ID and region
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    AWS_REGION="${AWS_REGION:-us-east-1}"
    ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${IMAGE_NAME}"
    
    # Login to ECR
    aws ecr get-login-password --region "$AWS_REGION" | \
        finch login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
    
    # Create repository if it doesn't exist
    aws ecr describe-repositories --repository-names "$IMAGE_NAME" --region "$AWS_REGION" 2>/dev/null || \
        aws ecr create-repository --repository-name "$IMAGE_NAME" --region "$AWS_REGION"
    
    # Tag and push
    finch tag "${IMAGE_NAME}:${IMAGE_TAG}" "${ECR_REPO}:${IMAGE_TAG}"
    finch push "${ECR_REPO}:${IMAGE_TAG}"
    
    echo -e "${GREEN}✓ Pushed to ECR: ${ECR_REPO}:${IMAGE_TAG}${NC}"
fi

echo -e "\n${GREEN}Done!${NC}"
