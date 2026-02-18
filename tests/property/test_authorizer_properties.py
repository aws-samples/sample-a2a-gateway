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
    username=st.text(min_size=0, max_size=100)
)
@pytest.mark.property_test
def test_property_context_extraction(user_id, scopes, roles, username):
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
        resource='arn:aws:execute-api:us-east-1:123456789012:api/stage/GET/path',
        context=context
    )
    
    # Verify principalId matches userId
    assert policy['principalId'] == user_id
    
    # Verify context conversion
    assert policy['context']['userId'] == user_id
    assert policy['context']['scopes'] == ','.join(scopes)
    assert policy['context']['roles'] == ','.join(roles)
    assert policy['context']['username'] == username


# Feature: a2a-gateway, Property 3: IAM Policy Generation
@given(
    user_id=st.text(min_size=1, max_size=100),
    effect=st.sampled_from(['Allow', 'Deny']),
    resource=st.text(min_size=10, max_size=200)
)
@pytest.mark.property_test
def test_property_policy_generation(user_id, effect, resource):
    """
    Property 3: For any valid user_id and effect, generate_policy should return
    a valid IAM policy with the correct structure.
    """
    context = {
        'userId': user_id,
        'scopes': [],
        'roles': [],
        'username': ''
    }
    
    policy = generate_policy(
        principal_id=user_id,
        effect=effect,
        resource=resource,
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
    assert statement['Effect'] == effect
    assert 'Resource' in statement


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
        resource='arn:aws:execute-api:us-east-1:123456789012:api/stage/GET/path',
        context=context
    )
    
    # Verify all scopes are preserved
    policy_scopes = policy['context']['scopes'].split(',') if policy['context']['scopes'] else []
    assert policy_scopes == scopes


# Resource wildcard conversion property
@given(
    api_id=st.text(min_size=10, max_size=20, alphabet=st.characters(whitelist_categories=('Ll', 'Nd'))),
    stage=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd'))),
    method=st.sampled_from(['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS']),
    path=st.text(min_size=1, max_size=100, alphabet=st.characters(
        whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='/-_'
    ))
)
@pytest.mark.property_test
def test_property_resource_wildcard_conversion(api_id, stage, method, path):
    """
    Property: For any API Gateway method ARN, generate_policy should convert
    it to a wildcard resource pattern.
    """
    resource = f"arn:aws:execute-api:us-east-1:123456789012:{api_id}/{stage}/{method}/{path}"
    
    context = {
        'userId': 'test-user',
        'scopes': [],
        'roles': [],
        'username': 'test'
    }
    
    policy = generate_policy(
        principal_id='test-user',
        effect='Allow',
        resource=resource,
        context=context
    )
    
    # Verify resource is converted to wildcard
    policy_resource = policy['policyDocument']['Statement'][0]['Resource']
    assert policy_resource.endswith('/*/*')
    assert f"{api_id}/{stage}" in policy_resource
