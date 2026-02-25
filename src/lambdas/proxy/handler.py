"""Proxy Lambda for routing A2A requests to backend agents."""

import os
import json
import logging
import requests
from typing import Dict, Any, Optional

# Add parent directory to path for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.dynamodb_client import create_client_from_env
from shared.oauth_client import OAuthClient
from shared.url_rewriter import rewrite_agent_card_urls
from shared.errors import (
    GatewayError, BadRequestError, NotFoundError,
    BackendError, TimeoutError as GatewayTimeoutError,
    INVALID_PATH_FORMAT, AGENT_NOT_FOUND,
    BACKEND_UNREACHABLE, OAUTH_ERROR, STREAM_IDLE_TIMEOUT
)

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Headers to exclude when forwarding
EXCLUDED_HEADERS = {
    'authorization', 'host', 'connection', 'transfer-encoding',
    'content-length', 'x-forwarded-for', 'x-forwarded-proto',
    'x-forwarded-port', 'x-amzn-trace-id'
}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Proxy Lambda handler.
    
    Routes A2A requests to backend agents with OAuth authentication.
    Supports both buffered and streaming responses.
    
    Args:
        event: API Gateway event
        context: Lambda context
        
    Returns:
        API Gateway response
    """
    try:
        logger.info(f"Proxy Lambda invoked: {event.get('httpMethod')} {event.get('path')}")
        
        # Extract user context from authorizer
        user_context = extract_user_context(event)
        logger.info(f"User: {user_context['userId']}, Scopes: {user_context['scopes']}")
        
        # Parse path to extract agent ID and operation
        agent_id, operation = parse_path(event['path'])
        logger.info(f"Agent: {agent_id}, Operation: {operation}")
        
        # Initialize clients
        db_client = create_client_from_env()
        oauth_client = OAuthClient()
        
        # Get agent from registry
        agent = db_client.get_agent(agent_id)
        
        if not agent:
            raise NotFoundError(
                AGENT_NOT_FOUND,
                f"Agent '{agent_id}' does not exist",
                {'agentId': agent_id}
            )
        
        # Check agent status
        if agent.get('status') != 'active':
            raise NotFoundError(
                AGENT_NOT_FOUND,
                f"Agent '{agent_id}' is not available",
                {'agentId': agent_id}
            )
        
        # Note: FGAC permission check is now handled by the Lambda Authorizer
        # The authorizer generates IAM policies with specific agent resource ARNs
        # If we reach this point, the user has already been authorized for this agent
        
        # Special case: Agent Card request - return cached card from DynamoDB
        if operation == '.well-known/agent-card.json' or operation.endswith('/.well-known/agent-card.json'):
            return handle_agent_card_request(agent_id, agent, event['httpMethod'])
        
        # For all other operations, proxy to backend
        # Get OAuth token for backend
        auth_config = agent.get('authConfig', {})
        access_token = oauth_client.get_access_token(agent_id, auth_config)
        
        backend_url = agent['backendUrl']
        
        # Check if this is a Bedrock AgentCore backend
        is_bedrock_agentcore = 'bedrock-agentcore' in backend_url
        
        if is_bedrock_agentcore:
            logger.info(f"Detected Bedrock AgentCore backend, using JSON-RPC format")
            # For Bedrock AgentCore, convert to JSON-RPC format
            response = forward_to_bedrock_agentcore(
                backend_url=backend_url,
                operation=operation,
                body=event.get('body'),
                access_token=access_token,
                headers=event.get('headers', {}),
                is_streaming=is_streaming_operation(operation)
            )
        else:
            # For standard A2A backends, forward HTTP directly
            backend_url = backend_url.rstrip('/')
            operation_path = operation.lstrip('/')
            request_url = f"{backend_url}/{operation_path}"
            
            logger.info(f"Forwarding to standard A2A backend: {request_url}")
            
            response = forward_request(
                url=request_url,
                method=event['httpMethod'],
                headers=event.get('headers', {}),
                body=event.get('body'),
                access_token=access_token,
                is_streaming=is_streaming_operation(operation)
            )
        
        return response
        
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


def parse_path(path: str) -> tuple[str, str]:
    """
    Parse API Gateway path to extract agent ID and operation.
    
    Path format: /agents/{agentId}/{operation}
    Examples:
        /agents/billing-agent/message:send
        /agents/billing-agent/.well-known/agent-card.json
        /agents/billing-agent/tasks/task-123
    
    Args:
        path: Request path
        
    Returns:
        Tuple of (agent_id, operation)
        
    Raises:
        BadRequestError: If path format is invalid
    """
    # Remove leading/trailing slashes
    path = path.strip('/')
    
    # Split path
    parts = path.split('/', 2)
    
    # Validate format: agents/{agentId}/{operation}
    if len(parts) < 3 or parts[0] != 'agents':
        raise BadRequestError(
            INVALID_PATH_FORMAT,
            f"Invalid path format. Expected: /agents/{{agentId}}/{{operation}}",
            {'path': path}
        )
    
    agent_id = parts[1]
    operation = parts[2]
    
    if not agent_id or not operation:
        raise BadRequestError(
            INVALID_PATH_FORMAT,
            "Agent ID and operation cannot be empty",
            {'path': path}
        )
    
    return agent_id, operation


def handle_agent_card_request(agent_id: str, agent: Dict[str, Any], method: str) -> Dict[str, Any]:
    """
    Handle agent card request by returning cached card from DynamoDB.
    
    This is a critical A2A compliance feature - standard A2A clients fetch
    agent cards from the URL provided in discovery. We return the cached card
    with URLs rewritten to point to the gateway.
    
    Args:
        agent_id: Agent identifier
        agent: Agent data from DynamoDB
        method: HTTP method (should be GET)
        
    Returns:
        API Gateway response with agent card
    """
    logger.info(f"Serving cached agent card for: {agent_id}")
    
    # Only allow GET for agent cards
    if method != 'GET':
        return {
            'statusCode': 405,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Allow': 'GET'
            },
            'body': json.dumps({
                'error': {
                    'code': 'METHOD_NOT_ALLOWED',
                    'message': 'Agent card endpoint only supports GET'
                }
            })
        }
    
    # Get cached agent card
    cached_card = agent.get('cachedAgentCard')
    
    if not cached_card:
        logger.warning(f"Agent {agent_id} has no cached agent card")
        return {
            'statusCode': 404,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': {
                    'code': 'AGENT_CARD_NOT_FOUND',
                    'message': f"Agent card not available for agent '{agent_id}'"
                }
            })
        }
    
    # Rewrite URLs to point to gateway
    gateway_domain = os.environ.get('GATEWAY_DOMAIN', 'PLACEHOLDER')
    rewritten_card = rewrite_agent_card_urls(
        cached_card,
        agent_id,
        gateway_domain
    )
    
    logger.info(f"Returning cached agent card for: {agent_id} with rewritten URLs")
    
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Cache-Control': 'public, max-age=300'  # Cache for 5 minutes
        },
        'body': json.dumps(rewritten_card)
    }


def extract_user_context(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract user context from API Gateway event.
    
    Args:
        event: API Gateway event
        
    Returns:
        Dict with userId, scopes, roles
    """
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


