#!/bin/bash
# Run tests for A2A Gateway

set -e

echo "=== Running A2A Gateway Tests ==="
echo ""

# Change to project root
cd "$(dirname "$0")/.."

# Install dependencies if needed
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3.12 -m venv venv
    source venv/bin/activate
    pip install -r src/requirements.txt
else
    source venv/bin/activate
fi

echo "=== Running Unit Tests ==="
pytest tests/unit/ -v -m "not property_test"

echo ""
echo "=== Running Property-Based Tests ==="
pytest tests/property/ -v -m property_test

echo ""
echo "=== Running All Tests with Coverage ==="
pytest tests/ --cov=src/lambdas --cov-report=term-missing --cov-report=html

echo ""
echo "=== Test Summary ==="
echo "Coverage report generated in htmlcov/index.html"
