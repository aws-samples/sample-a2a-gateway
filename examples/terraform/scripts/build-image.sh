#!/bin/bash
# Builds a container image locally and pushes it to ECR.
# Usage: build-image.sh <region> <ecr_repo_url> <image_tag> <source_dir>

set -euo pipefail

REGION="$1"
ECR_REPO_URL="$2"
IMAGE_TAG="$3"
SOURCE_DIR="$4"
ACCOUNT_ID=$(echo "$ECR_REPO_URL" | cut -d'.' -f1)

echo "Logging in to Amazon ECR..."
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

echo "Building Docker image from ${SOURCE_DIR}..."
docker build --platform linux/arm64 -t "${ECR_REPO_URL}:${IMAGE_TAG}" "$SOURCE_DIR"

echo "Pushing image to ECR..."
docker push "${ECR_REPO_URL}:${IMAGE_TAG}"

echo "Verifying image in ECR..."
REPO_NAME=$(echo "$ECR_REPO_URL" | cut -d'/' -f2-)
aws ecr describe-images \
  --repository-name "$REPO_NAME" \
  --image-ids imageTag="$IMAGE_TAG" \
  --region "$REGION" > /dev/null 2>&1

echo "Image verified: ${ECR_REPO_URL}:${IMAGE_TAG}"
