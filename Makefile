# Makefile for RAG MCP Server (Lambda + OpenSearch Serverless)

# --- Variables ---
# Default AWS region (override with environment variable or command line: make deploy AWS_REGION=...)
AWS_REGION ?= eu-west-3
# Default AWS profile (override with environment variable or command line: make deploy AWS_PROFILE=...)
AWS_PROFILE ?= tknff
# Get AWS Account ID automatically (requires AWS CLI configured and profile to work)
AWS_ACCOUNT_ID := $(shell aws sts get-caller-identity --query Account --output text --profile $(AWS_PROFILE))

# CDK App Configuration
CDK_APP = "python infrastructure/app.py"
STACK_NAME = RagMcpStack # Must match the stack name in infrastructure/app.py

# Build Configuration
PACKAGE_DIR = build/lambda_package

# Python Configuration (Assumes python3 and pip are available)
PYTHON = python3
PIP = pip

# --- Targets ---

.PHONY: help
help:
	@echo "Makefile Commands:"
	@echo "  make deps        Install Python dependencies for the project and CDK"
	@echo "  make build       Build the Lambda deployment package in $(PACKAGE_DIR)/"
	@echo "  make clean       Remove build artifacts and virtual environment"
	@echo "  make bootstrap   Run CDK bootstrap for the target AWS account/region (needed once)"
	@echo "  make synth       Synthesize the CloudFormation template"
	@echo "  make deploy      Build and deploy the CDK stack to AWS"
	@echo "  make destroy     Destroy the CDK stack from AWS"
	@echo "  make logs        Tail the logs of the deployed Lambda function"
	@echo "  make invoke      (Optional) Invoke the Lambda function locally or via AWS CLI"
	@echo "  make test        Run tests for the project"

# Dependency Management
.PHONY: deps
deps:
	@echo "---> Installing Python dependencies..."
	$(PIP) install -e ".[dev]" # Install project and dev dependencies in editable mode
	# Ensure CDK is installed globally or handle venv activation if needed

# Build Lambda Package
.PHONY: build
build:
	@echo "---> Building Lambda deployment package in $(PACKAGE_DIR) using Docker..."
	rm -rf build $(PACKAGE_DIR)
	mkdir -p $(PACKAGE_DIR)
	
	@echo "---> Installing dependencies inside python:3.9-slim container..."
	# Use Docker to install dependencies in a Lambda-like environment
	# Mount the current directory to /app in the container
	# Run pip install targeting the mounted /app/$(PACKAGE_DIR)
	# Explicitly use linux/amd64 platform and disable pip cache
	docker run --rm \
		--platform linux/amd64 \
		-v "$(shell pwd)":/app \
		-w /app \
		python:3.9-slim \
		pip install --no-cache-dir . --target /app/$(PACKAGE_DIR) # Added --no-cache-dir

	# Check if installation was successful (basic check: check if a key package exists)
	@if [ ! -d "$(PACKAGE_DIR)/pydantic" ]; then \
		echo "ERROR: Docker build failed to install dependencies into $(PACKAGE_DIR)."; \
		exit 1; \
	fi

	# Copy the application source code into the package directory
	@echo "---> Copying src/ directory..."
	cp -R src $(PACKAGE_DIR)/
	@echo "---> Build complete."

# Clean Build Artifacts
.PHONY: clean
clean:
	@echo "---> Cleaning build artifacts..."
	rm -rf build $(PACKAGE_DIR) .cdk.staging cdk.out
	@echo "---> Done."

# CDK Operations
.PHONY: bootstrap
bootstrap:
	@echo "---> Bootstrapping CDK environment aws://$(AWS_ACCOUNT_ID)/$(AWS_REGION)..."
	cd infrastructure && cdk bootstrap aws://$(AWS_ACCOUNT_ID)/$(AWS_REGION) --profile $(AWS_PROFILE)

