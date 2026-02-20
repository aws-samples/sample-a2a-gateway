"""Property-based tests for Lambda Authorizer."""

import pytest
from hypothesis import given, strategies as st, assume
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/lambdas'))

from authorizer.handler import extract_token, generate_policy
from shared.errors import AuthenticationError


# Feature: a2a-gateway, Property 1: JWT Signature Validation
# (Tested via integration with real Cognito - unit tests mock this)

# Feature: a2a-gateway, Property 2: JWT Claims Extraction
@given(
    user_id=st.text(min_size=1, max_size=100),
    scopes=st.lists(st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters=':_-'
    )), min_size=0, max_size=10),
    roles=st.lists(st.text(min_size=1, max_size=50), min_size=0, max_size=5),
    username=st.text(min_size=0, max_size=100),
    allowed_agents=st.frozensets(st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='-_'
    )), min_size=0, max_size=5)
)
@pytest.mark.property_test
def test_property_context_extraction(user_id, scopes, roles, username, allowed_agents):
    """
    Property 2: For any user context, generate_policy should correctly convert
    lists to comma-separated strings and preserve all values.
    """
    context = {
        'userId': user_id,
        'scopes': scopes,
        'roles': roles,
        'username': username
    }
    
    policy = generate_policy(
        principal_id=user_id,
        effect='Allow',
        method_arn='arn:aws:execute-api:us-east-1:123456789012:api/stage/GET/agents',
        allowed_agents=set(allowed_agents),
        context=context
    )
    
    # Verify principalId matches userId
    assert policy['principalId'] == user_id
    
    # Verify context conversion
    assert policy['context']['userId'] == user_id
    assert policy['context']['scopes'] == ','.join(scopes)
    assert policy['context']['roles'] == ','.join(roles)
    assert policy['context']['username'] == username


# Feature: a2a-gateway, Property 3: IAM Policy Generation with FGAC
@given(
    user_id=st.text(min_size=1, max_size=100),
    allowed_agents=st.frozensets(st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='-_'
    )), min_size=0, max_size=10)
)
@pytest.mark.property_test
def test_property_policy_generation_with_agents(user_id, allowed_agents):
    """
    Property 3: For any valid user_id and set of allowed agents, generate_policy 
    should return a valid IAM policy with agent-specific resource ARNs.
    """
    context = {
        'userId': user_id,
        'scopes': [],
        'roles': [],
        'username': ''
    }
    
    policy = generate_policy(
        principal_id=user_id,
        effect='Allow',
        method_arn='arn:aws:execute-api:us-east-1:123456789012:api/stage/GET/agents',
        allowed_agents=set(allowed_agents),
        context=context
    )
    
    # Verify policy structure
    assert 'principalId' in policy
    assert 'policyDocument' in policy
    assert 'context' in policy
    
    # Verify policy document structure
    assert policy['policyDocument']['Version'] == '2012-10-17'
    assert 'Statement' in policy['policyDocument']
    assert len(policy['policyDocument']['Statement']) > 0
    
    # Verify statement structure
    statement = policy['policyDocument']['Statement'][0]
    assert statement['Action'] == 'execute-api:Invoke'
    assert statement['Effect'] == 'Allow'
    assert 'Resource' in statement
    
    # Verify resources include registry endpoint
    resources = statement['Resource']
    assert any('/GET/agents' in r for r in resources)
    
    # Verify each allowed agent has a resource ARN
    for agent_id in allowed_agents:
        assert any(f'/agents/{agent_id}/' in r for r in resources)


# Token extraction property tests
@given(
    token=st.text(min_size=1, max_size=2000, alphabet=st.characters(
        whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='._-'
    ))
)
@pytest.mark.property_test
def test_property_token_extraction_valid_bearer(token):
    """
    Property: For any valid token string, extract_token should correctly
    extract it from a properly formatted Bearer header.
    """
    event = {
        'headers': {
            'Authorization': f'Bearer {token}'
        }
    }
    
    extracted = extract_token(event)
    assert extracted == token


