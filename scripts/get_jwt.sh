#!/bin/bash
# Helper script to get a JWT token from Cognito

set -e

cd "$(dirname "$0")/../terraform"

echo "=== Getting Cognito credentials from Terraform ==="
CLIENT_ID=$(terraform output -raw cognito_client_id)
CLIENT_SECRET=$(terraform output -raw cognito_client_secret)
TOKEN_ENDPOINT=$(terraform output -raw cognito_token_endpoint)

echo ""
echo "=== Requesting JWT token ==="
echo "Scopes: billing:read, billing:write, gateway:admin"
echo ""

TOKEN_RESPONSE=$(curl -s -X POST $TOKEN_ENDPOINT \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=$CLIENT_ID&client_secret=$CLIENT_SECRET&scope=a2a-gateway/billing:read a2a-gateway/billing:write a2a-gateway/gateway:admin")

JWT=$(echo $TOKEN_RESPONSE | jq -r .access_token)

if [ "$JWT" = "null" ] || [ -z "$JWT" ]; then
  echo "ERROR: Failed to get token"
  echo "Response: $TOKEN_RESPONSE"
  exit 1
fi

echo "✓ Token obtained successfully"
echo ""
echo "JWT=$JWT"
echo ""
echo "Export to use in curl commands:"
echo "export JWT=\"$JWT\""
echo ""
echo "Token claims:"
echo $JWT | cut -d. -f2 | base64 -d 2>/dev/null | jq .
