"""Proxy Lambda for routing A2A requests to backend agents.

Supports both HTTP+JSON/REST and JSON-RPC protocol bindings.
All backends are assumed to be JSON-RPC (AgentCore runtime).
- HTTP+REST requests are translated to JSON-RPC before forwarding
- JSON-RPC requests are forwarded as-is
"""

import os
import json
import logging
import requests
from typing import Dict, Any, Optional, Tuple
from uuid import uuid4

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

# REST operation to JSON-RPC method mapping
REST_TO_JSONRPC_MAP = {
    'message:send': 'message/send',
    'message:stream': 'message/stream',
}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Proxy Lambda handler.
    
    Routes A2A requests to backend agents with OAuth authentication.
    Supports both HTTP+JSON/REST and JSON-RPC protocol bindings.
    All backends are JSON-RPC (AgentCore runtime).
    
    Args:
        event: API Gateway event
        context: Lambda context
        
    Returns:
        API Gateway response
    """
    # Track if request is JSON-RPC for error formatting
    is_jsonrpc_request = False
    jsonrpc_id = None
    
    try:
        logger.info(f"Proxy Lambda invoked: {event.get('httpMethod')} {event.get('path')}")
        
        # Extract user context from authorizer
        user_context = extract_user_context(event)
        logger.info(f"User: {user_context['userId']}, Scopes: {user_context['scopes']}")
        
        # Parse path to extract agent ID and operation (if REST style)
        agent_id, operation = parse_path(event['path'])
        logger.info(f"Agent: {agent_id}, Operation: {operation}")
        
        # Detect protocol binding from request body
        body = event.get('body')
        parsed_body = None
        if body:
            try:
                parsed_body = json.loads(body)
            except json.JSONDecodeError:
                pass
        
        # Check if this is a JSON-RPC request
        is_jsonrpc_request, jsonrpc_id = detect_jsonrpc_request(parsed_body)
        
        if is_jsonrpc_request:
            logger.info(f"Detected JSON-RPC request, method: {parsed_body.get('method')}")
        
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
        
        # Get OAuth token for backend
        auth_config = agent.get('authConfig', {})
        access_token = oauth_client.get_access_token(agent_id, auth_config)
        
        backend_url = agent['backendUrl']
        
        # Route based on client protocol binding
        # All backends are JSON-RPC (AgentCore runtime)
        if is_jsonrpc_request:
            # JSON-RPC client → forward as-is to JSON-RPC backend
            response = handle_jsonrpc_to_jsonrpc(
                backend_url=backend_url,
                jsonrpc_request=parsed_body,
                access_token=access_token,
                headers=event.get('headers', {})
            )
        elif operation:
            # HTTP+REST client with operation → translate to JSON-RPC → forward to backend
            response = handle_rest_to_jsonrpc(
                backend_url=backend_url,
                operation=operation,
                body=body,
                access_token=access_token,
                headers=event.get('headers', {})
            )
        else:
            # No operation and not JSON-RPC - invalid request
            raise BadRequestError(
                INVALID_PATH_FORMAT,
                "Operation required for REST requests. Use /agents/{agentId}/{operation} or send JSON-RPC body",
                {'path': event['path']}
            )
        
        return response
        
    except GatewayError as e:
        logger.error(f"Gateway error: {e.code} - {e.message}")
        return format_error_response(e, is_jsonrpc_request, jsonrpc_id)
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return format_error_response(
            GatewayError('INTERNAL_ERROR', 'Internal server error', 500),
            is_jsonrpc_request,
            jsonrpc_id
        )


def parse_path(path: str) -> Tuple[str, str]:
    """
    Parse API Gateway path to extract agent ID and operation.
    
    Path format: /agents/{agentId}/{operation}
    For JSON-RPC on base path: /agents/{agentId}
    
    Examples:
        /agents/billing-agent/message:send
        /agents/billing-agent/.well-known/agent-card.json
        /agents/billing-agent/tasks/task-123
        /agents/billing-agent (JSON-RPC base path)
    
    Args:
        path: Request path
        
    Returns:
        Tuple of (agent_id, operation) - operation may be empty for JSON-RPC base path
        
    Raises:
        BadRequestError: If path format is invalid
    """
    # Remove leading/trailing slashes
    path = path.strip('/')
    
    # Split path
    parts = path.split('/', 2)
    
    # Validate format: agents/{agentId} or agents/{agentId}/{operation}
    if len(parts) < 2 or parts[0] != 'agents':
        raise BadRequestError(
            INVALID_PATH_FORMAT,
            f"Invalid path format. Expected: /agents/{{agentId}}/{{operation}}",
            {'path': path}
        )
    
    agent_id = parts[1]
    
    # Operation is optional for JSON-RPC requests on base path
    operation = parts[2] if len(parts) > 2 else ''
    
    if not agent_id:
        raise BadRequestError(
            INVALID_PATH_FORMAT,
            "Agent ID cannot be empty",
            {'path': path}
        )
    
    return agent_id, operation


def detect_jsonrpc_request(body: Optional[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    """
    Detect if request is JSON-RPC format.
    
    Args:
        body: Parsed request body
        
    Returns:
        Tuple of (is_jsonrpc, request_id)
    """
    if not body or not isinstance(body, dict):
        return False, None
    
    # JSON-RPC 2.0 requires jsonrpc field and method field
    if body.get('jsonrpc') == '2.0' and 'method' in body:
        return True, body.get('id')
    
    return False, None


def format_error_response(
    error: GatewayError,
    is_jsonrpc: bool,
    jsonrpc_id: Optional[str]
) -> Dict[str, Any]:
    """
    Format error response based on client protocol.
    
    Args:
        error: Gateway error
        is_jsonrpc: Whether client used JSON-RPC
        jsonrpc_id: JSON-RPC request ID
        
    Returns:
        API Gateway response
    """
    if is_jsonrpc:
        # JSON-RPC error format
        # Map HTTP status codes to JSON-RPC error codes
        jsonrpc_code = map_http_to_jsonrpc_error_code(error.status_code, error.code)
        
        return {
            'statusCode': 200,  # JSON-RPC errors return 200 with error in body
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'jsonrpc': '2.0',
                'id': jsonrpc_id,
                'error': {
                    'code': jsonrpc_code,
                    'message': error.message,
                    'data': {
                        'code': error.code,
                        'details': error.details
                    }
                }
            })
        }
    else:
        # HTTP+REST error format
        return {
            'statusCode': error.status_code,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps(error.to_dict())
        }


def map_http_to_jsonrpc_error_code(status_code: int, error_code: str) -> int:
    """
    Map HTTP status code to JSON-RPC error code.
    
    Based on A2A spec Section 5.4 Error Code Mappings.
    
    Args:
        status_code: HTTP status code
        error_code: A2A error code
        
    Returns:
        JSON-RPC error code
    """
    # A2A-specific error codes (from spec)
    a2a_error_map = {
        'TASK_NOT_FOUND': -32001,
        'TASK_NOT_CANCELABLE': -32002,
        'PUSH_NOTIFICATION_NOT_SUPPORTED': -32003,
        'UNSUPPORTED_OPERATION': -32004,
        'CONTENT_TYPE_NOT_SUPPORTED': -32005,
        'INVALID_AGENT_RESPONSE': -32006,
        AGENT_NOT_FOUND: -32001,  # Map to TaskNotFound equivalent
    }
    
    if error_code in a2a_error_map:
        return a2a_error_map[error_code]
    
    # Standard JSON-RPC error codes based on HTTP status
    if status_code == 400:
        return -32602  # Invalid params
    elif status_code == 401 or status_code == 403:
        return -32600  # Invalid request
    elif status_code == 404:
        return -32001  # Task/resource not found
    elif status_code == 500:
        return -32603  # Internal error
    elif status_code == 502 or status_code == 504:
        return -32603  # Internal error (backend issues)
    else:
        return -32603  # Default to internal error


def handle_jsonrpc_to_jsonrpc(
    backend_url: str,
    jsonrpc_request: Dict[str, Any],
    access_token: str,
    headers: Dict[str, str]
) -> Dict[str, Any]:
    """
    Handle JSON-RPC client request to JSON-RPC backend.
    
    Forwards the request as-is with minimal transformation.
    
    Args:
        backend_url: Backend URL
        jsonrpc_request: Parsed JSON-RPC request
        access_token: OAuth access token
        headers: Request headers
        
    Returns:
        API Gateway response
    """
    method = jsonrpc_request.get('method', '')
    jsonrpc_id = jsonrpc_request.get('id')
    
    # Determine if streaming based on method
    is_streaming = method in ('SendStreamingMessage', 'message/stream')
    
    # Transform A2A format to Bedrock AgentCore format (role values)
    params = jsonrpc_request.get('params', {})
    transformed_params = transform_a2a_to_bedrock_format(params)
    
    # Normalize method name to Bedrock format (message/send, message/stream)
    normalized_method = normalize_jsonrpc_method(method)
    
    # Build the forwarded request
    forward_request = {
        'jsonrpc': '2.0',
        'id': jsonrpc_id or str(uuid4()),
        'method': normalized_method,
        'params': transformed_params
    }
    
    # Build invoke URL
    invoke_url = get_backend_invoke_url(backend_url)
    
    logger.info(f"Forwarding JSON-RPC to backend: {invoke_url}, method: {normalized_method}")
    
    # Build headers
    backend_headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'X-Amzn-Bedrock-AgentCore-Runtime-Session-Id': str(uuid4())
    }
    
    try:
        response = requests.post(
            invoke_url,
            json=forward_request,
            headers=backend_headers,
            stream=is_streaming,
            timeout=900 if is_streaming else 300
        )
        
        logger.info(f"Backend response status: {response.status_code}")
        
        if is_streaming:
            return handle_streaming_response(response)
        else:
            return handle_buffered_response(response)
            
    except requests.Timeout:
        raise GatewayTimeoutError(
            STREAM_IDLE_TIMEOUT if is_streaming else 'BACKEND_TIMEOUT',
            'Backend request timed out'
        )
    except requests.RequestException as e:
        logger.error(f"Failed to connect to backend: {str(e)}")
        raise BackendError(
            BACKEND_UNREACHABLE,
            f'Failed to connect to backend: {str(e)}'
        )


def handle_rest_to_jsonrpc(
    backend_url: str,
    operation: str,
    body: Optional[str],
    access_token: str,
    headers: Dict[str, str]
) -> Dict[str, Any]:
    """
    Handle HTTP+REST client request by translating to JSON-RPC for backend.
    
    Args:
        backend_url: Backend URL
        operation: REST operation (e.g., 'message:send')
        body: Request body
        access_token: OAuth access token
        headers: Request headers
        
    Returns:
        API Gateway response
    """
    # Parse the incoming body
    try:
        request_body = json.loads(body) if body else {}
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in request body")
        raise BadRequestError(
            'INVALID_JSON',
            'Request body must be valid JSON',
            {}
        )
    
    # Map REST operation to JSON-RPC method
    jsonrpc_method = REST_TO_JSONRPC_MAP.get(operation)
    if not jsonrpc_method:
        raise BadRequestError(
            'UNSUPPORTED_OPERATION',
            f"Operation '{operation}' is not supported",
            {'operation': operation}
        )
    
    is_streaming = is_streaming_operation(operation)
    
    # Transform A2A format to Bedrock AgentCore format
    transformed_body = transform_a2a_to_bedrock_format(request_body)
    
    # Build JSON-RPC request
    jsonrpc_request = {
        'jsonrpc': '2.0',
        'id': str(uuid4()),
        'method': jsonrpc_method,
        'params': transformed_body
    }
    
    # Build invoke URL
    invoke_url = get_backend_invoke_url(backend_url)
    
    logger.info(f"Translating REST to JSON-RPC: {operation} -> {jsonrpc_method}")
    logger.info(f"Forwarding to backend: {invoke_url}")
    
    # Build headers
    backend_headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'X-Amzn-Bedrock-AgentCore-Runtime-Session-Id': str(uuid4())
    }
    
    try:
        response = requests.post(
            invoke_url,
            json=jsonrpc_request,
            headers=backend_headers,
            stream=is_streaming,
            timeout=900 if is_streaming else 300
        )
        
        logger.info(f"Backend response status: {response.status_code}")
        
        if is_streaming:
            return handle_streaming_response(response)
        else:
            # For REST clients, unwrap JSON-RPC response
            return handle_buffered_response_for_rest(response)
            
    except requests.Timeout:
        raise GatewayTimeoutError(
            STREAM_IDLE_TIMEOUT if is_streaming else 'BACKEND_TIMEOUT',
            'Backend request timed out'
        )
    except requests.RequestException as e:
        logger.error(f"Failed to connect to backend: {str(e)}")
        raise BackendError(
            BACKEND_UNREACHABLE,
            f'Failed to connect to backend: {str(e)}'
        )


def normalize_jsonrpc_method(method: str) -> str:
    """
    Normalize JSON-RPC method name to backend format.
    
    Converts PascalCase methods (SendMessage) to slash format (message/send).
    
    Args:
        method: JSON-RPC method name
        
    Returns:
        Normalized method name
    """
    method_map = {
        'SendMessage': 'message/send',
        'SendStreamingMessage': 'message/stream',
    }
    return method_map.get(method, method)


def get_backend_invoke_url(backend_url: str) -> str:
    """
    Get the invoke URL for the backend.
    
    Args:
        backend_url: Backend URL from agent config
        
    Returns:
        Full invoke URL
    """
    if '/invocations' not in backend_url:
        return f"{backend_url.rstrip('/')}/invocations"
    return backend_url.rstrip('/')


def handle_buffered_response_for_rest(response: requests.Response) -> Dict[str, Any]:
    """
    Handle buffered response from JSON-RPC backend for REST client.
    
    Unwraps JSON-RPC response to return just the result/error.
    
    Args:
        response: Requests response object
        
    Returns:
        API Gateway response
    """
    try:
        jsonrpc_response = response.json()
    except json.JSONDecodeError:
        # If not valid JSON, return as-is
        return handle_buffered_response(response)
    
    # Check for JSON-RPC error
    if 'error' in jsonrpc_response:
        error = jsonrpc_response['error']
        error_code = error.get('code', -32603)
        
        # Map JSON-RPC error code to HTTP status
        if error_code == -32001:
            status_code = 404
        elif error_code in (-32600, -32602):
            status_code = 400
        else:
            status_code = 500
        
        return {
            'statusCode': status_code,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': {
                    'code': error.get('data', {}).get('code', 'BACKEND_ERROR'),
                    'message': error.get('message', 'Backend error'),
                    'details': error.get('data', {}).get('details', {})
                }
            })
        }
    
    # Return just the result for success
    result = jsonrpc_response.get('result', {})
    
    return {
        'statusCode': response.status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(result)
    }


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


def build_backend_headers(client_headers: Dict[str, str], access_token: str) -> Dict[str, str]:
    """
    Build headers for backend request.
    
    Forwards all headers except excluded ones, and adds OAuth token.
    
    Args:
        client_headers: Headers from client request
        access_token: OAuth access token
        
    Returns:
        Headers for backend request
    """
    backend_headers = {}
    
    # Forward allowed headers
    for key, value in client_headers.items():
        if key.lower() not in EXCLUDED_HEADERS:
            backend_headers[key] = value
    
    # Add OAuth token
    backend_headers['Authorization'] = f'Bearer {access_token}'
    
    # Ensure Content-Type if not present
    if 'Content-Type' not in backend_headers and 'content-type' not in backend_headers:
        backend_headers['Content-Type'] = 'application/json'
    
    return backend_headers


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
