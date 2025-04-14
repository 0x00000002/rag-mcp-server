# Makefile for RAG MCP Server (Lambda + OpenSearch Serverless)

# --- Variables ---
# Default AWS region (override with environment variable or command line: make deploy AWS_REGION=...)
AWS_REGION ?= eu-west-3
# Default AWS profile (override with environment variable or command line: make deploy AWS_PROFILE=...)
AWS_PROFILE ?= default
# Get AWS Account ID automatically (requires AWS CLI configured)
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
build: deps # Ensure dependencies are installed first
	@echo "---> Building Lambda deployment package in $(PACKAGE_DIR)..."
	rm -rf build $(PACKAGE_DIR)
	mkdir -p $(PACKAGE_DIR)
	# Install project dependencies into the package directory
	$(PIP) install . --target $(PACKAGE_DIR)
	# Copy the application source code into the package directory
	# Ensure the target directory exists within the package if needed
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
	@echo "---> Deploying stack $(STACK_NAME) to $(AWS_REGION)..."
	cd infrastructure && cdk deploy $(STACK_NAME) --profile $(AWS_PROFILE) --require-approval never
	@echo "---> Deployment potentially complete. Check AWS console for status."

.PHONY: destroy
destroy:
	@echo "---> Destroying stack $(STACK_NAME) from $(AWS_REGION)..."
	cd infrastructure && cdk destroy $(STACK_NAME) --profile $(AWS_PROFILE) --force
	@echo "---> Stack destruction initiated."

# Utility Targets
.PHONY: logs
logs:
	@echo "---> Tailing logs for Lambda function (requires stack deployed and function name output)..."
	# Get Lambda function name from stack outputs
	FUNCTION_NAME=$$(aws cloudformation describe-stacks --stack-name $(STACK_NAME) --query "Stacks[0].Outputs[?OutputKey=='LambdaFunctionName'].OutputValue" --output text --profile $(AWS_PROFILE) --region $(AWS_REGION))
	@if [ -z "$(FUNCTION_NAME)" ]; then \
		echo "Error: Could not retrieve Lambda function name from stack outputs."; \
		exit 1; \
	fi
	@echo "Tailing logs for function: $(FUNCTION_NAME)... Press Ctrl+C to stop."
	aws logs tail /aws/lambda/$(FUNCTION_NAME) --follow --profile $(AWS_PROFILE) --region $(AWS_REGION)

.PHONY: invoke
invoke:
	@echo "---> Example Invocation (Discovery):"
	@echo "# Get API Gateway endpoint URL:"
	@echo "API_URL=$$(aws cloudformation describe-stacks --stack-name $(STACK_NAME) --query \"Stacks[0].Outputs[?OutputKey=='ApiGatewayEndpoint'].OutputValue\" --output text --profile $(AWS_PROFILE) --region $(AWS_REGION))"
	@echo "# Send GET request:"
	@echo "curl $${API_URL}mcp"
	@echo ""
	@echo "---> Example Invocation (Add Document):"
	@echo "# Prepare JSON payload in a file (e.g., payload.json):"
	@echo "# { \"name\": \"rag_add_document\", \"parameters\": { \"content\": \"This is the document content.\" } }"
	@echo "# Send POST request:"
	@echo "curl -X POST -H \"Content-Type: application/json\" -d @payload.json $${API_URL}mcp"

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