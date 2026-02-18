"""DynamoDB client utilities for agent registry and permissions."""

import os
import boto3
from typing import Dict, Any, List, Optional, Set
from botocore.exceptions import ClientError


class DynamoDBClient:
    """Client for interacting with DynamoDB tables."""
    
    def __init__(self, agent_registry_table: str, permissions_table: str):
        """
        Initialize DynamoDB client.
        
        Args:
            agent_registry_table: Name of AgentRegistry table
            permissions_table: Name of Permissions table
        """
        self.dynamodb = boto3.resource('dynamodb')
        self.agent_registry_table = self.dynamodb.Table(agent_registry_table)
        self.permissions_table = self.dynamodb.Table(permissions_table)
    
    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get agent by ID from AgentRegistry.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            Agent item or None if not found
        """
        try:
            response = self.agent_registry_table.get_item(
                Key={'agentId': agent_id}
            )
            return response.get('Item')
        except ClientError as e:
            raise Exception(f"Failed to get agent {agent_id}: {e}")
    
    def get_all_agents(self) -> List[Dict[str, Any]]:
        """
        Get all agents from AgentRegistry.
        
        Returns:
            List of agent items
        """
        try:
            response = self.agent_registry_table.scan()
            items = response.get('Items', [])
            
            # Handle pagination
            while 'LastEvaluatedKey' in response:
                response = self.agent_registry_table.scan(
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                items.extend(response.get('Items', []))
            
            return items
        except ClientError as e:
            raise Exception(f"Failed to scan agents: {e}")
    
    def get_active_agents(self) -> List[Dict[str, Any]]:
        """
        Get all active agents from AgentRegistry.
        
        Returns:
            List of active agent items
        """
        all_agents = self.get_all_agents()
        return [agent for agent in all_agents if agent.get('status') == 'active']
    
    def get_allowed_agents_for_scopes(self, scopes: List[str]) -> Set[str]:
        """
        Get allowed agent IDs for given scopes.
        
        Args:
            scopes: List of user scopes
            
        Returns:
            Set of allowed agent IDs (union of all scopes)
        """
        allowed_agents: Set[str] = set()
        
        for scope in scopes:
            try:
                response = self.permissions_table.get_item(
                    Key={'scope': scope}
                )
                
                if 'Item' in response:
                    # Add allowed agents from this scope
                    scope_agents = response['Item'].get('allowedAgents', [])
                    allowed_agents.update(scope_agents)
                    
            except ClientError as e:
                # Log but continue - don't fail if one scope lookup fails
                print(f"Warning: Failed to get permissions for scope {scope}: {e}")
                continue
        
        return allowed_agents
    
    def put_agent(self, agent_item: Dict[str, Any]) -> None:
        """
        Put agent item into AgentRegistry.
        
        Args:
            agent_item: Agent item to store
        """
        try:
            self.agent_registry_table.put_item(Item=agent_item)
        except ClientError as e:
            raise Exception(f"Failed to put agent: {e}")
    
    def update_agent_status(self, agent_id: str, status: str) -> None:
        """
        Update agent status.
        
        Args:
            agent_id: Agent identifier
            status: New status ('active' or 'inactive')
        """
        try:
            self.agent_registry_table.update_item(
                Key={'agentId': agent_id},
                UpdateExpression='SET #status = :status, updatedAt = :updated',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': status,
                    ':updated': self._get_timestamp()
                }
            )
        except ClientError as e:
            raise Exception(f"Failed to update agent status: {e}")
    
    def update_agent_card(self, agent_id: str, agent_card: Dict[str, Any]) -> None:
        """
        Update cached agent card.
        
        Args:
            agent_id: Agent identifier
            agent_card: New agent card data
        """
        try:
            self.agent_registry_table.update_item(
                Key={'agentId': agent_id},
                UpdateExpression='SET cachedAgentCard = :card, lastSynced = :synced, updatedAt = :updated',
                ExpressionAttributeValues={
                    ':card': agent_card,
                    ':synced': self._get_timestamp(),
                    ':updated': self._get_timestamp()
                }
            )
        except ClientError as e:
            raise Exception(f"Failed to update agent card: {e}")
    
    def put_permission(self, scope: str, allowed_agents: List[str], description: str = "") -> None:
        """
        Put permission mapping.
        
        Args:
            scope: Scope identifier
            allowed_agents: List of allowed agent IDs
            description: Optional description
        """
        try:
            self.permissions_table.put_item(
                Item={
                    'scope': scope,
                    'allowedAgents': allowed_agents,
                    'description': description,
                    'createdAt': self._get_timestamp(),
                    'updatedAt': self._get_timestamp()
                }
            )
        except ClientError as e:
            raise Exception(f"Failed to put permission: {e}")
    
    @staticmethod
    def _get_timestamp() -> str:
        """Get current timestamp in ISO 8601 format."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


def create_client_from_env() -> DynamoDBClient:
    """Create DynamoDB client from environment variables."""
    agent_registry_table = os.environ['AGENT_REGISTRY_TABLE']
    permissions_table = os.environ['PERMISSIONS_TABLE']
    
    return DynamoDBClient(agent_registry_table, permissions_table)
