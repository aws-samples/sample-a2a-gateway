"""Unit tests for Proxy Lambda."""

import pytest
import json
import os
from unittest.mock import Mock, patch, MagicMock

# Add src to path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/lambdas'))

from proxy.handler import (
    lambda_handler, parse_path, extract_user_context,
    is_streaming_operation, build_backend_headers
)
from shared.errors import BadRequestError, NotFoundError, AuthorizationError


class TestParsePath:
    """Test path parsing for agent ID and operation extraction."""
    
    def test_parse_message_send(self):
        """Should parse message:send operation."""
        agent_id, operation = parse_path('/agents/billing-agent/message:send')
        
        assert agent_id == 'billing-agent'
        assert operation == 'message:send'
    
    def test_parse_message_stream(self):
        """Should parse message:stream operation."""
        agent_id, operation = parse_path('/agents/search-agent/message:stream')
        
        assert agent_id == 'search-agent'
        assert operation == 'message:stream'
    
    def test_parse_agent_card(self):
        """Should parse agent card request."""
        agent_id, operation = parse_path('/agents/billing-agent/.well-known/agent-card.json')
        
        assert agent_id == 'billing-agent'
        assert operation == '.well-known/agent-card.json'
    
    def test_parse_get_task(self):
        """Should parse task retrieval."""
        agent_id, operation = parse_path('/agents/billing-agent/tasks/task-123')
        
        assert agent_id == 'billing-agent'
        assert operation == 'tasks/task-123'
    
    def test_parse_list_tasks(self):
        """Should parse task listing."""
        agent_id, operation = parse_path('/agents/billing-agent/tasks')
        
        assert agent_id == 'billing-agent'
        assert operation == 'tasks'
    
    def test_parse_cancel_task(self):
        """Should parse task cancellation."""
        agent_id, operation = parse_path('/agents/billing-agent/tasks/task-123:cancel')
        
        assert agent_id == 'billing-agent'
        assert operation == 'tasks/task-123:cancel'
    
    def test_parse_agent_card_operation(self):
        """Should parse agent card as an operation."""
        agent_id, operation = parse_path('/agents/billing-agent/.well-known/agent-card.json')
        
        assert agent_id == 'billing-agent'
        assert operation == '.well-known/agent-card.json'
    
    def test_parse_with_leading_trailing_slashes(self):
        """Should handle leading/trailing slashes."""
        agent_id, operation = parse_path('//agents/billing-agent/message:send//')
        
        assert agent_id == 'billing-agent'
        assert operation == 'message:send'
    
    def test_parse_invalid_no_operation(self):
        """Should raise error for missing operation."""
        with pytest.raises(BadRequestError) as exc_info:
            parse_path('/agents/billing-agent')
        
        assert exc_info.value.code == 'INVALID_PATH_FORMAT'
    
    def test_parse_invalid_no_agents_prefix(self):
        """Should raise error for missing 'agents' prefix."""
        with pytest.raises(BadRequestError) as exc_info:
            parse_path('/billing-agent/message:send')
        
        assert exc_info.value.code == 'INVALID_PATH_FORMAT'
    
    def test_parse_invalid_empty_agent_id(self):
        """Should raise error for empty agent ID."""
        with pytest.raises(BadRequestError) as exc_info:
            parse_path('/agents//message:send')
        
        assert exc_info.value.code == 'INVALID_PATH_FORMAT'


class TestStreamingDetection:
    """Test streaming operation detection."""
    
    def test_message_stream_is_streaming(self):
        """Should detect message:stream as streaming."""
        assert is_streaming_operation('message:stream') is True
    
    def test_message_send_not_streaming(self):
        """Should detect message:send as not streaming."""
        assert is_streaming_operation('message:send') is False
    
    def test_agent_card_not_streaming(self):
        """Should detect agent card as not streaming."""
        assert is_streaming_operation('.well-known/agent-card.json') is False
    
    def test_tasks_not_streaming(self):
        """Should detect task operations as not streaming."""
        assert is_streaming_operation('tasks/task-123') is False
        assert is_streaming_operation('tasks') is False


