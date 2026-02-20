"""
FastAPI-based A2A Proxy with streaming support.

This Lambda uses Lambda Web Adapter to run FastAPI, enabling both
streaming (SSE) and buffered responses through the same endpoint.
"""

import os
import sys
import json
import logging
from typing import Dict, Any, Optional, AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, StreamingResponse, Response
import httpx

# Add parent paths for shared module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.dynamodb_client import DynamoDBClient, create_client_from_env
from shared.oauth_client import OAuthClient
from shared.url_rewriter import rewrite_agent_card_urls
from shared.errors import (
    GatewayError, BadRequestError, NotFoundError,
    BackendError, TimeoutError as GatewayTimeoutError,
    INVALID_PATH_FORMAT, AGENT_NOT_FOUND,
    BACKEND_UNREACHABLE, OAUTH_ERROR, STREAM_IDLE_TIMEOUT
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Headers to exclude when forwarding
EXCLUDED_HEADERS = {
    'authorization', 'host', 'connection', 'transfer-encoding',
    'content-length', 'x-forwarded-for', 'x-forwarded-proto',
    'x-forwarded-port', 'x-amzn-trace-id', 'x-amzn-requestid'
}

# Global clients (reused across requests for Lambda warm starts)
_db_client: Optional[DynamoDBClient] = None
_oauth_client: Optional[OAuthClient] = None


def get_db_client() -> DynamoDBClient:
    """Get or create DynamoDB client."""
    global _db_client
    if _db_client is None:
        _db_client = create_client_from_env()
    return _db_client


def get_oauth_client() -> OAuthClient:
    """Get or create OAuth client."""
    global _oauth_client
    if _oauth_client is None:
        _oauth_client = OAuthClient()
    return _oauth_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("A2A Proxy Lambda starting up")
    yield
    logger.info("A2A Proxy Lambda shutting down")


app = FastAPI(
    title="A2A Gateway Proxy",
    description="Proxy for A2A protocol with streaming support",
    lifespan=lifespan
)


class UserContext:
    """User context extracted from API Gateway authorizer."""
    
    def __init__(self, user_id: str, scopes: list, roles: list, username: str):
        self.user_id = user_id
        self.scopes = scopes
        self.roles = roles
        self.username = username


def extract_user_context(request: Request) -> UserContext:
    """
    Extract user context from Lambda event passed through headers.
    
    API Gateway Lambda authorizer context is passed via special headers
    when using Lambda Web Adapter.
    """
    # Lambda Web Adapter passes the original event in x-amzn-request-context header
    request_context_header = request.headers.get('x-amzn-request-context', '{}')
    
    try:
        request_context = json.loads(request_context_header)
        authorizer = request_context.get('authorizer', {})
    except json.JSONDecodeError:
        authorizer = {}
    
    user_id = authorizer.get('userId', '')
    scopes_csv = authorizer.get('scopes', '')
    roles_csv = authorizer.get('roles', '')
    username = authorizer.get('username', '')
    
    scopes = [s.strip() for s in scopes_csv.split(',') if s.strip()]
    roles = [r.strip() for r in roles_csv.split(',') if r.strip()]
    
    return UserContext(user_id, scopes, roles, username)


def is_streaming_operation(operation: str) -> bool:
    """Check if operation requires streaming response."""
    return 'message:stream' in operation


def transform_a2a_to_bedrock_format(data: Any) -> Any:
    """
    Transform A2A protocol format to Bedrock AgentCore format.
    
    Key differences:
    - A2A uses "ROLE_USER"/"ROLE_AGENT", Bedrock uses "user"/"agent"
    """
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if key == 'role' and isinstance(value, str):
                if value == 'ROLE_USER':
                    result[key] = 'user'
                elif value == 'ROLE_AGENT':
                    result[key] = 'agent'
                else:
                    result[key] = value.lower() if value.isupper() else value
            else:
                result[key] = transform_a2a_to_bedrock_format(value)
        return result
    elif isinstance(data, list):
        return [transform_a2a_to_bedrock_format(item) for item in data]
    return data


def build_backend_headers(
    client_headers: Dict[str, str],
    access_token: str,
    backend_url: str = ''
) -> Dict[str, str]:
    """Build headers for backend request."""
    from uuid import uuid4
    
    backend_headers = {}
    
    for key, value in client_headers.items():
        if key.lower() not in EXCLUDED_HEADERS:
            backend_headers[key] = value
    
    backend_headers['Authorization'] = f'Bearer {access_token}'
    
    if 'bedrock-agentcore' in backend_url:
        backend_headers['X-Amzn-Bedrock-AgentCore-Runtime-Session-Id'] = str(uuid4())
    
    if 'Content-Type' not in backend_headers and 'content-type' not in backend_headers:
        backend_headers['Content-Type'] = 'application/json'
    
    return backend_headers


@app.get("/health")
async def health_check():
    """Health check endpoint for Lambda Web Adapter."""
    return {"status": "healthy"}


@app.get("/agents/{agent_id}/.well-known/agent-card.json")
async def get_agent_card(
    agent_id: str,
    request: Request,
    db_client: DynamoDBClient = Depends(get_db_client)
):
    """
    Serve cached agent card from DynamoDB.
    
    This is a critical A2A compliance feature - returns the cached card
    with URLs rewritten to point to the gateway.
    
    Note: FGAC permission check is handled by the Lambda Authorizer.
    If we reach this point, the user has already been authorized for this agent.
    """
    user_context = extract_user_context(request)
    logger.info(f"Agent card request for {agent_id} by user {user_context.user_id}")
    
    # Get agent from registry
    agent = db_client.get_agent(agent_id)
    
    if not agent:
        raise HTTPException(status_code=404, detail={
            'error': {'code': AGENT_NOT_FOUND, 'message': f"Agent '{agent_id}' not found"}
        })
    
    if agent.get('status') != 'active':
        raise HTTPException(status_code=404, detail={
            'error': {'code': AGENT_NOT_FOUND, 'message': f"Agent '{agent_id}' is not available"}
        })
    
    # Get cached agent card
    cached_card = agent.get('cachedAgentCard')
    if not cached_card:
        raise HTTPException(status_code=404, detail={
            'error': {'code': 'AGENT_CARD_NOT_FOUND', 'message': f"Agent card not available"}
        })
    
    # Rewrite URLs
    gateway_domain = os.environ.get('GATEWAY_DOMAIN', 'PLACEHOLDER')
    rewritten_card = rewrite_agent_card_urls(cached_card, agent_id, gateway_domain)
    
    return JSONResponse(
        content=rewritten_card,
        headers={
            'Access-Control-Allow-Origin': '*',
            'Cache-Control': 'public, max-age=300'
        }
    )


@app.api_route(
    "/agents/{agent_id}/{operation:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
)
async def proxy_request(
    agent_id: str,
    operation: str,
    request: Request,
    db_client: DynamoDBClient = Depends(get_db_client),
    oauth_client: OAuthClient = Depends(get_oauth_client)
):
    """
    Proxy requests to backend agents.
    
    Handles both streaming (SSE) and buffered responses based on operation.
    
    Note: FGAC permission check is handled by the Lambda Authorizer.
    If we reach this point, the user has already been authorized for this agent.
    """
    user_context = extract_user_context(request)
    logger.info(f"Proxy request: {request.method} /agents/{agent_id}/{operation}")
    logger.info(f"User: {user_context.user_id}, Scopes: {user_context.scopes}")
    
    # Get agent from registry
    agent = db_client.get_agent(agent_id)
    
    if not agent:
        raise HTTPException(status_code=404, detail={
            'error': {'code': AGENT_NOT_FOUND, 'message': f"Agent '{agent_id}' not found"}
        })
    
    if agent.get('status') != 'active':
        raise HTTPException(status_code=404, detail={
            'error': {'code': AGENT_NOT_FOUND, 'message': f"Agent '{agent_id}' is not available"}
        })
    
    # Get OAuth token
    auth_config = agent.get('authConfig', {})
    try:
        access_token = oauth_client.get_access_token(agent_id, auth_config)
    except Exception as e:
        logger.error(f"OAuth error: {e}")
        raise HTTPException(status_code=502, detail={
            'error': {'code': OAUTH_ERROR, 'message': f"Failed to authenticate with backend"}
        })
    
    backend_url = agent['backendUrl']
    is_streaming = is_streaming_operation(operation)
    is_bedrock = 'bedrock-agentcore' in backend_url
    
    # Read request body
    body = await request.body()
    body_str = body.decode('utf-8') if body else None
    
    if is_bedrock:
        return await forward_to_bedrock(
            backend_url=backend_url,
            operation=operation,
            body=body_str,
            access_token=access_token,
            headers=dict(request.headers),
            is_streaming=is_streaming
        )
    else:
        return await forward_to_standard_backend(
            backend_url=backend_url,
            operation=operation,
            method=request.method,
            body=body_str,
            access_token=access_token,
            headers=dict(request.headers),
            is_streaming=is_streaming
        )


async def forward_to_bedrock(
    backend_url: str,
    operation: str,
    body: Optional[str],
    access_token: str,
    headers: Dict[str, str],
    is_streaming: bool
) -> Response:
    """
    Forward request to Bedrock AgentCore backend using JSON-RPC format.
    """
    from uuid import uuid4
    
    # Convert operation to JSON-RPC method
    jsonrpc_method = operation.replace(':', '/')
    logger.info(f"Converting '{operation}' to JSON-RPC method '{jsonrpc_method}'")
    
    # Parse and transform body
    try:
        request_body = json.loads(body) if body else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail={
            'error': {'code': 'INVALID_JSON', 'message': 'Request body must be valid JSON'}
        })
    
    request_body = transform_a2a_to_bedrock_format(request_body)
    
    # Build JSON-RPC request
    jsonrpc_request = {
        "jsonrpc": "2.0",
        "method": jsonrpc_method,
        "id": str(uuid4()),
        "params": request_body
    }
    
    # Build URL
    if '/invocations' not in backend_url:
        invoke_url = f"{backend_url.rstrip('/')}/invocations"
    else:
        invoke_url = backend_url.rstrip('/')
    
    logger.info(f"Forwarding to Bedrock AgentCore: {invoke_url}")
    
    # Build headers
    backend_headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'X-Amzn-Bedrock-AgentCore-Runtime-Session-Id': str(uuid4())
    }
    
    if is_streaming:
        return await stream_bedrock_response(invoke_url, jsonrpc_request, backend_headers)
    else:
        return await buffered_bedrock_response(invoke_url, jsonrpc_request, backend_headers)


