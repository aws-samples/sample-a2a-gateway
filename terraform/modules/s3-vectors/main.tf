# S3 Vectors for semantic agent search

# Vector Bucket
resource "aws_s3vectors_vector_bucket" "agents" {
  vector_bucket_name = "${var.project_name}-${var.environment}-agents"

  # Enable force_destroy to allow deletion even with vectors present
  force_destroy = true

  tags = {
    Name        = "${var.project_name}-${var.environment}-agents"
    Environment = var.environment
  }
}

# Vector Index for agent embeddings
resource "aws_s3vectors_index" "agents" {
  index_name         = "agents"
  vector_bucket_name = aws_s3vectors_vector_bucket.agents.vector_bucket_name
  
  # Titan Text Embeddings V2 uses 1024 dimensions
  data_type       = "float32"
  dimension       = 1024
  distance_metric = "cosine"

  # Store source text as non-filterable (we don't need to filter on it)
  metadata_configuration {
    non_filterable_metadata_keys = ["sourceText"]
  }

  tags = {
    Name        = "${var.project_name}-${var.environment}-agents-index"
    Environment = var.environment
  }
}