class TestBackendHeaders:
    """Test backend header construction."""
    
    def test_adds_oauth_token(self):
        """Should add OAuth Bearer token."""
        client_headers = {
            'Content-Type': 'application/json'
        }
        
        backend_headers = build_backend_headers(client_headers, 'test-token-123')
        
        assert backend_headers['Authorization'] == 'Bearer test-token-123'
    
    def test_forwards_allowed_headers(self):
        """Should forward allowed headers."""
        client_headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'X-Custom-Header': 'custom-value'
        }
        
        backend_headers = build_backend_headers(client_headers, 'token')
        
        assert backend_headers['Content-Type'] == 'application/json'
        assert backend_headers['Accept'] == 'application/json'
        assert backend_headers['X-Custom-Header'] == 'custom-value'
    
    def test_excludes_authorization_header(self):
        """Should exclude client Authorization header."""
        client_headers = {
            'Authorization': 'Bearer client-jwt',
            'Content-Type': 'application/json'
        }
        
        backend_headers = build_backend_headers(client_headers, 'backend-token')
        
        # Should use backend token, not client token
        assert backend_headers['Authorization'] == 'Bearer backend-token'
    
    def test_excludes_hop_by_hop_headers(self):
        """Should exclude hop-by-hop headers."""
        client_headers = {
            'Host': 'gateway.example.com',
            'Connection': 'keep-alive',
            'Transfer-Encoding': 'chunked',
            'Content-Type': 'application/json'
        }
        
        backend_headers = build_backend_headers(client_headers, 'token')
        
        assert 'Host' not in backend_headers
        assert 'Connection' not in backend_headers
        assert 'Transfer-Encoding' not in backend_headers
        assert 'Content-Type' in backend_headers
    
    def test_adds_default_content_type(self):
        """Should add default Content-Type if missing."""
        client_headers = {}
        
        backend_headers = build_backend_headers(client_headers, 'token')
        
        assert backend_headers['Content-Type'] == 'application/json'