def is_streaming_operation(operation: str) -> bool:
    """
    Check if operation requires streaming response.
    
    Args:
        operation: A2A operation path
        
    Returns:
        True if streaming operation
    """
    # A2A streaming operations
    return operation.startswith('message:stream') or '/message:stream' in operation


def transform_a2a_to_bedrock_format(data: Any) -> Any:
    """
    Transform A2A protocol format to Bedrock AgentCore format.
    
    Key differences:
    - A2A uses "ROLE_USER"/"ROLE_AGENT", Bedrock uses "user"/"agent"
    - Recursively transforms nested structures
    
    Args:
        data: A2A formatted data
        
    Returns:
        Bedrock AgentCore formatted data
    """
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            # Transform role field
            if key == 'role' and isinstance(value, str):
                # Convert ROLE_USER -> user, ROLE_AGENT -> agent
                if value == 'ROLE_USER':
                    result[key] = 'user'
                elif value == 'ROLE_AGENT':
                    result[key] = 'agent'
                else:
                    # Already in correct format or unknown value
                    result[key] = value.lower() if value.isupper() else value
            else:
                # Recursively transform nested structures
                result[key] = transform_a2a_to_bedrock_format(value)
        return result
    elif isinstance(data, list):
        return [transform_a2a_to_bedrock_format(item) for item in data]
    else:
        return data


