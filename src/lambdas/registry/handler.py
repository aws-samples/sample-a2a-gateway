"""Registry Lambda for agent discovery with FGAC."""

import os
import json
import logging
from typing import Dict, Any, List

# Add parent directory to path for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.dynamodb_client import create_client_from_env
from shared.url_rewriter import rewrite_agent_card_urls
from shared.errors import GatewayError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Registry Lambda handler.
    
    Returns list of Agent Cards filtered by user permissions with URLs rewritten
    to point to the gateway.
    
    Args:
        event: API Gateway event with user context from authorizer
        context: Lambda context
        
    Returns:
        API Gateway response with Agent Card array
    """
    try:
        logger.info("Registry Lambda invoked")
        
        # Extract user context from authorizer
        user_context = extract_user_context(event)
        logger.info(f"User: {user_context['userId']}, Scopes: {user_context['scopes']}")
        
        # Get gateway domain from environment
        gateway_domain = os.environ['GATEWAY_DOMAIN']
        
        # Initialize DynamoDB client
        db_client = create_client_from_env()
        
        # Get allowed agents for user's scopes
        allowed_agent_ids = db_client.get_allowed_agents_for_scopes(user_context['scopes'])
        logger.info(f"Allowed agents for user: {allowed_agent_ids}")
        
        # Get all active agents
        all_agents = db_client.get_active_agents()
        
        # Filter agents by permissions
        accessible_agents = [
            agent for agent in all_agents
            if agent['agentId'] in allowed_agent_ids
        ]
        
        logger.info(f"Returning {len(accessible_agents)} accessible agents")
        
        # Build Agent Card array with URL rewriting
        agent_cards = []
        for agent in accessible_agents:
            # Get cached Agent Card
            cached_card = agent.get('cachedAgentCard')
            
            if not cached_card:
                logger.warning(f"Agent {agent['agentId']} has no cached Agent Card, skipping")
                continue
            
            # Rewrite URLs to point to gateway
            rewritten_card = rewrite_agent_card_urls(
                cached_card,
                agent['agentId'],
                gateway_domain
            )
            
            agent_cards.append(rewritten_card)
        
        # Return Agent Card array
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Authorization, Content-Type',
                'Access-Control-Allow-Methods': 'GET, OPTIONS'
            },
            'body': json.dumps(agent_cards)
        }
        
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


def extract_user_context(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract user context from API Gateway event.
    
    The Lambda Authorizer injects user context into the request context.
    Context values are strings, so we need to parse CSV lists.
    
    Args:
        event: API Gateway event
        
    Returns:
        Dict with userId, scopes, roles
    """
    request_context = event.get('requestContext', {})
    authorizer_context = request_context.get('authorizer', {})
    
    # Extract context values (all are strings from authorizer)
    user_id = authorizer_context.get('userId', '')
    scopes_csv = authorizer_context.get('scopes', '')
    roles_csv = authorizer_context.get('roles', '')
    
    # Parse CSV strings back to lists
    scopes = [s.strip() for s in scopes_csv.split(',') if s.strip()]
    roles = [r.strip() for r in roles_csv.split(',') if r.strip()]
    
    return {
        'userId': user_id,
        'scopes': scopes,
        'roles': roles,
        'username': authorizer_context.get('username', '')
    }


# For local testing
if __name__ == '__main__':
    # Mock event for testing
    test_event = {
        'requestContext': {
            'authorizer': {
                'userId': 'user-123',
                'scopes': 'billing:read,billing:write',
                'roles': 'user',
                'username': 'testuser'
            }
        }
    }
    
    # Set environment variables for testing
    os.environ['GATEWAY_DOMAIN'] = 'gateway.example.com'
    os.environ['AGENT_REGISTRY_TABLE'] = 'a2a-gateway-poc-agent-registry'
    os.environ['PERMISSIONS_TABLE'] = 'a2a-gateway-poc-permissions'
    
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))