@given(
    header_value=st.text(min_size=0, max_size=100)
)
@pytest.mark.property_test
def test_property_token_extraction_invalid_format(header_value):
    """
    Property: For any header value that doesn't match 'Bearer <token>' format,
    extract_token should raise AuthenticationError.
    """
    # Skip valid Bearer tokens
    assume(not header_value.startswith('Bearer ') or len(header_value.split()) != 2)
    
    event = {
        'headers': {
            'Authorization': header_value
        }
    }
    
    with pytest.raises(AuthenticationError):
        extract_token(event)


# Feature: a2a-gateway, Property 6: Multiple Scope Permission Union
@given(
    scopes=st.lists(
        st.text(min_size=1, max_size=50, alphabet=st.characters(
            whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters=':_-'
        )),
        min_size=1,
        max_size=20,
        unique=True
    )
)
@pytest.mark.property_test
def test_property_multiple_scopes_preserved(scopes):
    """
    Property 6: For any list of scopes, the policy context should preserve
    all scopes in comma-separated format, maintaining order.
    """
    context = {
        'userId': 'test-user',
        'scopes': scopes,
        'roles': [],
        'username': 'test'
    }
    
    policy = generate_policy(
        principal_id='test-user',
        effect='Allow',
        method_arn='arn:aws:execute-api:us-east-1:123456789012:api/stage/GET/agents',
        allowed_agents=set(),
        context=context
    )
    
    # Verify all scopes are preserved
    policy_scopes = policy['context']['scopes'].split(',') if policy['context']['scopes'] else []
    assert policy_scopes == scopes


# Feature: a2a-gateway, Property: Agent-specific resource ARN generation
@given(
    api_id=st.text(min_size=10, max_size=20, alphabet=st.characters(whitelist_categories=('Ll', 'Nd'))),
    stage=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd'))),
    allowed_agents=st.frozensets(st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='-_'
    )), min_size=1, max_size=5)
)
@pytest.mark.property_test
def test_property_agent_specific_resources(api_id, stage, allowed_agents):
    """
    Property: For any set of allowed agents, generate_policy should create
    resource ARNs that allow access only to those specific agents.
    """
    method_arn = f"arn:aws:execute-api:us-east-1:123456789012:{api_id}/{stage}/GET/agents"
    
    context = {
        'userId': 'test-user',
        'scopes': [],
        'roles': [],
        'username': 'test'
    }
    
    policy = generate_policy(
        principal_id='test-user',
        effect='Allow',
        method_arn=method_arn,
        allowed_agents=set(allowed_agents),
        context=context
    )
    
    resources = policy['policyDocument']['Statement'][0]['Resource']
    
    # Verify each allowed agent has exactly one resource ARN
    for agent_id in allowed_agents:
        agent_resources = [r for r in resources if f'/agents/{agent_id}/' in r]
        assert len(agent_resources) == 1
        # Verify the resource allows all methods (*)
        assert '/*/' in agent_resources[0] or '/*/agents/' in agent_resources[0]


# Feature: a2a-gateway, Property: No agents means registry-only access
@given(
    api_id=st.text(min_size=10, max_size=20, alphabet=st.characters(whitelist_categories=('Ll', 'Nd'))),
    stage=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd')))
)
@pytest.mark.property_test
def test_property_no_agents_registry_only(api_id, stage):
    """
    Property: When no agents are allowed, the policy should only permit
    access to the registry endpoint (GET /agents).
    """
    method_arn = f"arn:aws:execute-api:us-east-1:123456789012:{api_id}/{stage}/GET/agents"
    
    context = {
        'userId': 'test-user',
        'scopes': [],
        'roles': [],
        'username': 'test'
    }
    
    policy = generate_policy(
        principal_id='test-user',
        effect='Allow',
        method_arn=method_arn,
        allowed_agents=set(),
        context=context
    )
    
    resources = policy['policyDocument']['Statement'][0]['Resource']
    
    # Should only have one resource (registry endpoint)
    assert len(resources) == 1
    assert resources[0].endswith('/GET/agents')
