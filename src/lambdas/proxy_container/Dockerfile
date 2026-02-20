# Lambda Web Adapter with FastAPI for A2A Proxy
# Supports both streaming and buffered responses
#
# Build context should be src/lambdas/ directory:
#   finch build -t a2a-proxy -f proxy_container/Dockerfile .

FROM public.ecr.aws/docker/library/python:3.12-slim

# Install Lambda Web Adapter
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.8.4 /lambda-adapter /opt/extensions/lambda-adapter

# Set working directory
WORKDIR /var/task

# Copy shared modules first (for caching)
COPY shared/ /var/task/shared/

# Copy application requirements and install
COPY proxy_container/app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY proxy_container/app/ /var/task/app/

# Set environment variables for Lambda Web Adapter
ENV AWS_LAMBDA_EXEC_WRAPPER=/opt/extensions/lambda-adapter
ENV AWS_LWA_INVOKE_MODE=response_stream
ENV AWS_LWA_READINESS_CHECK_PATH=/health
ENV AWS_LWA_PORT=8080
ENV PORT=8080

# Run uvicorn
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
