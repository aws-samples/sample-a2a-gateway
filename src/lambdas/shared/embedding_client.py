"""Embedding client for generating vector embeddings via Amazon Bedrock."""

import json
import boto3
from typing import Dict, Any, List


class EmbeddingClient:
    """Client for generating embeddings using Amazon Bedrock Titan."""
    
    DEFAULT_MODEL_ID = "amazon.titan-embed-text-v2:0"
    EMBEDDING_DIMENSION = 1024
    
    def __init__(self, region_name: str = None):
        """
        Initialize embedding client.
        
        Args:
            region_name: AWS region (uses default if not specified)
        """
        self.bedrock = boto3.client("bedrock-runtime", region_name=region_name)
        self.model_id = self.DEFAULT_MODEL_ID
    
    def get_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for text.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats (1024 dimensions for Titan v2)
        """
        response = self.bedrock.invoke_model(
            modelId=self.model_id,
            body=json.dumps({"inputText": text})
        )
        
        response_body = json.loads(response["body"].read())
        return response_body["embedding"]
    
    def format_agent_for_embedding(self, agent_card: Dict[str, Any]) -> str:
        """
        Format agent card data into text suitable for embedding.
        
        Args:
            agent_card: Agent card JSON
            
        Returns:
            Formatted text string
        """
        parts = []
        
        # Name and description
        if agent_card.get("name"):
            parts.append(agent_card["name"])
        
        if agent_card.get("description"):
            parts.append(agent_card["description"])
        
        # Skills
        skills = agent_card.get("skills", [])
        if skills:
            skill_texts = []
            for skill in skills:
                skill_name = skill.get("name", skill.get("id", ""))
                skill_desc = skill.get("description", "")
                if skill_name:
                    skill_texts.append(f"{skill_name}: {skill_desc}" if skill_desc else skill_name)
            if skill_texts:
                parts.append("Skills: " + ", ".join(skill_texts))
        
        # Capabilities
        capabilities = agent_card.get("capabilities", {})
        if capabilities:
            cap_list = [k for k, v in capabilities.items() if v]
            if cap_list:
                parts.append("Capabilities: " + ", ".join(cap_list))
        
        return ". ".join(parts)
