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
    """Test IAM policy generation."""
    
    def test_generate_allow_policy(self):
        """Should generate Allow policy with user context."""
        context = {
            'userId': 'user-123',
            'scopes': ['billing:read', 'billing:write'],
            'roles': ['user'],
            'username': 'testuser'
        }
        
        policy = generate_policy(
            principal_id='user-123',
            effect='Allow',
            resource='arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/GET/agents',
            context=context
        )
        
        assert policy['principalId'] == 'user-123'
        assert policy['policyDocument']['Statement'][0]['Effect'] == 'Allow'
        assert policy['policyDocument']['Statement'][0]['Action'] == 'execute-api:Invoke'
        
        # Check context is converted to strings
        assert policy['context']['userId'] == 'user-123'
        assert policy['context']['scopes'] == 'billing:read,billing:write'
        assert policy['context']['roles'] == 'user'
        assert policy['context']['username'] == 'testuser'
    
    def test_generate_policy_wildcard_resource(self):
        """Should convert specific resource to wildcard."""
        context = {
            'userId': 'user-123',
            'scopes': [],
            'roles': [],
            'username': 'testuser'
        }
        
        policy = generate_policy(
            principal_id='user-123',
            effect='Allow',
            resource='arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/GET/agents/billing-agent',
            context=context
        )
        
        # Should convert to wildcard
        resource = policy['policyDocument']['Statement'][0]['Resource']
        assert resource.endswith('/*/*')
    
    def test_generate_policy_empty_scopes(self):
        """Should handle empty scopes and roles."""
        context = {
            'userId': 'user-123',
            'scopes': [],
            'roles': [],
            'username': ''
        }
        
        policy = generate_policy(
            principal_id='user-123',
            effect='Allow',
            resource='arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/GET/agents',
            context=context
        )
        
        assert policy['context']['scopes'] == ''
        assert policy['context']['roles'] == ''


class TestLambdaHandler:
    """Test Lambda handler integration."""
    
    @patch('authorizer.handler.create_validator_from_env')
    def test_successful_authorization(self, mock_create_validator):
        """Should return Allow policy for valid JWT."""
        # Mock validator
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
