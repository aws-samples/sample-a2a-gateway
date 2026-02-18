"""Lambda Authorizer for JWT validation and FGAC context injection."""

import os
import json
import logging
from typing import Dict, Any

# Add parent directory to path for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.jwt_validator import create_validator_from_env
from shared.errors import AuthenticationError, MISSING_AUTH_HEADER, INVALID_JWT_SIGNATURE, EXPIRED_JWT, INVALID_JWT_ISSUER
from jose.exceptions import JWTError, ExpiredSignatureError, JWTClaimsError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda Authorizer handler.
    
    Validates JWT from Authorization header and returns IAM policy with user context.
    
    Args:
        event: API Gateway authorizer event
        context: Lambda context
        
    Returns:
        IAM policy document with user context
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
        
        # Generate Allow policy with user context
        policy = generate_policy(
            principal_id=user_context['userId'],
            effect='Allow',
            resource=event['methodArn'],
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


def generate_policy(principal_id: str, effect: str, resource: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate IAM policy document.
    
    Args:
        principal_id: User identifier
        effect: 'Allow' or 'Deny'
        resource: Method ARN
        context: User context to pass to downstream Lambdas
        
    Returns:
        IAM policy document
    """
    # Convert resource to wildcard to allow all methods
    # This allows the same policy to work for all endpoints
    resource_parts = resource.split('/')
    if len(resource_parts) >= 2:
        # Convert "arn:aws:execute-api:region:account:api-id/stage/METHOD/path"
        # to "arn:aws:execute-api:region:account:api-id/stage/*/*"
        base = '/'.join(resource_parts[:2])
        resource = f"{base}/*/*"
    
    policy = {
        'principalId': principal_id,
        'policyDocument': {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Action': 'execute-api:Invoke',
                    'Effect': effect,
                    'Resource': resource
                }
            ]
        },
        'context': {
            # API Gateway context values must be strings, numbers, or booleans
            # Convert lists to comma-separated strings
            'userId': context['userId'],
            'scopes': ','.join(context['scopes']),  # Convert list to CSV
            'roles': ','.join(context['roles']),    # Convert list to CSV
            'username': context.get('username', '')
        }
    }
    
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
    
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))
