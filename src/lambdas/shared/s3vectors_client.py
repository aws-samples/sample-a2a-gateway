"""S3 Vectors client for storing and querying vector embeddings."""

import os
import boto3
from typing import Dict, Any, List, Optional


class S3VectorsClient:
    """Client for interacting with S3 Vectors."""
    
    def __init__(self, vector_bucket_name: str, index_name: str, region_name: str = None):
        """
        Initialize S3 Vectors client.
        
        Args:
            vector_bucket_name: Name of the S3 vector bucket
            index_name: Name of the vector index
            region_name: AWS region (uses default if not specified)
        """
        self.s3vectors = boto3.client("s3vectors", region_name=region_name)
        self.vector_bucket_name = vector_bucket_name
        self.index_name = index_name
    
    def put_vector(
        self,
        key: str,
        embedding: List[float],
        metadata: Dict[str, Any]
    ) -> None:
        """
        Store a single vector.
        
        Args:
            key: Unique identifier for the vector
            embedding: Vector embedding (list of floats)
            metadata: Metadata to attach to the vector
        """
        self.s3vectors.put_vectors(
            vectorBucketName=self.vector_bucket_name,
            indexName=self.index_name,
            vectors=[{
                "key": key,
                "data": {"float32": embedding},
                "metadata": metadata
            }]
        )
    
    def delete_vector(self, key: str) -> None:
        """
        Delete a vector by key.
        
        Args:
            key: Vector key to delete
        """
        self.s3vectors.delete_vectors(
            vectorBucketName=self.vector_bucket_name,
            indexName=self.index_name,
            keys=[key]
        )
    
    def query(
        self,
        query_embedding: List[float],
        top_k: int = 50,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Query for similar vectors.
        
        Args:
            query_embedding: Query vector
            top_k: Number of results to return
            filter_metadata: Optional metadata filter
            
        Returns:
            List of matching vectors with metadata and distance
        """
        params = {
            "vectorBucketName": self.vector_bucket_name,
            "indexName": self.index_name,
            "queryVector": {"float32": query_embedding},
            "topK": top_k,
            "returnDistance": True,
            "returnMetadata": True
        }
        
        if filter_metadata:
            params["filter"] = filter_metadata
        
        response = self.s3vectors.query_vectors(**params)
        return response.get("vectors", [])


def create_client_from_env() -> S3VectorsClient:
    """Create S3 Vectors client from environment variables."""
    vector_bucket_name = os.environ["VECTOR_BUCKET_NAME"]
    vector_index_name = os.environ["VECTOR_INDEX_NAME"]
    
    return S3VectorsClient(vector_bucket_name, vector_index_name)
