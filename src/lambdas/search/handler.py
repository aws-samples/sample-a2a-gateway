"""Search Lambda for semantic agent discovery."""

import os
import json
import logging
from typing import Dict, Any, List, Set

# Add parent directory to path for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.dynamodb_client import create_client_from_env as create_db_client
from shared.s3vectors_client import create_client_from_env as create_vectors_client
from shared.embedding_client import EmbeddingClient
from shared.url_rewriter import rewrite_agent_card_urls
from shared.errors import GatewayError, BadRequestError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Search Lambda handler.
    
    Performs semantic search over agents filtered by user permissions.
    
    Args:
        event: API Gateway event with user context from authorizer
        context: Lambda context
        
    Returns:
        API Gateway response with matching Agent Cards
    """
    try:
        logger.info("Search Lambda invoked")
        
        # Extract user context from authorizer
        user_context = extract_user_context(event)
        logger.info(f"User: {user_context['userId']}, Scopes: {user_context['scopes']}")
        
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            raise BadRequestError('INVALID_JSON', 'Invalid JSON in request body')
        
        query = body.get('query', '').strip()
        if not query:
            raise BadRequestError('MISSING_QUERY', 'Query parameter is required')
        
        top_k = body.get('topK', 10)
        if not isinstance(top_k, int) or top_k < 1 or top_k > 100:
            raise BadRequestError('INVALID_TOP_K', 'topK must be an integer between 1 and 100')
        
        # Get gateway domain from environment
        gateway_domain = os.environ['GATEWAY_DOMAIN']
        
        # Initialize clients
        db_client = create_db_client()
        vectors_client = create_vectors_client()
        embedding_client = EmbeddingClient()
        
        # Get allowed agents for user's scopes
        allowed_agent_ids = db_client.get_allowed_agents_for_scopes(user_context['scopes'])
        logger.info(f"User has access to {len(allowed_agent_ids)} agents")
        
        if not allowed_agent_ids:
            # User has no permissions, return empty results
            return build_response(200, {"results": [], "query": query})
        
        # Generate query embedding
        logger.info(f"Generating embedding for query: {query[:50]}...")
        query_embedding = embedding_client.get_embedding(query)
        
        # Query S3 Vectors (fetch more than needed for post-filtering)
        fetch_count = min(top_k * 5, 100)  # Fetch 5x to account for filtering
        logger.info(f"Querying S3 Vectors for top {fetch_count} results")
        
        vector_results = vectors_client.query(
            query_embedding=query_embedding,
            top_k=fetch_count
        )
        
        # Filter by permissions
        filtered_results = [
            r for r in vector_results
            if r.get('metadata', {}).get('agentId') in allowed_agent_ids
        ]
        
        logger.info(f"Filtered to {len(filtered_results)} permitted results")
        
        # Get agent cards for top results
        agent_cards = []
        for result in filtered_results[:top_k]:
            agent_id = result['metadata']['agentId']
            agent = db_client.get_agent(agent_id)
            
            if agent and agent.get('cachedAgentCard'):
                # Rewrite URLs to point to gateway
                rewritten_card = rewrite_agent_card_urls(
                    agent['cachedAgentCard'],
                    agent_id,
                    gateway_domain
                )
                agent_cards.append({
                    "agentCard": rewritten_card,
                    "score": 1 - result.get('distance', 0)  # Convert distance to similarity
                })
        
        logger.info(f"Returning {len(agent_cards)} results")
        
        return build_response(200, {
            "results": agent_cards,
            "query": query,
            "totalMatches": len(filtered_results)
        })
        
    except GatewayError as e:
        logger.error(f"Gateway error: {e.code} - {e.message}")
        return build_response(e.status_code, e.to_dict())
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return build_response(500, {
            'error': {
                'code': 'INTERNAL_ERROR',
                'message': 'Internal server error'
            }
        })


def extract_user_context(event: Dict[str, Any]) -> Dict[str, Any]:
    """Extract user context from API Gateway event."""
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


def build_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """Build API Gateway response."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Authorization, Content-Type',
            'Access-Control-Allow-Methods': 'POST, OPTIONS'
        },
        'body': json.dumps(body)
    }
