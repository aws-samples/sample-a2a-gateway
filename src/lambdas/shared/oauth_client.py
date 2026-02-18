"""OAuth 2.0 Client Credentials flow implementation."""

import time
import boto3
import requests
import json
from typing import Dict, Any, Optional
from botocore.exceptions import ClientError


class OAuthTokenCache:
    """In-memory cache for OAuth tokens with expiration tracking."""
    
    def __init__(self):
        self._tokens: Dict[str, Dict[str, Any]] = {}
    
    def get(self, agent_id: str) -> Optional[str]:
        """
        Get cached token if valid.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            Access token or None if expired/missing
        """
        if agent_id not in self._tokens:
            return None
        
        token_data = self._tokens[agent_id]
        
        # Check if token is expired (with 60-second buffer)
        if time.time() >= token_data['expires_at'] - 60:
            del self._tokens[agent_id]
            return None
        
        return token_data['access_token']
    
    def set(self, agent_id: str, access_token: str, expires_in: int):
        """
        Cache token with expiration.
        
        Args:
            agent_id: Agent identifier
            access_token: OAuth access token
            expires_in: Token lifetime in seconds
        """
        self._tokens[agent_id] = {
            'access_token': access_token,
            'expires_at': time.time() + expires_in
        }


# Global token cache (persists across Lambda invocations)
_token_cache = OAuthTokenCache()


class OAuthClient:
    """OAuth 2.0 Client Credentials flow client."""
    
    def __init__(self, secrets_manager_client=None):
        """
        Initialize OAuth client.
        
        Args:
            secrets_manager_client: Boto3 Secrets Manager client (optional)
        """
        self.secrets_manager = secrets_manager_client or boto3.client('secretsmanager')
        self.token_cache = _token_cache
    
    def get_access_token(self, agent_id: str, auth_config: Dict[str, Any]) -> str:
        """
        Get OAuth access token for agent (with caching).
        
        Args:
            agent_id: Agent identifier
            auth_config: OAuth configuration from agent registry
            
        Returns:
            Access token
            
        Raises:
            Exception: If token acquisition fails
        """
        # Check cache first
        cached_token = self.token_cache.get(agent_id)
        if cached_token:
            return cached_token
        
        # Acquire new token
        access_token, expires_in = self._acquire_token(auth_config)
        
        # Cache token
        self.token_cache.set(agent_id, access_token, expires_in)
        
        return access_token
    
    def _acquire_token(self, auth_config: Dict[str, Any]) -> tuple[str, int]:
        """
        Acquire OAuth token via Client Credentials flow.
        
        Args:
            auth_config: OAuth configuration with tokenUrl, clientId, clientSecretArn, scopes
            
        Returns:
            Tuple of (access_token, expires_in)
            
        Raises:
            Exception: If token acquisition fails
        """
        # Retrieve client secret from Secrets Manager
        try:
            response = self.secrets_manager.get_secret_value(
                SecretId=auth_config['clientSecretArn']
            )
            secret_data = json.loads(response['SecretString'])
            client_secret = secret_data['clientSecret']
        except ClientError as e:
            raise Exception(f"Failed to retrieve OAuth client secret: {e}")
        
        # Prepare token request
        token_url = auth_config['tokenUrl']
        client_id = auth_config['clientId']
        scopes = auth_config.get('scopes', [])
        
        # Build request data
        data = {
            'grant_type': 'client_credentials',
            'client_id': client_id,
            'client_secret': client_secret
        }
        
        # Add scopes if provided
        if scopes:
            data['scope'] = ' '.join(scopes) if isinstance(scopes, list) else scopes
        
        # Request token
        try:
            response = requests.post(
                token_url,
                data=data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=10
            )
            
            if response.status_code != 200:
                raise Exception(
                    f"OAuth token request failed: {response.status_code} - {response.text}"
                )
            
            token_data = response.json()
            
            # Extract token and expiration
            access_token = token_data.get('access_token')
            expires_in = token_data.get('expires_in', 3600)  # Default 1 hour
            
            if not access_token:
                raise Exception("OAuth response missing access_token")
            
            return access_token, expires_in
            
        except requests.RequestException as e:
            raise Exception(f"OAuth token request failed: {e}")
