"""Unit tests for Registry Lambda."""

import pytest
import json
import os
from unittest.mock import Mock, patch, MagicMock

# Add src to path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/lambdas'))

from registry.handler import lambda_handler, extract_user_context
from shared.url_rewriter import rewrite_agent_card_urls


class TestExtractUserContext:
    """Test user context extraction from API Gateway event."""
    
    def test_extract_context_with_scopes(self):
        """Should extract user context with multiple scopes."""
        event = {
            'requestContext': {
                'authorizer': {
                    'userId': 'user-123',
                    'scopes': 'billing:read,billing:write,search:read',
                    'roles': 'user,admin',
                    'username': 'testuser'
                }
            }
        }
        
        context = extract_user_context(event)
        
        assert context['userId'] == 'user-123'
        assert context['scopes'] == ['billing:read', 'billing:write', 'search:read']
        assert context['roles'] == ['user', 'admin']
        assert context['username'] == 'testuser'
    
    def test_extract_context_empty_scopes(self):
        """Should handle empty scopes."""
        event = {
            'requestContext': {
                'authorizer': {
                    'userId': 'user-123',
                    'scopes': '',
                    'roles': '',
                    'username': 'testuser'
                }
            }
        }
        
        context = extract_user_context(event)
        
        assert context['userId'] == 'user-123'
        assert context['scopes'] == []
        assert context['roles'] == []
    
    def test_extract_context_single_scope(self):
        """Should handle single scope."""
        event = {
            'requestContext': {
                'authorizer': {
                    'userId': 'user-123',
                    'scopes': 'billing:read',
                    'roles': 'user',
                    'username': 'testuser'
                }
            }
        }
        
        context = extract_user_context(event)
        
        assert context['scopes'] == ['billing:read']
        assert context['roles'] == ['user']


