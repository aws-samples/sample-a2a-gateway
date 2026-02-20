"""Unit tests for Lambda Authorizer."""

import pytest
import json
import os
from unittest.mock import Mock, patch, MagicMock
from jose import jwt
from jose.exceptions import JWTError, ExpiredSignatureError

# Add src to path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/lambdas'))

from authorizer.handler import lambda_handler, extract_token, generate_policy
from shared.errors import AuthenticationError, MISSING_AUTH_HEADER


class TestExtractToken:
    """Test token extraction from Authorization header."""
    
    def test_extract_valid_bearer_token(self):
        """Should extract token from valid Bearer header."""
        event = {
            'headers': {
                'Authorization': 'Bearer abc123xyz'
            }
        }
        
        token = extract_token(event)
        assert token == 'abc123xyz'
    
    def test_extract_token_case_insensitive(self):
        """Should handle lowercase 'authorization' header."""
        event = {
            'headers': {
                'authorization': 'Bearer abc123xyz'
            }
        }
        
        token = extract_token(event)
        assert token == 'abc123xyz'
    
    def test_missing_authorization_header(self):
        """Should raise error when Authorization header is missing."""
        event = {'headers': {}}
        
        with pytest.raises(AuthenticationError) as exc_info:
            extract_token(event)
        
        assert exc_info.value.code == MISSING_AUTH_HEADER
        assert exc_info.value.status_code == 401
    
    def test_invalid_header_format_no_bearer(self):
        """Should raise error when Bearer prefix is missing."""
        event = {
            'headers': {
                'Authorization': 'abc123xyz'
            }
        }
        
        with pytest.raises(AuthenticationError) as exc_info:
            extract_token(event)
        
        assert exc_info.value.code == MISSING_AUTH_HEADER
    
    def test_invalid_header_format_wrong_scheme(self):
        """Should raise error when using wrong auth scheme."""
        event = {
            'headers': {
                'Authorization': 'Basic abc123xyz'
            }
        }
        
        with pytest.raises(AuthenticationError) as exc_info:
            extract_token(event)
        
        assert exc_info.value.code == MISSING_AUTH_HEADER


class TestGeneratePolicy:
    """Test IAM policy generation with FGAC."""
    
    def test_generate_policy_with_allowed_agents(self):
        """Should generate policy with specific agent resource ARNs."""
        context = {
            'userId': 'user-123',
            'scopes': ['billing:read', 'billing:write'],
            'roles': ['user'],
            'username': 'testuser'
        }
        allowed_agents = {'billing-agent', 'support-agent'}
        
        policy = generate_policy(
            principal_id='user-123',
            effect='Allow',
            method_arn='arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/GET/agents',
            allowed_agents=allowed_agents,
            context=context
        )
        
        assert policy['principalId'] == 'user-123'
        assert policy['policyDocument']['Statement'][0]['Effect'] == 'Allow'
        assert policy['policyDocument']['Statement'][0]['Action'] == 'execute-api:Invoke'
        
        # Check resources include registry and specific agents
        resources = policy['policyDocument']['Statement'][0]['Resource']
        assert 'arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/GET/agents' in resources
        assert 'arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/*/agents/billing-agent/*' in resources
        assert 'arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/*/agents/support-agent/*' in resources
        
        # Check context is converted to strings
        assert policy['context']['userId'] == 'user-123'
        assert policy['context']['scopes'] == 'billing:read,billing:write'
        assert policy['context']['roles'] == 'user'
        assert policy['context']['username'] == 'testuser'
        assert 'billing-agent' in policy['context']['allowedAgents']
    
    def test_generate_policy_no_allowed_agents(self):
        """Should generate policy with only registry access when no agents allowed."""
        context = {
            'userId': 'user-123',
            'scopes': [],
            'roles': [],
            'username': 'testuser'
        }
        allowed_agents = set()
        
        policy = generate_policy(
            principal_id='user-123',
            effect='Allow',
            method_arn='arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/GET/agents',
            allowed_agents=allowed_agents,
            context=context
        )
        
        # Should only have registry endpoint
        resources = policy['policyDocument']['Statement'][0]['Resource']
        assert len(resources) == 1
        assert 'arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/GET/agents' in resources
    
    def test_generate_policy_empty_scopes(self):
        """Should handle empty scopes and roles."""
        context = {
            'userId': 'user-123',
            'scopes': [],
            'roles': [],
            'username': ''
        }
        allowed_agents = {'test-agent'}
        
        policy = generate_policy(
            principal_id='user-123',
            effect='Allow',
            method_arn='arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/GET/agents',
            allowed_agents=allowed_agents,
            context=context
        )
        
        assert policy['context']['scopes'] == ''
        assert policy['context']['roles'] == ''