.PHONY: synth
synth:
	@echo "---> Synthesizing CloudFormation template..."
	cd infrastructure && cdk synth $(STACK_NAME) --profile $(AWS_PROFILE) --require-approval never

.PHONY: deploy
deploy: build
	@echo "---> Deploying stack $(STACK_NAME) to $(AWS_REGION) using profile [$(AWS_PROFILE)]..."
	cd infrastructure && cdk deploy $(STACK_NAME) --profile $(AWS_PROFILE) --require-approval never
	@echo "---> Deployment potentially complete. Check AWS console for status."

.PHONY: destroy
destroy:
	@echo "---> Destroying stack $(STACK_NAME) from $(AWS_REGION) using profile [$(AWS_PROFILE)]..."
	cd infrastructure && cdk destroy $(STACK_NAME) --profile $(AWS_PROFILE) --force
	@echo "---> Stack destruction initiated."

# Utility Targets
.PHONY: logs
logs:
	@echo "---> Tailing logs for Lambda function..."
	# Use the known function name directly in the aws command
	# FUNCTION_NAME=RagMcpStack-AppLambda46D23914-YOOlSWvdishr # Hardcoded name from deploy output
	# export FUNCTION_NAME # Export the variable
	@echo "Tailing logs for RagMcpStack-AppLambda46D23914-YOOlSWvdishr... Press Ctrl+C to stop."
	# Use the AWS_PROFILE variable and the hardcoded function name
	aws logs tail /aws/lambda/RagMcpStack-AppLambda46D23914-YOOlSWvdishr --follow --profile $(AWS_PROFILE) --region $(AWS_REGION)

.PHONY: invoke
invoke:
	@echo "---> Example Invocation (Requires deployed stack and valid API Key)"
	@echo "# Set environment variables (replace with your actual key):"
	@echo "export API_KEY='YOUR_APP_API_KEY' # Replace with value from AI/MCP_SERVERS/RAG_SERVER_API_KEY secret"
	@echo "export API_URL=$$(aws cloudformation describe-stacks --stack-name $(STACK_NAME) --query \"Stacks[0].Outputs[?OutputKey=='ApiGatewayEndpoint'].OutputValue\" --output text --profile $(AWS_PROFILE) --region $(AWS_REGION))"
	@echo ""
	@echo "# Test Discovery (GET /mcp):"
	@echo "curl -H \"X-API-Key: $${API_KEY}\" $${API_URL}mcp"
	@echo ""
	@echo "# Add Document (POST /mcp using example_payloads/payload_add.json):"
	@echo "curl -X POST -H \"Content-Type: application/json\" -H \"X-API-Key: $${API_KEY}\" -d @example_payloads/payload_add.json $${API_URL}mcp"
	@echo ""
	@echo "# List Documents (POST /mcp using example_payloads/payload_list.json):"
	@echo "curl -X POST -H \"Content-Type: application/json\" -H \"X-API-Key: $${API_KEY}\" -d @example_payloads/payload_list.json $${API_URL}mcp"
	@echo ""
	@echo "# Query Documents (POST /mcp using example_payloads/payload_query.json):"
	@echo "curl -X POST -H \"Content-Type: application/json\" -H \"X-API-Key: $${API_KEY}\" -d @example_payloads/payload_query.json $${API_URL}mcp"

.PHONY: test
test: build
	@echo "---> Running tests..."
	# Add infrastructure dir to PYTHONPATH for CDK tests - NO LONGER NEEDED
	# PYTHONPATH=infrastructure:$$PYTHONPATH pytest
	pytest # Run pytest directly

.PHONY: bootstrap
bootstrap:
	@echo "---> Bootstrapping CDK environment aws://$(AWS_ACCOUNT_ID)/$(AWS_REGION)..."
	cd infrastructure && cdk bootstrap aws://$(AWS_ACCOUNT_ID)/$(AWS_REGION) --profile $(AWS_PROFILE) 