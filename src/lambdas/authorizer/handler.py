"""Lambda Authorizer for JWT validation and FGAC enforcement."""

import os
import json
import logging
from typing import Dict, Any, List, Set

# Add parent directory to path for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.jwt_validator import create_validator_from_env
from shared.dynamodb_client import create_client_from_env
from shared.errors import AuthenticationError, MISSING_AUTH_HEADER, INVALID_JWT_SIGNATURE, EXPIRED_JWT, INVALID_JWT_ISSUER
from jose.exceptions import JWTError, ExpiredSignatureError, JWTClaimsError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda Authorizer handler.
    
    Validates JWT from Authorization header, performs FGAC lookup in DynamoDB,
    and returns IAM policy that only allows access to permitted agents.
    
    Args:
        event: API Gateway authorizer event
        context: Lambda context
        
    Returns:
        IAM policy document with agent-specific resource ARNs
    """
    try:
        logger.info(f"Authorizer invoked for method: {event.get('methodArn')}")
        
        # Extract token from Authorization header
        token = extract_token(event)
        
        # Validate JWT
        validator = create_validator_from_env()
        claims = validator.validate_token(token)
        
        # Extract user context
        user_context = validator.extract_user_context(claims)
        
        logger.info(f"Token validated for user: {user_context['userId']}, scopes: {user_context['scopes']}")
        
        # Query DynamoDB for allowed agents based on user's scopes
        db_client = create_client_from_env()
        allowed_agents = db_client.get_allowed_agents_for_scopes(user_context['scopes'])
        
        logger.info(f"User {user_context['userId']} allowed agents: {allowed_agents}")
        
        # Generate policy with specific agent resource ARNs
        policy = generate_policy(
            principal_id=user_context['userId'],
            effect='Allow',
            method_arn=event['methodArn'],
            allowed_agents=allowed_agents,
            context=user_context
        )
        
        return policy
        
    except AuthenticationError as e:
        logger.warning(f"Authentication failed: {e.code} - {e.message}")
        # Return Deny policy for authentication failures
        raise Exception('Unauthorized')
        
    except Exception as e:
        logger.error(f"Unexpected error in authorizer: {str(e)}", exc_info=True)
        # Return Deny policy for unexpected errors
        raise Exception('Unauthorized')


def extract_token(event: Dict[str, Any]) -> str:
    """
    Extract JWT token from Authorization header.
    
    Args:
        event: API Gateway authorizer event
        
    Returns:
        JWT token string
        
    Raises:
        AuthenticationError: If token is missing or malformed
    """
    # Get Authorization header
    auth_header = event.get('headers', {}).get('Authorization') or event.get('headers', {}).get('authorization')
    
    if not auth_header:
        raise AuthenticationError(
            MISSING_AUTH_HEADER,
            "Missing Authorization header"
        )
    
    # Extract Bearer token
    parts = auth_header.split()
    
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        raise AuthenticationError(
            MISSING_AUTH_HEADER,
            "Invalid Authorization header format. Expected: Bearer <token>"
        )
    
    return parts[1]


def generate_policy(
    principal_id: str,
    effect: str,
    method_arn: str,
    allowed_agents: Set[str],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generate IAM policy document with agent-specific resource ARNs.
    
    Args:
        principal_id: User identifier
        effect: 'Allow' or 'Deny'
        method_arn: Original method ARN from request
        allowed_agents: Set of agent IDs the user can access
        context: User context to pass to downstream Lambdas
        
    Returns:
        IAM policy document with specific agent resources
    """
    # Parse method ARN to extract base
    # Format: arn:aws:execute-api:region:account:api-id/stage/METHOD/path
    arn_parts = method_arn.split('/')
    if len(arn_parts) >= 2:
        # Get base: arn:aws:execute-api:region:account:api-id/stage
        base_arn = '/'.join(arn_parts[:2])
    else:
        base_arn = method_arn
    
    # Build resource ARNs for each allowed agent
    # Format: base/*/agents/{agentId}/*
    resources = []
    
    # Always allow GET /agents (registry endpoint) - it does its own filtering
    resources.append(f"{base_arn}/GET/agents")
    
    # Add specific agent paths for each allowed agent
    for agent_id in allowed_agents:
        # Allow all methods and sub-paths for this agent
        resources.append(f"{base_arn}/*/agents/{agent_id}/*")
    
    # If no agents allowed, we still return a valid policy
    # The user can access /agents (registry) but no specific agents
    
    policy = {
        'principalId': principal_id,
        'policyDocument': {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Action': 'execute-api:Invoke',
                    'Effect': effect,
                    'Resource': resources
                }
            ]
        },
        'context': {
            # API Gateway context values must be strings, numbers, or booleans
            # Convert lists to comma-separated strings
            'userId': context['userId'],
            'scopes': ','.join(context['scopes']),  # Convert list to CSV
            'roles': ','.join(context['roles']),    # Convert list to CSV
            'username': context.get('username', ''),
            'allowedAgents': ','.join(sorted(allowed_agents))  # Pass to downstream for logging
        }
    }
    
    logger.info(f"Generated policy with {len(resources)} resource ARNs for {len(allowed_agents)} agents")
    
    return policy


# For local testing
if __name__ == '__main__':
    # Mock event for testing
    test_event = {
        'type': 'REQUEST',
        'methodArn': 'arn:aws:execute-api:us-east-1:123456789012:abcdef123/prod/GET/agents',
        'headers': {
            'Authorization': 'Bearer eyJraWQiOiJ...'  # Replace with real token for testing
        }
    }
    
    # Set environment variables for testing
    os.environ['COGNITO_JWKS_URI'] = 'https://cognito-idp.us-east-1.amazonaws.com/us-east-1_xxxxx/.well-known/jwks.json'
    os.environ['COGNITO_ISSUER_URL'] = 'https://cognito-idp.us-east-1.amazonaws.com/us-east-1_xxxxx'
    os.environ['AGENT_REGISTRY_TABLE'] = 'a2a-gateway-poc-agent-registry'
    os.environ['PERMISSIONS_TABLE'] = 'a2a-gateway-poc-permissions'
    
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))