class TestLambdaHandler:
    """Test Lambda handler integration."""
    
    @patch('authorizer.handler.create_client_from_env')
    @patch('authorizer.handler.create_validator_from_env')
    def test_successful_authorization_with_agents(self, mock_create_validator, mock_create_db_client):
        """Should return Allow policy with agent-specific resources for valid JWT."""
        # Mock JWT validator
        mock_validator = Mock()
        mock_validator.validate_token.return_value = {
            'sub': 'user-123',
            'scope': 'a2a-gateway/billing:read a2a-gateway/billing:write',
            'cognito:groups': ['user'],
            'username': 'testuser'
        }
        mock_validator.extract_user_context.return_value = {
            'userId': 'user-123',
            'scopes': ['billing:read', 'billing:write'],
            'roles': ['user'],
            'username': 'testuser'
        }
        mock_create_validator.return_value = mock_validator
        
        # Mock DynamoDB client
        mock_db_client = Mock()
        mock_db_client.get_allowed_agents_for_scopes.return_value = {'billing-agent', 'support-agent'}
        mock_create_db_client.return_value = mock_db_client
        
        event = {
            'type': 'REQUEST',
            'methodArn': 'arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/GET/agents',
            'headers': {
                'Authorization': 'Bearer valid-token'
            }
        }
        
        result = lambda_handler(event, None)
        
        assert result['principalId'] == 'user-123'
        assert result['policyDocument']['Statement'][0]['Effect'] == 'Allow'
        assert result['context']['userId'] == 'user-123'
        assert 'billing:read' in result['context']['scopes']
        
        # Verify agent-specific resources
        resources = result['policyDocument']['Statement'][0]['Resource']
        assert any('billing-agent' in r for r in resources)
        assert any('support-agent' in r for r in resources)
        
        # Verify DynamoDB was called with correct scopes
        mock_db_client.get_allowed_agents_for_scopes.assert_called_once_with(['billing:read', 'billing:write'])
    
    @patch('authorizer.handler.create_client_from_env')
    @patch('authorizer.handler.create_validator_from_env')
    def test_authorization_no_allowed_agents(self, mock_create_validator, mock_create_db_client):
        """Should return policy with only registry access when user has no agent permissions."""
        # Mock JWT validator
        mock_validator = Mock()
        mock_validator.validate_token.return_value = {
            'sub': 'user-123',
            'scope': '',
            'cognito:groups': [],
            'username': 'testuser'
        }
        mock_validator.extract_user_context.return_value = {
            'userId': 'user-123',
            'scopes': [],
            'roles': [],
            'username': 'testuser'
        }
        mock_create_validator.return_value = mock_validator
        
        # Mock DynamoDB client - no agents allowed
        mock_db_client = Mock()
        mock_db_client.get_allowed_agents_for_scopes.return_value = set()
        mock_create_db_client.return_value = mock_db_client
        
        event = {
            'type': 'REQUEST',
            'methodArn': 'arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/GET/agents',
            'headers': {
                'Authorization': 'Bearer valid-token'
            }
        }
        
        result = lambda_handler(event, None)
        
        # Should still get Allow policy (for registry endpoint)
        assert result['principalId'] == 'user-123'
        assert result['policyDocument']['Statement'][0]['Effect'] == 'Allow'
        
        # But only registry endpoint in resources
        resources = result['policyDocument']['Statement'][0]['Resource']
        assert len(resources) == 1
        assert resources[0].endswith('/GET/agents')
    
    @patch('authorizer.handler.create_validator_from_env')
    def test_missing_token_raises_unauthorized(self, mock_create_validator):
        """Should raise Unauthorized for missing token."""
        event = {
            'type': 'REQUEST',
            'methodArn': 'arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/GET/agents',
            'headers': {}
        }
        
        with pytest.raises(Exception) as exc_info:
            lambda_handler(event, None)
        
        assert str(exc_info.value) == 'Unauthorized'
    
    @patch('authorizer.handler.create_validator_from_env')
    def test_invalid_jwt_raises_unauthorized(self, mock_create_validator):
        """Should raise Unauthorized for invalid JWT."""
        # Mock validator to raise JWTError
        mock_validator = Mock()
        mock_validator.validate_token.side_effect = JWTError("Invalid signature")
        mock_create_validator.return_value = mock_validator
        
        event = {
            'type': 'REQUEST',
            'methodArn': 'arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/GET/agents',
            'headers': {
                'Authorization': 'Bearer invalid-token'
            }
        }
        
        with pytest.raises(Exception) as exc_info:
            lambda_handler(event, None)
        
        assert str(exc_info.value) == 'Unauthorized'
    
    @patch('authorizer.handler.create_validator_from_env')
    def test_expired_jwt_raises_unauthorized(self, mock_create_validator):
        """Should raise Unauthorized for expired JWT."""
        # Mock validator to raise ExpiredSignatureError
        mock_validator = Mock()
        mock_validator.validate_token.side_effect = ExpiredSignatureError("Token expired")
        mock_create_validator.return_value = mock_validator
        
        event = {
            'type': 'REQUEST',
            'methodArn': 'arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/GET/agents',
            'headers': {
                'Authorization': 'Bearer expired-token'
            }
        }
        
        with pytest.raises(Exception) as exc_info:
            lambda_handler(event, None)
        
        assert str(exc_info.value) == 'Unauthorized'
    
    @patch('authorizer.handler.create_client_from_env')
    @patch('authorizer.handler.create_validator_from_env')
    def test_dynamodb_error_raises_unauthorized(self, mock_create_validator, mock_create_db_client):
        """Should raise Unauthorized when DynamoDB lookup fails."""
        # Mock JWT validator
        mock_validator = Mock()
        mock_validator.validate_token.return_value = {'sub': 'user-123'}
        mock_validator.extract_user_context.return_value = {
            'userId': 'user-123',
            'scopes': ['billing:read'],
            'roles': [],
            'username': 'testuser'
        }
        mock_create_validator.return_value = mock_validator
        
        # Mock DynamoDB client to raise error
        mock_db_client = Mock()
        mock_db_client.get_allowed_agents_for_scopes.side_effect = Exception("DynamoDB error")
        mock_create_db_client.return_value = mock_db_client
        
        event = {
            'type': 'REQUEST',
            'methodArn': 'arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/GET/agents',
            'headers': {
                'Authorization': 'Bearer valid-token'
            }
        }
        
        with pytest.raises(Exception) as exc_info:
            lambda_handler(event, None)
        
        assert str(exc_info.value) == 'Unauthorized'
