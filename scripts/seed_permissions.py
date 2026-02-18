#!/usr/bin/env python3
"""Seed initial permissions in DynamoDB for testing."""

import boto3
import sys
from datetime import datetime, timezone

def get_timestamp():
    """Get current timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()

def seed_permissions(table_name, region='us-east-1'):
    """
    Seed initial permission mappings.
    
    Args:
        table_name: Name of the Permissions DynamoDB table
        region: AWS region
    """
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(table_name)
    
    # Define initial permissions
    permissions = [
        {
            'scope': 'billing:read',
            'allowedAgents': ['billing-agent'],
            'description': 'Read access to billing agent',
            'createdAt': get_timestamp(),
            'updatedAt': get_timestamp()
        },
        {
            'scope': 'billing:write',
            'allowedAgents': ['billing-agent'],
            'description': 'Write access to billing agent',
            'createdAt': get_timestamp(),
            'updatedAt': get_timestamp()
        },
        {
            'scope': 'search:read',
            'allowedAgents': ['search-agent'],
            'description': 'Read access to search agent',
            'createdAt': get_timestamp(),
            'updatedAt': get_timestamp()
        },
        {
            'scope': 'gateway:admin',
            'allowedAgents': ['billing-agent', 'search-agent', 'customer-support'],
            'description': 'Admin access to all agents',
            'createdAt': get_timestamp(),
            'updatedAt': get_timestamp()
        }
    ]
    
    # Insert permissions
    print(f"Seeding permissions into table: {table_name}")
    
    for permission in permissions:
        print(f"  - Creating permission for scope: {permission['scope']}")
        table.put_item(Item=permission)
    
    print(f"\nSuccessfully seeded {len(permissions)} permissions!")
    print("\nPermission mappings:")
    for permission in permissions:
        print(f"  {permission['scope']}: {', '.join(permission['allowedAgents'])}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python seed_permissions.py <permissions-table-name> [region]")
        print("\nExample:")
        print("  python seed_permissions.py a2a-gateway-poc-permissions us-east-1")
        sys.exit(1)
    
    table_name = sys.argv[1]
    region = sys.argv[2] if len(sys.argv) > 2 else 'us-east-1'
    
    try:
        seed_permissions(table_name, region)
    except Exception as e:
        print(f"Error seeding permissions: {e}", file=sys.stderr)
        sys.exit(1)
