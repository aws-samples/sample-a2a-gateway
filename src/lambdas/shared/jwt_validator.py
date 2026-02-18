"""JWT validation utilities for Cognito tokens."""

import json
import time
from typing import Dict, Any, Optional
from urllib.request import urlopen
from jose import jwt, jwk
from jose.exceptions import JWTError, ExpiredSignatureError, JWTClaimsError


class JWTValidator:
    """Validates Cognito JWTs and extracts claims."""
    
    def __init__(self, jwks_uri: str, issuer: str, audience: Optional[str] = None):
        """
        Initialize JWT validator.
        
        Args:
            jwks_uri: URL to Cognito JWKS endpoint
            issuer: Expected token issuer (Cognito User Pool URL)
            audience: Expected audience (client_id), optional
        """
        self.jwks_uri = jwks_uri
        self.issuer = issuer
        self.audience = audience
        self._jwks_cache: Optional[Dict[str, Any]] = None
        self._jwks_cache_time: float = 0
        self._jwks_cache_ttl: int = 3600  # 1 hour
    
    def _get_jwks(self) -> Dict[str, Any]:
        """Fetch JWKS from Cognito, with caching."""
        current_time = time.time()
        
        # Return cached JWKS if still valid
        if self._jwks_cache and (current_time - self._jwks_cache_time) < self._jwks_cache_ttl:
            return self._jwks_cache
        
        # Fetch fresh JWKS
        with urlopen(self.jwks_uri) as response:
            jwks = json.loads(response.read())
        
        self._jwks_cache = jwks
        self._jwks_cache_time = current_time
        
        return jwks
    
    def _get_signing_key(self, token: str) -> Dict[str, Any]:
        """Get the signing key for the token from JWKS."""
        # Decode header without verification to get kid
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get('kid')
        
        if not kid:
            raise JWTError("Token missing 'kid' in header")
        
        # Find matching key in JWKS
        jwks = self._get_jwks()
        
        for key in jwks.get('keys', []):
            if key.get('kid') == kid:
                return jwk.construct(key)
        
        raise JWTError(f"Unable to find signing key with kid: {kid}")
    
    def validate_token(self, token: str) -> Dict[str, Any]:
        """
        Validate JWT and return claims.
        
        Args:
            token: JWT token string
            
        Returns:
            Dict containing validated claims
            
        Raises:
            JWTError: If token is invalid
            ExpiredSignatureError: If token is expired
            JWTClaimsError: If claims validation fails
        """
        # Get signing key
        signing_key = self._get_signing_key(token)
        
        # Verify token
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=['RS256'],
            issuer=self.issuer,
            audience=self.audience,
            options={
                'verify_signature': True,
                'verify_exp': True,
                'verify_iss': True,
                'verify_aud': self.audience is not None,
            }
        )
        
        return claims
    
    def extract_user_context(self, claims: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract user context from validated claims.
        
        Args:
            claims: Validated JWT claims
            
        Returns:
            Dict with userId, scopes, and roles
        """
        # Extract user ID (sub claim)
        user_id = claims.get('sub', '')
        
        # Extract scopes from 'scope' claim (space-separated string)
        # Cognito returns scopes as "a2a-gateway/billing:read a2a-gateway/billing:write"
        scope_string = claims.get('scope', '')
        scopes = []
        
        if scope_string:
            # Parse scopes and remove resource server prefix
            for scope in scope_string.split():
                # Remove "a2a-gateway/" prefix if present
                if '/' in scope:
                    scope = scope.split('/', 1)[1]
                scopes.append(scope)
        
        # Extract roles from cognito:groups (if present)
        roles = claims.get('cognito:groups', [])
        if isinstance(roles, str):
            roles = [roles]
        
        return {
            'userId': user_id,
            'scopes': scopes,
            'roles': roles,
            'username': claims.get('username', claims.get('cognito:username', ''))
        }


def create_validator_from_env() -> JWTValidator:
    """Create JWT validator from environment variables."""
    import os
    
    jwks_uri = os.environ['COGNITO_JWKS_URI']
    issuer = os.environ['COGNITO_ISSUER_URL']
    audience = os.environ.get('COGNITO_CLIENT_ID')  # Optional
    
    return JWTValidator(jwks_uri, issuer, audience)