def forward_to_bedrock_agentcore(
    backend_url: str,
    operation: str,
    body: Optional[str],
    access_token: str,
    headers: Dict[str, str],
    is_streaming: bool
) -> Dict[str, Any]:
    """
    Forward request to Bedrock AgentCore backend using JSON-RPC format.
    
    Bedrock AgentCore expects JSON-RPC payloads at /invocations endpoint.
    HTTP operations like 'message:send' must be converted to JSON-RPC methods like 'message/send'.
    
    Args:
        backend_url: Bedrock AgentCore runtime URL
        operation: A2A operation (e.g., 'message:send')
        body: Request body (A2A message payload)
        access_token: OAuth access token
        headers: Request headers
        is_streaming: Whether this is a streaming operation
        
    Returns:
        API Gateway response
    """
    from uuid import uuid4
    
    # Parse the operation to get the JSON-RPC method
    # Convert 'message:send' -> 'message/send', 'message:stream' -> 'message/stream'
    jsonrpc_method = operation.replace(':', '/')
    
    logger.info(f"Converting operation '{operation}' to JSON-RPC method '{jsonrpc_method}'")
    
    # Parse the incoming body
    try:
        request_body = json.loads(body) if body else {}
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in request body: {body}")
        raise BadRequestError(
            'INVALID_JSON',
            'Request body must be valid JSON',
            {'body': body[:100] if body else None}
        )
    
    # Transform A2A format to Bedrock AgentCore format
    # A2A uses "ROLE_USER"/"ROLE_AGENT", Bedrock uses "user"/"agent"
    request_body = transform_a2a_to_bedrock_format(request_body)
    
    # Build JSON-RPC request
    jsonrpc_request = {
        "jsonrpc": "2.0",
        "method": jsonrpc_method,
        "id": str(uuid4()),
        "params": request_body
    }
    
    # Bedrock AgentCore always uses /invocations endpoint
    # The backend_url should already include /invocations if properly configured
    if '/invocations' not in backend_url:
        invoke_url = f"{backend_url.rstrip('/')}/invocations"
    else:
        invoke_url = backend_url.rstrip('/')
    
    logger.info(f"Forwarding to Bedrock AgentCore: {invoke_url}")
    logger.info(f"JSON-RPC request: {json.dumps(jsonrpc_request)}")
    
    # Build headers for Bedrock AgentCore
    backend_headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'X-Amzn-Bedrock-AgentCore-Runtime-Session-Id': str(uuid4())
    }
    
    try:
        # Make request to Bedrock AgentCore
        response = requests.post(
            invoke_url,
            json=jsonrpc_request,
            headers=backend_headers,
            stream=is_streaming,
            timeout=900 if is_streaming else 300  # 15 min for streaming, 5 min for buffered
        )
        
        logger.info(f"Bedrock AgentCore response status: {response.status_code}")
        
        if is_streaming:
            return handle_streaming_response(response)
        else:
            return handle_buffered_response(response)
            
    except requests.Timeout:
        raise GatewayTimeoutError(
            STREAM_IDLE_TIMEOUT if is_streaming else 'BACKEND_TIMEOUT',
            'Bedrock AgentCore request timed out'
        )
    except requests.RequestException as e:
        logger.error(f"Failed to connect to Bedrock AgentCore: {str(e)}")
        raise BackendError(
            BACKEND_UNREACHABLE,
            f'Failed to connect to Bedrock AgentCore: {str(e)}'
        )