class TestURLRewriting:
    """Test URL rewriting in Agent Cards."""
    
    def test_rewrite_basic_agent_card(self):
        """Should rewrite URLs in basic Agent Card."""
        agent_card = {
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
        
        rewritten = rewrite_agent_card_urls(agent_card, 'billing-agent', 'gateway.example.com')
        
        assert rewritten['url'] == 'https://gateway.example.com/agents/billing-agent'
        assert rewritten['supportedInterfaces'][0]['url'] == 'https://gateway.example.com/agents/billing-agent'
        assert rewritten['name'] == 'Billing Agent'  # Other fields unchanged
    
    def test_rewrite_multiple_interfaces(self):
        """Should rewrite URLs in multiple interfaces."""
        agent_card = {
            'name': 'Test Agent',
            'url': 'https://backend.example.com',
            'supportedInterfaces': [
                {
                    'url': 'https://backend.example.com',
                    'protocolBinding': 'HTTP+JSON',
                    'protocolVersion': '0.3'
                },
                {
                    'url': 'https://backend.example.com',
                    'protocolBinding': 'HTTP+JSON',
                    'protocolVersion': '0.2'
                }
            ]
        }
        
        rewritten = rewrite_agent_card_urls(agent_card, 'test-agent', 'gateway.example.com')
        
        for interface in rewritten['supportedInterfaces']:
            assert interface['url'] == 'https://gateway.example.com/agents/test-agent'
    
    def test_rewrite_preserves_original(self):
        """Should not modify original Agent Card."""
        original = {
            'name': 'Test Agent',
            'url': 'https://backend.example.com',
            'supportedInterfaces': [
                {
                    'url': 'https://backend.example.com',
                    'protocolBinding': 'HTTP+JSON',
                    'protocolVersion': '0.3'
                }
            ]
        }
        
        original_url = original['url']
        rewritten = rewrite_agent_card_urls(original, 'test-agent', 'gateway.example.com')
        
        # Original should be unchanged
        assert original['url'] == original_url
        assert original['url'] != rewritten['url']


class TestRegistryLambdaHandler:
    """Test Registry Lambda handler integration."""
    
    @patch('registry.handler.create_client_from_env')
    def test_successful_discovery_with_permissions(self, mock_create_client):
        """Should return filtered Agent Cards for user with permissions."""
        # Mock DynamoDB client
        mock_db = Mock()
        mock_db.get_allowed_agents_for_scopes.return_value = {'billing-agent', 'search-agent'}
        mock_db.get_active_agents.return_value = [
            {
                'agentId': 'billing-agent',
                'name': 'Billing Agent',
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
            },
            {
                'agentId': 'search-agent',
                'name': 'Search Agent',
                'status': 'active',
                'cachedAgentCard': {
                    'name': 'Search Agent',
                    'url': 'https://backend2.example.com',
                    'supportedInterfaces': [
                        {
                            'url': 'https://backend2.example.com',
                            'protocolBinding': 'HTTP+JSON',
                            'protocolVersion': '0.3'
                        }
                    ],
                    'skills': []
                }
            },
            {
                'agentId': 'admin-agent',
                'name': 'Admin Agent',
                'status': 'active',
                'cachedAgentCard': {
                    'name': 'Admin Agent',
                    'url': 'https://backend3.example.com',
                    'supportedInterfaces': [],
                    'skills': []
                }
            }
        ]
        mock_create_client.return_value = mock_db
        
        # Set environment
        os.environ['GATEWAY_DOMAIN'] = 'gateway.example.com'
        os.environ['AGENT_REGISTRY_TABLE'] = 'test-registry'
        os.environ['PERMISSIONS_TABLE'] = 'test-permissions'
        
        event = {
            'requestContext': {
                'authorizer': {
                    'userId': 'user-123',
                    'scopes': 'billing:read,search:read',
                    'roles': 'user',
                    'username': 'testuser'
                }
            }
        }
        
        result = lambda_handler(event, None)
        
        assert result['statusCode'] == 200
        
        body = json.loads(result['body'])
        assert len(body) == 2  # Only billing and search agents
        
        # Verify URLs are rewritten
        agent_names = {agent['name'] for agent in body}
        assert 'Billing Agent' in agent_names
        assert 'Search Agent' in agent_names
        assert 'Admin Agent' not in agent_names  # Filtered out
        
        # Verify URL rewriting
        for agent in body:
            assert agent['url'].startswith('https://gateway.example.com/agents/')
            for interface in agent['supportedInterfaces']:
                assert interface['url'].startswith('https://gateway.example.com/agents/')
    
    @patch('registry.handler.create_client_from_env')
    def test_empty_result_no_permissions(self, mock_create_client):
        """Should return empty array when user has no permissions."""
        # Mock DynamoDB client
        mock_db = Mock()
        mock_db.get_allowed_agents_for_scopes.return_value = set()  # No permissions
        mock_db.get_active_agents.return_value = [
            {
                'agentId': 'billing-agent',
                'name': 'Billing Agent',
                'status': 'active',
                'cachedAgentCard': {'name': 'Billing Agent', 'url': 'https://backend.com', 'supportedInterfaces': []}
            }
        ]
        mock_create_client.return_value = mock_db
        
        os.environ['GATEWAY_DOMAIN'] = 'gateway.example.com'
        os.environ['AGENT_REGISTRY_TABLE'] = 'test-registry'
        os.environ['PERMISSIONS_TABLE'] = 'test-permissions'
        
        event = {
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
        
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body == []  # Empty array
    
    @patch('registry.handler.create_client_from_env')
    def test_filters_inactive_agents(self, mock_create_client):
        """Should not return inactive agents."""
        # Mock DynamoDB client
        mock_db = Mock()
        mock_db.get_allowed_agents_for_scopes.return_value = {'billing-agent'}
        mock_db.get_active_agents.return_value = []  # get_active_agents already filters
        mock_create_client.return_value = mock_db
        
        os.environ['GATEWAY_DOMAIN'] = 'gateway.example.com'
        os.environ['AGENT_REGISTRY_TABLE'] = 'test-registry'
        os.environ['PERMISSIONS_TABLE'] = 'test-permissions'
        
        event = {
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
        body = json.loads(result['body'])
        assert body == []
    
    @patch('registry.handler.create_client_from_env')
    def test_skips_agents_without_cached_card(self, mock_create_client):
        """Should skip agents that don't have cached Agent Card."""
        # Mock DynamoDB client
        mock_db = Mock()
        mock_db.get_allowed_agents_for_scopes.return_value = {'billing-agent'}
        mock_db.get_active_agents.return_value = [
            {
                'agentId': 'billing-agent',
                'name': 'Billing Agent',
                'status': 'active',
                'cachedAgentCard': None  # No cached card
            }
        ]
        mock_create_client.return_value = mock_db
        
        os.environ['GATEWAY_DOMAIN'] = 'gateway.example.com'
        os.environ['AGENT_REGISTRY_TABLE'] = 'test-registry'
        os.environ['PERMISSIONS_TABLE'] = 'test-permissions'
        
        event = {
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
        body = json.loads(result['body'])
        assert body == []  # Skipped agent without card
