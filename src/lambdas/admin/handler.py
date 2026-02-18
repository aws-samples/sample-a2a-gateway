"""Admin Lambda for agent registration and management."""

import os
import json
import logging
import requests
from typing import Dict, Any
from datetime import datetime, timezone

# Add parent directory to path for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.dynamodb_client import create_client_from_env
from shared.oauth_client import OAuthClient
from shared.errors import (
    GatewayError, BadRequestError, AuthorizationError, BackendError,
    ADMIN_PERMISSION_REQUIRED, AGENT_NOT_FOUND, BACKEND_UNREACHABLE, OAUTH_ERROR
)

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Admin Lambda handler.
    
    Handles agent registration, sync, and status management.
    
    Args:
        event: API Gateway event
        context: Lambda context
        
    Returns:
        API Gateway response
    """
    try:
        logger.info(f"Admin Lambda invoked: {event.get('httpMethod')} {event.get('path')}")
        
        # Extract user context from authorizer
        user_context = extract_user_context(event)
        
        # Verify admin permission
        if 'gateway:admin' not in user_context['scopes']:
            raise AuthorizationError(
                ADMIN_PERMISSION_REQUIRED,
                "Admin permission required for this operation",
                {'userId': user_context['userId']}
            )
        
        # Route to appropriate handler
        path = event['path']
        method = event['httpMethod']
        
        if method == 'POST' and path.endswith('/register'):
            return handle_register(event)
        elif method == 'POST' and '/sync' in path:
            return handle_sync(event)
        elif method == 'PATCH' and '/status' in path:
            return handle_status_update(event)
        else:
            raise BadRequestError(
                'INVALID_ADMIN_OPERATION',
                f"Unknown admin operation: {method} {path}"
            )
        
    except GatewayError as e:
        logger.error(f"Gateway error: {e.code} - {e.message}")
        return {
            'statusCode': e.status_code,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps(e.to_dict())
        }
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': {
                    'code': 'INTERNAL_ERROR',
                    'message': 'Internal server error'
                }
            })
        }


def handle_register(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle agent registration.
    
    Request body:
    {
      "agentId": "billing-agent",
      "name": "Billing Agent",
      "backendUrl": "https://backend1.example.com",
      "agentCardUrl": "https://backend1.example.com/.well-known/agent-card.json",
      "authConfig": {
        "type": "oauth2_client_credentials",
        "tokenUrl": "https://auth.backend1.example.com/oauth/token",
        "clientId": "gateway-client-id",
        "clientSecret": "secret-value",
        "scopes": ["agent:invoke"]
      }
    }
    
    Args:
        event: API Gateway event
        
    Returns:
        API Gateway response
    """
    logger.info("Handling agent registration")
    
    # Parse request body
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        raise BadRequestError('INVALID_JSON', 'Invalid JSON in request body')
    
    # Validate required fields
    required_fields = ['agentId', 'name', 'backendUrl', 'agentCardUrl', 'authConfig']
    for field in required_fields:
        if field not in body:
            raise BadRequestError(
                'MISSING_REQUIRED_FIELD',
                f"Missing required field: {field}",
                {'field': field}
            )
    
    agent_id = body['agentId']
    name = body['name']
    backend_url = body['backendUrl']
    agent_card_url = body['agentCardUrl']
    auth_config = body['authConfig']
    
    # Validate auth config
    if auth_config.get('type') != 'oauth2_client_credentials':
        raise BadRequestError(
            'INVALID_AUTH_CONFIG',
            "Only 'oauth2_client_credentials' auth type is supported"
        )
    
    required_auth_fields = ['tokenUrl', 'clientId', 'clientSecret']
    for field in required_auth_fields:
        if field not in auth_config:
            raise BadRequestError(
                'MISSING_AUTH_FIELD',
                f"Missing required auth config field: {field}",
                {'field': field}
            )
    
    # Store client secret in Secrets Manager
    import boto3
    secrets_manager = boto3.client('secretsmanager')
    
    secret_name = f"a2a-gateway/{agent_id}/oauth-credentials"
    
    try:
        secret_response = secrets_manager.create_secret(
            Name=secret_name,
            SecretString=json.dumps({
                'clientSecret': auth_config['clientSecret']
            }),
            Description=f"OAuth credentials for {name}"
        )
        secret_arn = secret_response['ARN']
        logger.info(f"Created secret: {secret_arn}")
    except secrets_manager.exceptions.ResourceExistsException:
        # Secret already exists, update it
        secret_response = secrets_manager.put_secret_value(
            SecretId=secret_name,
            SecretString=json.dumps({
                'clientSecret': auth_config['clientSecret']
            })
        )
        # Get ARN
        describe_response = secrets_manager.describe_secret(SecretId=secret_name)
        secret_arn = describe_response['ARN']
        logger.info(f"Updated existing secret: {secret_arn}")
    
    # Build auth config with ARN (remove client secret)
    stored_auth_config = {
        'type': auth_config['type'],
        'tokenUrl': auth_config['tokenUrl'],
        'clientId': auth_config['clientId'],
        'clientSecretArn': secret_arn,
        'scopes': auth_config.get('scopes', [])
    }
    
    # Fetch Agent Card from backend
    oauth_client = OAuthClient(secrets_manager)
    
    try:
        # Get OAuth token
        access_token = oauth_client.get_access_token(agent_id, stored_auth_config)
        
        # Fetch Agent Card
        agent_card = fetch_agent_card(agent_card_url, access_token)
        
    except Exception as e:
        logger.error(f"Failed to fetch Agent Card: {e}")
        raise BackendError(
            BACKEND_UNREACHABLE,
            f"Failed to fetch Agent Card from backend: {str(e)}",
            {'agentCardUrl': agent_card_url}
        )
    
    # Store agent in registry
    db_client = create_client_from_env()
    
    timestamp = get_timestamp()
    
    agent_item = {
        'agentId': agent_id,
        'name': name,
        'backendUrl': backend_url,
        'agentCardUrl': agent_card_url,
        'cachedAgentCard': agent_card,
        'lastSynced': timestamp,
        'status': 'active',
        'authConfig': stored_auth_config,
        'createdAt': timestamp,
        'updatedAt': timestamp
    }
    
    db_client.put_agent(agent_item)
    
    logger.info(f"Registered agent: {agent_id}")
    
    # Build gateway URL
    gateway_domain = os.environ['GATEWAY_DOMAIN']
    gateway_url = f"https://{gateway_domain}/agents/{agent_id}"
    
    return {
        'statusCode': 201,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'status': 'registered',
            'agentId': agent_id,
            'gatewayUrl': gateway_url,
            'agentCard': agent_card
        })
    }


