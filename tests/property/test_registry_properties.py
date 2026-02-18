"""Property-based tests for Registry Lambda."""

import pytest
from hypothesis import given, strategies as st, assume
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/lambdas'))

from shared.url_rewriter import rewrite_agent_card_urls, extract_agent_id_from_url
from registry.handler import extract_user_context


# Feature: a2a-gateway, Property 4: Agent Filtering by Permissions
# (Tested via integration - requires DynamoDB mock)

# Feature: a2a-gateway, Property 8: URL Rewriting at Read Time
@given(
    agent_id=st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='-_'
    )),
    gateway_domain=st.text(min_size=5, max_size=100, alphabet=st.characters(
        whitelist_categories=('Ll', 'Nd'), whitelist_characters='.-'
    )),
    backend_url=st.text(min_size=10, max_size=100)
)
@pytest.mark.property_test
def test_property_url_rewriting(agent_id, gateway_domain, backend_url):
    """
    Property 8: For any Agent Card with backend URLs, rewrite_agent_card_urls
    should transform all URLs to gateway URLs with the correct agent path.
    """
    # Assume valid domain format
    assume('.' in gateway_domain)
    
    agent_card = {
        'name': 'Test Agent',
        'url': backend_url,
        'supportedInterfaces': [
            {
                'url': backend_url,
                'protocolBinding': 'HTTP+JSON',
                'protocolVersion': '0.3'
            }
        ],
        'skills': []
    }
    
    rewritten = rewrite_agent_card_urls(agent_card, agent_id, gateway_domain)
    
    expected_url = f"https://{gateway_domain}/agents/{agent_id}"
    
    # Verify main URL is rewritten
    assert rewritten['url'] == expected_url
    
    # Verify all interface URLs are rewritten
    for interface in rewritten['supportedInterfaces']:
        assert interface['url'] == expected_url
    
    # Verify other fields are preserved
    assert rewritten['name'] == agent_card['name']


# Feature: a2a-gateway, Property 9: Original URL Preservation in Cache
@given(
    agent_id=st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='-_'
    )),
    backend_url=st.text(min_size=10, max_size=100)
)
@pytest.mark.property_test
def test_property_original_url_preservation(agent_id, backend_url):
    """
    Property 9: For any Agent Card, rewrite_agent_card_urls should not modify
    the original card - it should return a new copy.
    """
    original_card = {
        'name': 'Test Agent',
        'url': backend_url,
        'supportedInterfaces': [
            {
                'url': backend_url,
                'protocolBinding': 'HTTP+JSON',
                'protocolVersion': '0.3'
            }
        ]
    }
    
    original_url = original_card['url']
    original_interface_url = original_card['supportedInterfaces'][0]['url']
    
    # Rewrite URLs
    rewritten = rewrite_agent_card_urls(original_card, agent_id, 'gateway.example.com')
    
    # Verify original is unchanged
    assert original_card['url'] == original_url
    assert original_card['supportedInterfaces'][0]['url'] == original_interface_url
    
    # Verify rewritten is different
    assert rewritten['url'] != original_url


# Feature: a2a-gateway, Property 6: Multiple Scope Permission Union
@given(
    scopes=st.lists(
        st.text(min_size=1, max_size=50, alphabet=st.characters(
            whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters=':_-'
        )),
        min_size=0,
        max_size=20,
        unique=True
    )
)
@pytest.mark.property_test
def test_property_scope_parsing_from_csv(scopes):
    """
    Property 6: For any list of scopes passed as CSV from authorizer,
    extract_user_context should correctly parse them back to a list.
    """
    # Create event with CSV scopes
    scopes_csv = ','.join(scopes)
    
    event = {
        'requestContext': {
            'authorizer': {
                'userId': 'test-user',
                'scopes': scopes_csv,
                'roles': '',
                'username': 'test'
            }
        }
    }
    
    context = extract_user_context(event)
    
    # Verify scopes are correctly parsed
    assert context['scopes'] == scopes


# URL extraction property
@given(
    agent_id=st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='-_'
    )),
    gateway_domain=st.text(min_size=5, max_size=100, alphabet=st.characters(
        whitelist_categories=('Ll', 'Nd'), whitelist_characters='.-'
    ))
)
@pytest.mark.property_test
def test_property_agent_id_extraction_from_url(agent_id, gateway_domain):
    """
    Property: For any gateway URL, extract_agent_id_from_url should correctly
    extract the agent ID.
    """
    assume('.' in gateway_domain)
    
    gateway_url = f"https://{gateway_domain}/agents/{agent_id}"
    
    extracted_id = extract_agent_id_from_url(gateway_url)
    
    assert extracted_id == agent_id


# Multiple interfaces URL rewriting
@given(
    agent_id=st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='-_'
    )),
    num_interfaces=st.integers(min_value=1, max_value=10),
    backend_urls=st.lists(
        st.text(min_size=10, max_size=100),
        min_size=1,
        max_size=10
    )
)
@pytest.mark.property_test
def test_property_multiple_interfaces_rewriting(agent_id, num_interfaces, backend_urls):
    """
    Property: For any Agent Card with multiple interfaces, all interface URLs
    should be rewritten to the same gateway URL.
    """
    # Create agent card with multiple interfaces
    interfaces = [
        {
            'url': backend_urls[i % len(backend_urls)],
            'protocolBinding': 'HTTP+JSON',
            'protocolVersion': '0.3'
        }
        for i in range(num_interfaces)
    ]
    
    agent_card = {
        'name': 'Test Agent',
        'url': backend_urls[0],
        'supportedInterfaces': interfaces
    }
    
    rewritten = rewrite_agent_card_urls(agent_card, agent_id, 'gateway.example.com')
    
    expected_url = f"https://gateway.example.com/agents/{agent_id}"
    
    # Verify all interfaces have the same gateway URL
    for interface in rewritten['supportedInterfaces']:
        assert interface['url'] == expected_url


# Context extraction with various formats
@given(
    user_id=st.text(min_size=1, max_size=100),
    scopes=st.lists(st.text(min_size=1, max_size=50), min_size=0, max_size=20),
    roles=st.lists(st.text(min_size=1, max_size=50), min_size=0, max_size=10),
    username=st.text(min_size=0, max_size=100)
)
@pytest.mark.property_test
def test_property_context_extraction_roundtrip(user_id, scopes, roles, username):
    """
    Property: For any user context passed through authorizer as CSV strings,
    extract_user_context should correctly parse all values.
    """
    event = {
        'requestContext': {
            'authorizer': {
                'userId': user_id,
                'scopes': ','.join(scopes),
                'roles': ','.join(roles),
                'username': username
            }
        }
    }
    
    context = extract_user_context(event)
    
    assert context['userId'] == user_id
    assert context['scopes'] == scopes
    assert context['roles'] == roles
    assert context['username'] == username
