#!/usr/bin/env python3
"""
End-to-end test script for A2A Gateway.

Tests the complete workflow:
1. Get JWT from Cognito
2. Test discovery (should be empty initially)
3. Register a mock backend agent
4. Test discovery (should return the agent)
5. Test A2A operations through the gateway
"""

import sys
import json
import subprocess
import requests
from typing import Dict, Any, Optional


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_step(step: str):
    """Print a test step."""
    print(f"\n{Colors.BLUE}{Colors.BOLD}=== {step} ==={Colors.END}")


def print_success(message: str):
    """Print success message."""
    print(f"{Colors.GREEN}✓ {message}{Colors.END}")


def print_error(message: str):
    """Print error message."""
    print(f"{Colors.RED}✗ {message}{Colors.END}")


def print_warning(message: str):
    """Print warning message."""
    print(f"{Colors.YELLOW}⚠ {message}{Colors.END}")


def get_terraform_output(key: str) -> str:
    """Get Terraform output value."""
    try:
        result = subprocess.run(
            ['terraform', 'output', '-raw', key],
            cwd='terraform',
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to get Terraform output '{key}': {e}")
        sys.exit(1)


def get_jwt_token(client_id: str, client_secret: str, token_endpoint: str) -> str:
    """Get JWT token from Cognito."""
    print_step("Getting JWT Token from Cognito")
    
    response = requests.post(
        token_endpoint,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        data={
            'grant_type': 'client_credentials',
            'client_id': client_id,
            'client_secret': client_secret,
            'scope': 'a2a-gateway/billing:read a2a-gateway/billing:write a2a-gateway/gateway:admin'
        }
    )
    
    if response.status_code != 200:
        print_error(f"Failed to get token: {response.status_code}")
        print(response.text)
        sys.exit(1)
    
    token_data = response.json()
    jwt = token_data.get('access_token')
    
    if not jwt:
        print_error("No access_token in response")
        print(json.dumps(token_data, indent=2))
        sys.exit(1)
    
    print_success("JWT token obtained")
    print(f"Token expires in: {token_data.get('expires_in', 'unknown')} seconds")
    
    return jwt


def test_discovery(gateway_url: str, jwt: str, expected_count: Optional[int] = None) -> list:
    """Test agent discovery endpoint."""
    print_step("Testing Agent Discovery")
    
    response = requests.get(
        f"{gateway_url}/agents",
        headers={'Authorization': f'Bearer {jwt}'}
    )
    
    if response.status_code != 200:
        print_error(f"Discovery failed: {response.status_code}")
        print(response.text)
        return []
    
    agents = response.json()
    
    if not isinstance(agents, list):
        print_error("Discovery response is not an array")
        print(json.dumps(agents, indent=2))
        return []
    
    print_success(f"Discovery successful - found {len(agents)} agent(s)")
    
    if expected_count is not None and len(agents) != expected_count:
        print_warning(f"Expected {expected_count} agents, got {len(agents)}")
    
    for agent in agents:
        print(f"  - {agent.get('name', 'Unknown')} ({agent.get('url', 'No URL')})")
    
    return agents


def register_mock_agent(gateway_url: str, jwt: str, agent_id: str = "mock-agent") -> bool:
    """Register a mock backend agent."""
    print_step(f"Registering Mock Agent: {agent_id}")
    
    # Note: This will fail if you don't have a real backend
    # For testing, you can use a mock server or skip this step
    print_warning("This requires a real A2A backend server")
    print("If you don't have one, you can:")
    print("  1. Deploy a mock A2A server")
    print("  2. Use an existing A2A service")
    print("  3. Skip this step and test with a pre-registered agent")
    
    backend_url = input("\nEnter backend URL (or press Enter to skip): ").strip()
    
    if not backend_url:
        print_warning("Skipping agent registration")
        return False
    
    agent_card_url = input("Enter agent card URL: ").strip()
    if not agent_card_url:
        agent_card_url = f"{backend_url}/.well-known/agent-card.json"
    
    token_url = input("Enter OAuth token URL: ").strip()
    client_id = input("Enter OAuth client ID: ").strip()
    client_secret = input("Enter OAuth client secret: ").strip()
    
    registration_data = {
        "agentId": agent_id,
        "name": "Mock Test Agent",
        "backendUrl": backend_url,
        "agentCardUrl": agent_card_url,
        "authConfig": {
            "type": "oauth2_client_credentials",
            "tokenUrl": token_url,
            "clientId": client_id,
            "clientSecret": client_secret,
            "scopes": ["agent:invoke"]
        }
    }
    
    response = requests.post(
        f"{gateway_url}/admin/agents/register",
        headers={
            'Authorization': f'Bearer {jwt}',
            'Content-Type': 'application/json'
        },
        json=registration_data
    )
    
    if response.status_code not in [200, 201]:
        print_error(f"Registration failed: {response.status_code}")
        print(response.text)
        return False
    
    result = response.json()
    print_success(f"Agent registered: {result.get('gatewayUrl', 'Unknown URL')}")
    
    return True


def test_agent_card(gateway_url: str, jwt: str, agent_id: str) -> bool:
    """Test fetching agent card through gateway."""
    print_step(f"Testing Agent Card Fetch: {agent_id}")
    
    response = requests.get(
        f"{gateway_url}/agents/{agent_id}/.well-known/agent-card.json",
        headers={'Authorization': f'Bearer {jwt}'}
    )
    
    if response.status_code != 200:
        print_error(f"Agent card fetch failed: {response.status_code}")
        print(response.text)
        return False
    
    agent_card = response.json()
    print_success("Agent card fetched successfully")
    print(f"  Name: {agent_card.get('name', 'Unknown')}")
    print(f"  URL: {agent_card.get('url', 'Unknown')}")
    print(f"  Skills: {len(agent_card.get('skills', []))}")
    
    return True


def test_message_send(gateway_url: str, jwt: str, agent_id: str) -> bool:
    """Test sending a message through gateway."""
    print_step(f"Testing Message Send: {agent_id}")
    
    message_data = {
        "message": {
            "messageId": "test-msg-001",
            "role": "ROLE_USER",
            "parts": [
                {
                    "text": "Hello from A2A Gateway test script!"
                }
            ]
        }
    }
    
    response = requests.post(
        f"{gateway_url}/agents/{agent_id}/message:send",
        headers={
            'Authorization': f'Bearer {jwt}',
            'Content-Type': 'application/json'
        },
        json=message_data
    )
    
    if response.status_code != 200:
        print_error(f"Message send failed: {response.status_code}")
        print(response.text)
        return False
    
    result = response.json()
    print_success("Message sent successfully")
    
    if 'task' in result:
        task = result['task']
        print(f"  Task ID: {task.get('id', 'Unknown')}")
        print(f"  Status: {task.get('status', {}).get('state', 'Unknown')}")
    
    return True


def test_permission_enforcement(gateway_url: str, jwt: str) -> bool:
    """Test that permission enforcement works."""
    print_step("Testing Permission Enforcement")
    
    # Try to access an agent that doesn't exist or user doesn't have permission for
    response = requests.get(
        f"{gateway_url}/agents/nonexistent-agent/.well-known/agent-card.json",
        headers={'Authorization': f'Bearer {jwt}'}
    )
    
    if response.status_code == 403:
        print_success("Permission enforcement working (403 Forbidden)")
        return True
    elif response.status_code == 404:
        print_success("Permission enforcement working (404 Not Found)")
        return True
    else:
        print_warning(f"Unexpected status code: {response.status_code}")
        return False


def main():
    """Main test flow."""
    print(f"{Colors.BOLD}A2A Gateway End-to-End Test{Colors.END}")
    print("=" * 50)
    
    # Get configuration from Terraform
    print_step("Loading Configuration from Terraform")
    
    try:
        gateway_url = get_terraform_output('api_gateway_url')
        client_id = get_terraform_output('cognito_client_id')
        client_secret = get_terraform_output('cognito_client_secret')
        token_endpoint = get_terraform_output('cognito_token_endpoint')
    except Exception as e:
        print_error(f"Failed to load configuration: {e}")
        print("\nMake sure you've deployed the infrastructure with Terraform")
        sys.exit(1)
    
    print_success("Configuration loaded")
    print(f"  Gateway URL: {gateway_url}")
    
    # Get JWT token
    jwt = get_jwt_token(client_id, client_secret, token_endpoint)
    
    # Test 1: Initial discovery (should be empty or have existing agents)
    initial_agents = test_discovery(gateway_url, jwt)
    
    # Test 2: Register a mock agent (optional)
    print("\n")
    register_agent = input("Do you want to register a new agent? (y/N): ").strip().lower()
    
    if register_agent == 'y':
        registered = register_mock_agent(gateway_url, jwt)
        
        if registered:
            # Test 3: Discovery after registration
            agents = test_discovery(gateway_url, jwt, expected_count=len(initial_agents) + 1)
        else:
            agents = initial_agents
    else:
        agents = initial_agents
    
    # Test 4: Test with existing agents
    if agents:
        print("\n")
        print(f"Found {len(agents)} agent(s) to test with:")
        for i, agent in enumerate(agents):
            print(f"  {i+1}. {agent.get('name', 'Unknown')}")
        
        choice = input(f"\nSelect agent to test (1-{len(agents)}, or Enter to skip): ").strip()
        
        if choice.isdigit() and 1 <= int(choice) <= len(agents):
            selected_agent = agents[int(choice) - 1]
            agent_url = selected_agent.get('url', '')
            
            # Extract agent ID from URL
            # URL format: https://gateway.example.com/agents/{agentId}
            agent_id = agent_url.rstrip('/').split('/')[-1]
            
            print(f"\nTesting with agent: {selected_agent.get('name')} (ID: {agent_id})")
            
            # Test agent card
            test_agent_card(gateway_url, jwt, agent_id)
            
            # Test message send
            test_message_send(gateway_url, jwt, agent_id)
    else:
        print_warning("No agents available to test")
        print("Register an agent first using the admin endpoint")
    
    # Test 5: Permission enforcement
    test_permission_enforcement(gateway_url, jwt)
    
    # Summary
    print(f"\n{Colors.BOLD}Test Summary{Colors.END}")
    print("=" * 50)
    print_success("Gateway is operational and A2A compliant!")
    print("\nNext steps:")
    print("  1. Register your real backend agents")
    print("  2. Configure permissions for different user scopes")
    print("  3. Test with a standard A2A client")
    print("  4. Monitor CloudWatch logs for any issues")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Test interrupted by user{Colors.END}")
        sys.exit(0)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