async def buffered_bedrock_response(
    url: str,
    jsonrpc_request: dict,
    headers: dict
) -> JSONResponse:
    """Make buffered request to Bedrock AgentCore."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, json=jsonrpc_request, headers=headers)
            
            return JSONResponse(
                content=response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text,
                status_code=response.status_code,
                headers={
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Authorization, Content-Type',
                    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS'
                }
            )
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail={
                'error': {'code': 'BACKEND_TIMEOUT', 'message': 'Backend request timed out'}
            })
        except httpx.RequestError as e:
            logger.error(f"Backend request failed: {e}")
            raise HTTPException(status_code=502, detail={
                'error': {'code': BACKEND_UNREACHABLE, 'message': f'Failed to connect to backend'}
            })


async def stream_bedrock_response(
    url: str,
    jsonrpc_request: dict,
    headers: dict
) -> StreamingResponse:
    """Stream response from Bedrock AgentCore."""
    
    async def generate() -> AsyncGenerator[bytes, None]:
        async with httpx.AsyncClient(timeout=httpx.Timeout(900.0, connect=30.0)) as client:
            try:
                async with client.stream('POST', url, json=jsonrpc_request, headers=headers) as response:
                    async for chunk in response.aiter_bytes():
                        yield chunk
            except httpx.TimeoutException:
                logger.error("Stream timeout")
                yield b'event: error\ndata: {"error": "Stream timeout"}\n\n'
            except httpx.RequestError as e:
                logger.error(f"Stream error: {e}")
                yield b'event: error\ndata: {"error": "Backend connection failed"}\n\n'
    
    return StreamingResponse(
        generate(),
        media_type='text/event-stream',
        headers={
            'Access-Control-Allow-Origin': '*',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )


async def forward_to_standard_backend(
    backend_url: str,
    operation: str,
    method: str,
    body: Optional[str],
    access_token: str,
    headers: Dict[str, str],
    is_streaming: bool
) -> Response:
    """Forward request to standard A2A backend."""
    
    # Build URL
    backend_url = backend_url.rstrip('/')
    operation_path = operation.lstrip('/')
    request_url = f"{backend_url}/{operation_path}"
    
    logger.info(f"Forwarding to standard backend: {method} {request_url}")
    
    # Build headers
    backend_headers = build_backend_headers(headers, access_token, backend_url)
    
    if is_streaming:
        return await stream_standard_response(request_url, method, body, backend_headers)
    else:
        return await buffered_standard_response(request_url, method, body, backend_headers)


async def buffered_standard_response(
    url: str,
    method: str,
    body: Optional[str],
    headers: dict
) -> Response:
    """Make buffered request to standard backend."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                content=body.encode('utf-8') if body else None
            )
            
            # Build response headers
            response_headers = {
                'Content-Type': response.headers.get('Content-Type', 'application/json'),
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Authorization, Content-Type',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS'
            }
            
            # Forward additional headers
            for key, value in response.headers.items():
                if key.lower() not in EXCLUDED_HEADERS:
                    response_headers[key] = value
            
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=response_headers
            )
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail={
                'error': {'code': 'BACKEND_TIMEOUT', 'message': 'Backend request timed out'}
            })
        except httpx.RequestError as e:
            logger.error(f"Backend request failed: {e}")
            raise HTTPException(status_code=502, detail={
                'error': {'code': BACKEND_UNREACHABLE, 'message': f'Failed to connect to backend'}
            })


