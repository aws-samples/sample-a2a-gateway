"""URL rewriting utilities for Agent Cards."""

from typing import Dict, Any
from copy import deepcopy


def rewrite_agent_card_urls(agent_card: Dict[str, Any], agent_id: str, gateway_domain: str) -> Dict[str, Any]:
    """
    Rewrite backend URLs to gateway URLs in Agent Card.
    
    This ensures clients always route through the gateway instead of directly
    to backend servers.
    
    Args:
        agent_card: Original Agent Card with backend URLs
        agent_id: Agent identifier (used in gateway path)
        gateway_domain: Gateway domain (e.g., "gateway.example.com")
        
    Returns:
        Agent Card with rewritten URLs
    """
    # Deep copy to avoid modifying original
    rewritten_card = deepcopy(agent_card)
    
    # Construct gateway URL for this agent
    gateway_url = f"https://{gateway_domain}/agents/{agent_id}"
    
    # Rewrite main URL
    rewritten_card['url'] = gateway_url
    
    # Rewrite supportedInterfaces URLs
    if 'supportedInterfaces' in rewritten_card:
        for interface in rewritten_card['supportedInterfaces']:
            interface['url'] = gateway_url
    
    return rewritten_card


def extract_agent_id_from_url(url: str) -> str:
    """
    Extract agent ID from gateway URL.
    
    Args:
        url: Gateway URL (e.g., "https://gateway.example.com/agents/billing-agent")
        
    Returns:
        Agent ID
    """
    # URL format: https://gateway.example.com/agents/{agentId}
    parts = url.rstrip('/').split('/')
    
    if len(parts) >= 2 and parts[-2] == 'agents':
        return parts[-1]
    
    raise ValueError(f"Invalid gateway URL format: {url}")