def forward_request(
    url: str,
    method: str,
    headers: Dict[str, str],
    body: Optional[str],
    access_token: str,
    is_streaming: bool
) -> Dict[str, Any]:
    """
    Forward request to backend agent.
    
    Args:
        url: Backend URL
        method: HTTP method
        headers: Request headers
        body: Request body
        access_token: OAuth access token
        is_streaming: Whether to stream response
        
    Returns:
        API Gateway response
    """
    # Build headers for backend request
    backend_headers = build_backend_headers(headers, access_token, url)
    
    try:
        # Make request to backend
        response = requests.request(
            method=method,
            url=url,
            headers=backend_headers,
            data=body.encode('utf-8') if body else None,
            stream=is_streaming,
            timeout=900 if is_streaming else 300  # 15 min for streaming, 5 min for buffered
        )
        
        if is_streaming:
            # For streaming, we need to handle SSE events
            # Note: Lambda response streaming requires special configuration
            # For now, we'll buffer the stream (POC limitation)
            # In production, use Lambda response streaming with streamifyResponse
            return handle_streaming_response(response)
        else:
            # Buffered response
            return handle_buffered_response(response)
            
    except requests.Timeout:
        raise GatewayTimeoutError(
            STREAM_IDLE_TIMEOUT if is_streaming else 'BACKEND_TIMEOUT',
            'Backend request timed out'
        )
    except requests.RequestException as e:
        raise BackendError(
            BACKEND_UNREACHABLE,
            f'Failed to connect to backend: {str(e)}'
        )


def build_backend_headers(client_headers: Dict[str, str], access_token: str, backend_url: str = '') -> Dict[str, str]:
    """
    Build headers for backend request.
    
    Forwards all headers except excluded ones, and adds OAuth token.
    
    Args:
        client_headers: Headers from client request
        access_token: OAuth access token
        backend_url: Backend URL (used to detect Bedrock AgentCore)
        
    Returns:
        Headers for backend request
    """
    from uuid import uuid4
    
    backend_headers = {}
    
    # Forward allowed headers
    for key, value in client_headers.items():
        if key.lower() not in EXCLUDED_HEADERS:
            backend_headers[key] = value
    
    # Add OAuth token
    backend_headers['Authorization'] = f'Bearer {access_token}'
    
    # Add session ID header for Bedrock AgentCore
    if 'bedrock-agentcore' in backend_url:
        backend_headers['X-Amzn-Bedrock-AgentCore-Runtime-Session-Id'] = str(uuid4())
    
    # Ensure Content-Type if not present
    if 'Content-Type' not in backend_headers and 'content-type' not in backend_headers:
        backend_headers['Content-Type'] = 'application/json'
    
    return backend_headers


def handle_buffered_response(response: requests.Response) -> Dict[str, Any]:
    """
    Handle buffered response from backend.
    
    Args:
        response: Requests response object
        
    Returns:
        API Gateway response
    """
    # Build response headers
    response_headers = {
        'Content-Type': response.headers.get('Content-Type', 'application/json'),
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Authorization, Content-Type',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS'
    }
    
    # Forward additional headers (excluding hop-by-hop)
    for key, value in response.headers.items():
        if key.lower() not in EXCLUDED_HEADERS:
            response_headers[key] = value
    
    return {
        'statusCode': response.status_code,
        'headers': response_headers,
        'body': response.text
    }


def handle_streaming_response(response: requests.Response) -> Dict[str, Any]:
    """
    Handle streaming response from backend.
    
    Note: This is a POC implementation that buffers the stream.
    Production should use Lambda response streaming with streamifyResponse.
    
    Args:
        response: Requests response object with stream=True
        
    Returns:
        API Gateway response with buffered stream content
    """
    # Buffer all SSE events
    events = []
    
    for line in response.iter_lines():
        if line:
            events.append(line.decode('utf-8'))
    
    # Return buffered events as newline-separated text
    return {
        'statusCode': response.status_code,
        'headers': {
            'Content-Type': 'text/event-stream',
            'Access-Control-Allow-Origin': '*',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive'
        },
        'body': '\n'.join(events)
    }


# For local testing
if __name__ == '__main__':
    test_event = {
        'httpMethod': 'POST',
        'path': '/agents/billing-agent/message:send',
        'headers': {
            'Content-Type': 'application/json'
        },
        'body': json.dumps({
            'message': {
                'messageId': 'msg-123',
                'role': 'ROLE_USER',
                'parts': [{'text': 'Test message'}]
            }
        }),
        'requestContext': {
            'authorizer': {
                'userId': 'user-123',
                'scopes': 'billing:read,billing:write',
                'roles': 'user',
                'username': 'testuser'
            }
        }
    }
    
    os.environ['AGENT_REGISTRY_TABLE'] = 'a2a-gateway-poc-agent-registry'
    os.environ['PERMISSIONS_TABLE'] = 'a2a-gateway-poc-permissions'
    
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))