class TestProxyLambdaHandler:
    """Test Proxy Lambda handler integration."""
    
    @patch('proxy.handler.create_client_from_env')
    @patch('proxy.handler.OAuthClient')
    @patch('proxy.handler.forward_request')
    def test_successful_message_send(self, mock_forward, mock_oauth_class, mock_create_client):
        """Should successfully proxy message:send request."""
        # Mock DynamoDB client
        mock_db = Mock()
        mock_db.get_agent.return_value = {
            'agentId': 'billing-agent',
            'backendUrl': 'https://backend1.example.com',
            'status': 'active',
            'authConfig': {
                'tokenUrl': 'https://auth.example.com/token',
                'clientId': 'client-id',
                'clientSecretArn': 'arn:aws:secretsmanager:...',
                'scopes': ['agent:invoke']
            }
        }
        mock_db.get_allowed_agents_for_scopes.return_value = {'billing-agent'}
        mock_create_client.return_value = mock_db
        
        # Mock OAuth client
        mock_oauth = Mock()
        mock_oauth.get_access_token.return_value = 'backend-token-123'
        mock_oauth_class.return_value = mock_oauth
        
        # Mock forward_request
        mock_forward.return_value = {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'task': {'id': 'task-123'}})
        }
        
        # Set environment
        os.environ['AGENT_REGISTRY_TABLE'] = 'test-registry'
        os.environ['PERMISSIONS_TABLE'] = 'test-permissions'
        
        event = {
            'httpMethod': 'POST',
            'path': '/agents/billing-agent/message:send',
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'message': {'messageId': 'msg-123', 'role': 'ROLE_USER', 'parts': []}}),
            'requestContext': {
                'authorizer': {
                    'userId': 'user-123',
                    'scopes': 'billing:read',
                    'roles': 'user',
                    'username': 'testuser'
                }
            }
        }
        
        result = lambda_handler(event, None)
        
        assert result['statusCode'] == 200
        
        # Verify OAuth token was obtained
        mock_oauth.get_access_token.assert_called_once()
        
        # Verify request was forwarded
        mock_forward.assert_called_once()
        call_args = mock_forward.call_args[1]
        assert call_args['url'] == 'https://backend1.example.com/message:send'
        assert call_args['access_token'] == 'backend-token-123'
    
    @patch('proxy.handler.create_client_from_env')
    def test_agent_not_found(self, mock_create_client):
        """Should return 404 for non-existent agent."""
        mock_db = Mock()
        mock_db.get_agent.return_value = None
        mock_create_client.return_value = mock_db
        
        os.environ['AGENT_REGISTRY_TABLE'] = 'test-registry'
        os.environ['PERMISSIONS_TABLE'] = 'test-permissions'
        
        event = {
            'httpMethod': 'POST',
            'path': '/agents/nonexistent/message:send',
            'headers': {},
            'body': '{}',
            'requestContext': {
                'authorizer': {
                    'userId': 'user-123',
                    'scopes': '',
                    'roles': '',
                    'username': 'testuser'
                }
            }
        }
        
        result = lambda_handler(event, None)
        
        assert result['statusCode'] == 404
        body = json.loads(result['body'])
        assert body['error']['code'] == 'AGENT_NOT_FOUND'
    
    @patch('proxy.handler.create_client_from_env')
    def test_inactive_agent(self, mock_create_client):
        """Should return 404 for inactive agent."""
        mock_db = Mock()
        mock_db.get_agent.return_value = {
            'agentId': 'billing-agent',
            'status': 'inactive'
        }
        mock_create_client.return_value = mock_db
        
        os.environ['AGENT_REGISTRY_TABLE'] = 'test-registry'
        os.environ['PERMISSIONS_TABLE'] = 'test-permissions'
        
        event = {
            'httpMethod': 'POST',
            'path': '/agents/billing-agent/message:send',
            'headers': {},
            'body': '{}',
            'requestContext': {
                'authorizer': {
                    'userId': 'user-123',
                    'scopes': 'billing:read',
                    'roles': 'user',
                    'username': 'testuser'
                }
            }
        }
        
        result = lambda_handler(event, None)
        
        assert result['statusCode'] == 404
    
    @patch('proxy.handler.create_client_from_env')
    def test_permission_denied(self, mock_create_client):
        """Should return 403 when user lacks permission."""
        mock_db = Mock()
        mock_db.get_agent.return_value = {
            'agentId': 'admin-agent',
            'status': 'active'
        }
        mock_db.get_allowed_agents_for_scopes.return_value = set()  # No permissions
        mock_create_client.return_value = mock_db
        
        os.environ['AGENT_REGISTRY_TABLE'] = 'test-registry'
        os.environ['PERMISSIONS_TABLE'] = 'test-permissions'
        
        event = {
            'httpMethod': 'POST',
            'path': '/agents/admin-agent/message:send',
            'headers': {},
            'body': '{}',
            'requestContext': {
                'authorizer': {
                    'userId': 'user-123',
                    'scopes': 'billing:read',
                    'roles': 'user',
                    'username': 'testuser'
                }
            }
        }
        
        result = lambda_handler(event, None)
        
        assert result['statusCode'] == 403
        body = json.loads(result['body'])
        assert body['error']['code'] == 'PERMISSION_DENIED'
    
    @patch('proxy.handler.create_client_from_env')
    def test_agent_card_request_returns_cached_card(self, mock_create_client):
        """Should return cached agent card with rewritten URLs."""
        # Mock DynamoDB client
        mock_db = Mock()
        mock_db.get_agent.return_value = {
            'agentId': 'billing-agent',
            'backendUrl': 'https://backend1.example.com',
            'status': 'active',
            'cachedAgentCard': {
                'name': 'Billing Agent',
                'url': 'https://backend1.example.com',
                'supportedInterfaces': [
                    {
                        'url': 'https://backend1.example.com',
                        'protocolBinding': 'HTTP+JSON',
                        'protocolVersion': '0.3'
                    }
                ],
                'skills': []
            }
        }
        mock_db.get_allowed_agents_for_scopes.return_value = {'billing-agent'}
        mock_create_client.return_value = mock_db
        
        os.environ['AGENT_REGISTRY_TABLE'] = 'test-registry'
        os.environ['PERMISSIONS_TABLE'] = 'test-permissions'
        os.environ['GATEWAY_DOMAIN'] = 'gateway.example.com/v1'
        
        event = {
            'httpMethod': 'GET',
            'path': '/agents/billing-agent/.well-known/agent-card.json',
            'headers': {},
            'body': None,
            'requestContext': {
                'authorizer': {
                    'userId': 'user-123',
                    'scopes': 'billing:read',
                    'roles': 'user',
                    'username': 'testuser'
                }
            }
        }
        
        result = lambda_handler(event, None)
        
        assert result['statusCode'] == 200
        
        # Verify agent card is returned with rewritten URLs
        body = json.loads(result['body'])
        assert body['name'] == 'Billing Agent'
        assert body['url'] == 'https://gateway.example.com/v1/agents/billing-agent'
        assert body['supportedInterfaces'][0]['url'] == 'https://gateway.example.com/v1/agents/billing-agent'
    
    @patch('proxy.handler.create_client_from_env')
    def test_agent_card_not_proxied_to_backend(self, mock_create_client):
        """Should NOT proxy agent card requests to backend."""
        # Mock DynamoDB client
        mock_db = Mock()
        mock_db.get_agent.return_value = {
            'agentId': 'billing-agent',
            'status': 'active',
            'cachedAgentCard': {
                'name': 'Test',
                'url': 'https://backend.com',
                'supportedInterfaces': [],
                'skills': []
            }
        }
        mock_db.get_allowed_agents_for_scopes.return_value = {'billing-agent'}
        mock_create_client.return_value = mock_db
        
        os.environ['AGENT_REGISTRY_TABLE'] = 'test-registry'
        os.environ['PERMISSIONS_TABLE'] = 'test-permissions'
        os.environ['GATEWAY_DOMAIN'] = 'gateway.example.com/v1'
        
        event = {
            'httpMethod': 'GET',
            'path': '/agents/billing-agent/.well-known/agent-card.json',
            'headers': {},
            'body': None,
            'requestContext': {
                'authorizer': {
                    'userId': 'user-123',
                    'scopes': 'billing:read',
                    'roles': 'user',
                    'username': 'testuser'
                }
            }
        }
        
        # This should NOT call forward_request
        with patch('proxy.handler.forward_request') as mock_forward:
            result = lambda_handler(event, None)
            
            # Verify forward_request was NOT called
            mock_forward.assert_not_called()
            
            # Verify we got a successful response
            assert result['statusCode'] == 200