def handle_sync(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle agent sync (refresh Agent Card).
    
    Path: POST /admin/agents/{agentId}/sync
    
    Args:
        event: API Gateway event
        
    Returns:
        API Gateway response
    """
    logger.info("Handling agent sync")
    
    # Extract agent ID from path
    path = event['path']
    # Path format: /admin/agents/{agentId}/sync
    parts = path.strip('/').split('/')
    
    if len(parts) < 4 or parts[0] != 'admin' or parts[1] != 'agents':
        raise BadRequestError('INVALID_PATH', 'Invalid sync path format')
    
    agent_id = parts[2]
    
    # Get agent from registry
    db_client = create_client_from_env()
    agent = db_client.get_agent(agent_id)
    
    if not agent:
        raise BadRequestError(
            AGENT_NOT_FOUND,
            f"Agent '{agent_id}' does not exist",
            {'agentId': agent_id}
        )
    
    # Fetch fresh Agent Card
    oauth_client = OAuthClient()
    
    try:
        # Get OAuth token
        access_token = oauth_client.get_access_token(agent_id, agent['authConfig'])
        
        # Fetch Agent Card
        new_agent_card = fetch_agent_card(agent['agentCardUrl'], access_token)
        
    except Exception as e:
        logger.error(f"Failed to fetch Agent Card: {e}")
        raise BackendError(
            BACKEND_UNREACHABLE,
            f"Failed to fetch Agent Card from backend: {str(e)}",
            {'agentCardUrl': agent['agentCardUrl']}
        )
    
    # Update cached Agent Card
    db_client.update_agent_card(agent_id, new_agent_card)
    
    logger.info(f"Synced agent: {agent_id}")
    
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'status': 'synced',
            'agentId': agent_id,
            'lastSynced': get_timestamp(),
            'agentCard': new_agent_card
        })
    }


def handle_status_update(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle agent status update.
    
    Path: PATCH /admin/agents/{agentId}/status
    Body: {"status": "active" | "inactive"}
    
    Args:
        event: API Gateway event
        
    Returns:
        API Gateway response
    """
    logger.info("Handling agent status update")
    
    # Extract agent ID from path
    path = event['path']
    parts = path.strip('/').split('/')
    
    if len(parts) < 4 or parts[0] != 'admin' or parts[1] != 'agents':
        raise BadRequestError('INVALID_PATH', 'Invalid status update path format')
    
    agent_id = parts[2]
    
    # Parse request body
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        raise BadRequestError('INVALID_JSON', 'Invalid JSON in request body')
    
    new_status = body.get('status')
    
    if new_status not in ['active', 'inactive']:
        raise BadRequestError(
            'INVALID_STATUS',
            "Status must be 'active' or 'inactive'",
            {'status': new_status}
        )
    
    # Update agent status
    db_client = create_client_from_env()
    
    # Verify agent exists
    agent = db_client.get_agent(agent_id)
    if not agent:
        raise BadRequestError(
            AGENT_NOT_FOUND,
            f"Agent '{agent_id}' does not exist",
            {'agentId': agent_id}
        )
    
    db_client.update_agent_status(agent_id, new_status)
    
    logger.info(f"Updated agent status: {agent_id} -> {new_status}")
    
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'status': 'updated',
            'agentId': agent_id,
            'newStatus': new_status
        })
    }


def fetch_agent_card(url: str, access_token: str) -> Dict[str, Any]:
    """
    Fetch Agent Card from backend.
    
    Args:
        url: Agent Card URL
        access_token: OAuth access token
        
    Returns:
        Agent Card JSON
        
    Raises:
        Exception: If fetch fails
    """
    from uuid import uuid4
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json'
    }
    
    # Add session ID header for Bedrock AgentCore
    if 'bedrock-agentcore' in url:
        headers['X-Amzn-Bedrock-AgentCore-Runtime-Session-Id'] = str(uuid4())
    
    response = requests.get(url, headers=headers, timeout=10)
    
    if response.status_code != 200:
        raise Exception(f"HTTP {response.status_code}: {response.text}")
    
    return response.json()


def extract_user_context(event: Dict[str, Any]) -> Dict[str, Any]:
    """Extract user context from API Gateway event."""
    request_context = event.get('requestContext', {})
    authorizer_context = request_context.get('authorizer', {})
    
    user_id = authorizer_context.get('userId', '')
    scopes_csv = authorizer_context.get('scopes', '')
    roles_csv = authorizer_context.get('roles', '')
    
    scopes = [s.strip() for s in scopes_csv.split(',') if s.strip()]
    roles = [r.strip() for r in roles_csv.split(',') if r.strip()]
    
    return {
        'userId': user_id,
        'scopes': scopes,
        'roles': roles,
        'username': authorizer_context.get('username', '')
    }


def get_timestamp() -> str:
    """Get current timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()
