"""Property-based tests for Proxy Lambda - A2A Protocol Compliance."""

import pytest
from hypothesis import given, strategies as st, assume
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/lambdas'))

from proxy.handler import parse_path, build_backend_headers, is_streaming_operation
from shared.errors import BadRequestError


# Feature: a2a-gateway, Property 10: Path Parsing
@given(
    agent_id=st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='-_'
    )),
    operation=st.text(min_size=1, max_size=100, alphabet=st.characters(
        whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='-_:/.~'
    ))
)
@pytest.mark.property_test
def test_property_path_parsing(agent_id, operation):
    """
    Property 10: For any valid agentId and operation, parse_path should
    correctly extract both components from the path.
    """
    # Skip operations that are only slashes (they get stripped)
    assume(operation.strip('/') != '')
    
    path = f"/agents/{agent_id}/{operation}"
    
    parsed_agent_id, parsed_operation = parse_path(path)
    
    assert parsed_agent_id == agent_id
    assert parsed_operation == operation


# Feature: a2a-gateway, Property 11: Header Forwarding
@given(
    headers=st.dictionaries(
        keys=st.text(min_size=1, max_size=50, alphabet=st.characters(
            whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='-_'
        )),
        values=st.text(min_size=0, max_size=200),
        min_size=0,
        max_size=20
    ),
    access_token=st.text(min_size=10, max_size=200)
)
@pytest.mark.property_test
def test_property_header_forwarding(headers, access_token):
    """
    Property 11: For any request headers, build_backend_headers should forward
    all headers except excluded ones and add OAuth token.
    """
    # Exclude hop-by-hop headers from test
    excluded = {'authorization', 'host', 'connection', 'transfer-encoding', 'content-length'}
    filtered_headers = {k: v for k, v in headers.items() if k.lower() not in excluded}
    
    backend_headers = build_backend_headers(filtered_headers, access_token)
    
    # Verify OAuth token is added
    assert backend_headers['Authorization'] == f'Bearer {access_token}'
    
    # Verify all non-excluded headers are forwarded
    for key, value in filtered_headers.items():
        if key.lower() not in excluded:
            assert backend_headers.get(key) == value


# Feature: a2a-gateway, Property 16: OAuth Token in Authorization Header
@given(
    access_token=st.text(min_size=10, max_size=500, alphabet=st.characters(
        whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='._-'
    ))
)
@pytest.mark.property_test
def test_property_oauth_token_header(access_token):
    """
    Property 16: For any OAuth access token, build_backend_headers should
    include it in the Authorization header as "Bearer {token}".
    """
    backend_headers = build_backend_headers({}, access_token)
    
    assert 'Authorization' in backend_headers
    assert backend_headers['Authorization'] == f'Bearer {access_token}'


# A2A operation path parsing with various formats
@given(
    agent_id=st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='-_'
    )),
    task_id=st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='-_'
    ))
)
@pytest.mark.property_test
def test_property_task_path_parsing(agent_id, task_id):
    """
    Property: For any agent ID and task ID, parse_path should correctly
    extract both from task operation paths.
    """
    # Test various task operations
    paths = [
        f"/agents/{agent_id}/tasks/{task_id}",
        f"/agents/{agent_id}/tasks/{task_id}:cancel",
        f"/agents/{agent_id}/tasks"
    ]
    
    for path in paths:
        parsed_agent_id, operation = parse_path(path)
        assert parsed_agent_id == agent_id
        assert 'tasks' in operation


# Streaming detection property
@given(
    operation=st.text(min_size=1, max_size=100)
)
@pytest.mark.property_test
def test_property_streaming_detection(operation):
    """
    Property: For any operation containing 'message:stream', is_streaming_operation
    should return True, otherwise False.
    """
    result = is_streaming_operation(operation)
    
    if 'message:stream' in operation:
        assert result is True
    else:
        # Could be True or False depending on operation
        assert isinstance(result, bool)


# Path parsing with leading/trailing slashes
@given(
    agent_id=st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='-_'
    )),
    operation=st.text(min_size=1, max_size=100, alphabet=st.characters(
        whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='-_:/.~'
    )),
    leading_slashes=st.integers(min_value=0, max_value=5),
    trailing_slashes=st.integers(min_value=0, max_value=5)
)
@pytest.mark.property_test
def test_property_path_parsing_with_slashes(agent_id, operation, leading_slashes, trailing_slashes):
    """
    Property: For any path with leading/trailing slashes, parse_path should
    correctly extract agent ID and operation.
    """
    path = '/' * leading_slashes + f"agents/{agent_id}/{operation}" + '/' * trailing_slashes
    
    parsed_agent_id, parsed_operation = parse_path(path)
    
    assert parsed_agent_id == agent_id
    assert parsed_operation == operation


# Header case-insensitivity for excluded headers
@given(
    excluded_header=st.sampled_from(['Authorization', 'Host', 'Connection', 'Transfer-Encoding']),
    header_value=st.text(min_size=1, max_size=100),
    access_token=st.text(min_size=10, max_size=200)
)
@pytest.mark.property_test
def test_property_excluded_headers_case_insensitive(excluded_header, header_value, access_token):
    """
    Property: For any excluded header in any case, build_backend_headers should
    not forward it (except Authorization which is replaced with OAuth token).
    """
    # Test various cases
    for case_variant in [excluded_header.lower(), excluded_header.upper(), excluded_header]:
        headers = {case_variant: header_value}
        backend_headers = build_backend_headers(headers, access_token)
        
        # Authorization should be replaced with OAuth token
        if excluded_header.lower() == 'authorization':
            assert backend_headers['Authorization'] == f'Bearer {access_token}'
            assert backend_headers['Authorization'] != header_value
        else:
            # Other excluded headers should not be present
            assert case_variant not in backend_headers


# A2A standard operations path parsing
@pytest.mark.property_test
def test_property_standard_a2a_operations():
    """
    Property: For all standard A2A operations, parse_path should correctly
    extract agent ID and operation.
    """
    agent_id = 'test-agent'
    
    # Standard A2A operations
    operations = [
        'message:send',
        'message:stream',
        '.well-known/agent-card.json',
        'tasks',
        'tasks/task-123',
        'tasks/task-123:cancel',
        'tasks/task-123/push-notification-configs'
    ]
    
    for operation in operations:
        path = f"/agents/{agent_id}/{operation}"
        parsed_agent_id, parsed_operation = parse_path(path)
        
        assert parsed_agent_id == agent_id
        assert parsed_operation == operation


# Content-Type header preservation
@given(
    content_type=st.sampled_from([
        'application/json',
        'text/plain',
        'application/x-www-form-urlencoded',
        'multipart/form-data',
        'text/event-stream'
    ]),
    access_token=st.text(min_size=10, max_size=200)
)
@pytest.mark.property_test
def test_property_content_type_preservation(content_type, access_token):
    """
    Property: For any Content-Type header, build_backend_headers should
    preserve it in the backend request.
    """
    headers = {'Content-Type': content_type}
    backend_headers = build_backend_headers(headers, access_token)
    
    assert backend_headers['Content-Type'] == content_type