async def stream_standard_response(
    url: str,
    method: str,
    body: Optional[str],
    headers: dict
) -> StreamingResponse:
    """Stream response from standard backend."""
    
    async def generate() -> AsyncGenerator[bytes, None]:
        async with httpx.AsyncClient(timeout=httpx.Timeout(900.0, connect=30.0)) as client:
            try:
                async with client.stream(
                    method=method,
                    url=url,
                    headers=headers,
                    content=body.encode('utf-8') if body else None
                ) as response:
                    async for line in response.aiter_lines():
                        if line:
                            yield (line + '\n').encode('utf-8')
            except httpx.TimeoutException:
                logger.error("Stream timeout")
                yield b'event: error\ndata: {"error": "Stream timeout"}\n\n'
            except httpx.RequestError as e:
                logger.error(f"Stream error: {e}")
                yield b'event: error\ndata: {"error": "Backend connection failed"}\n\n'
    
    return StreamingResponse(
        generate(),
        media_type='text/event-stream',
        headers={
            'Access-Control-Allow-Origin': '*',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )


@app.exception_handler(GatewayError)
async def gateway_error_handler(request: Request, exc: GatewayError):
    """Handle GatewayError exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
        headers={'Access-Control-Allow-Origin': '*'}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.error(f"Unexpected error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={'error': {'code': 'INTERNAL_ERROR', 'message': 'Internal server error'}},
        headers={'Access-Control-Allow-Origin': '*'}
    )


# For local testing with uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
