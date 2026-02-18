#!/bin/bash
set -e

# Build Lambda deployment package with dependencies
# Usage: ./scripts/build_lambda_package.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/terraform/modules/lambda-functions/builds"
PACKAGE_DIR="$BUILD_DIR/package"

echo "Building Lambda deployment package..."

# Clean and create build directory
rm -rf "$BUILD_DIR"
mkdir -p "$PACKAGE_DIR"

# Install dependencies
echo "Installing Python dependencies..."
pip install -r "$PROJECT_ROOT/src/requirements.txt" -t "$PACKAGE_DIR" --quiet

# Copy Lambda source code
echo "Copying Lambda source code..."
cp -r "$PROJECT_ROOT/src/lambdas/"* "$PACKAGE_DIR/"

# Create zip file
echo "Creating deployment package..."
cd "$PACKAGE_DIR"
zip -r "$BUILD_DIR/lambda.zip" . -q

echo "✓ Lambda package created: $BUILD_DIR/lambda.zip"
echo "  Size: $(du -h "$BUILD_DIR/lambda.zip" | cut -f1)"
