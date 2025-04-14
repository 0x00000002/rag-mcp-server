# RAG MCP Server (Lambda + OpenSearch Serverless)

This project implements a RAG (Retrieval-Augmented Generation) server designed as an MCP (Model Context Protocol) tool, deployed using a serverless architecture on AWS.

It uses AWS Lambda for compute, API Gateway (HTTP API) for the request interface, OpenSearch Serverless for vector storage/search, OpenAI for embeddings and generation, and AWS S3 for persistent raw document storage.

Infrastructure is managed using the AWS Cloud Development Kit (CDK) with Python.

## Prerequisites

Before you begin, ensure you have the following installed:

- **Node.js and npm:** Required for AWS CDK. ([Download](https://nodejs.org/))
- **AWS CDK Toolkit:** Install globally via npm: `npm install -g aws-cdk`
- **AWS CLI:** Installed and configured. This is how CDK and the Makefile interact with your AWS account.
  - **Configuration:** You need to configure credentials, typically via:
    - IAM Identity Center (SSO): Run `aws configure sso` or `aws sso login`. This is the recommended modern approach.
    - IAM User: Run `aws configure` and provide an Access Key ID and Secret Access Key (less recommended for security).
  - See the [AWS CLI Configuration Guide](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-quickstart.html).
  - **Important:** Ensure the AWS profile you configure (or your default profile) has sufficient permissions (see Setup section).
- **Python:** Version 3.9 or higher (matching the Lambda runtime).
- **Pip:** Usually included with Python. Used for managing Python dependencies.
- **Make:** Required for using the Makefile automation targets. (Commonly pre-installed on Linux/macOS; may need installation on Windows).

## Project Structure

```
/
├── Makefile             # Automation commands (build, deploy, test, etc.)
├── pyproject.toml       # Application dependencies & project metadata
├── pytest.ini           # Pytest configuration (ensures tests find modules)
├── .env.example         # Example environment variables for local testing/config
├── README.md            # This file
├── src/                 # Application source code (Lambda handler, services, utils)
├── stack/               # CDK Stack definition (Python)
├── infrastructure/      # AWS CDK app definition and config
│   ├── app.py           # CDK App entrypoint
│   ├── cdk.json         # CDK configuration
└── tests/               # Application and infrastructure tests
    ├── test_lambda_handler.py
    └── test_infrastructure.py
└── example_payloads/    # Example JSON payloads for API requests
    ├── payload_add.json
    ├── payload_query.json
    └── payload_list.json
```

## Setup & Configuration

1.  **Install Dependencies:** From the project root, install Python dependencies.

    ```bash
    make deps
    ```

2.  **AWS Credentials & Permissions:** (Ensure AdministratorAccess or equivalent for deployment).

3.  **Create Secrets in AWS Secrets Manager (Target Region):**

    - **OpenAI API Key Secret:**
      - **Name:** `AI/MCP_SERVERS/RAG_SERVER` (or update `stack/rag_mpc_stack.py`)
      - **Type:** Other type of secret
      - **Secret key/value:** Add one key `OPENAI_API_KEY` with your `sk-...` key as the value.
    - **Application API Key Secret:**
      - **Why:** To authenticate client requests to your deployed API.
      - **Name:** `App/RagMcp/ApiKey` (or update `stack/rag_mpc_stack.py`)
      - **Type:** Other type of secret
      - **Secret value:** Choose **Plaintext** and enter a strong, random API key value that your client application (Agentic AI framework) will use. (e.g., generate a UUID or use a password generator). Do _not_ store it as key/value pairs, just the key string itself.

4.  **Environment Variables (Local Use):** (Not required for testing/deployment).

## Deployment and Management via Makefile

The `Makefile` provides convenient targets for managing the application lifecycle. You can override the default AWS region and profile using environment variables if needed (e.g., `AWS_REGION=us-east-1 make deploy`).

**Typical Workflow:**

1.  `make deps`
2.  `make bootstrap`
3.  **Create BOTH Secrets** (OpenAI Key, App API Key) in AWS Secrets Manager.
4.  `make deploy`
5.  `make invoke` / `make logs` / Use the application via its API endpoint (including API Key).
6.  `make destroy`

**Makefile Targets:**

- **`make build`**: Builds the Lambda deployment package (installing dependencies from `pyproject.toml` and copying `src/`) into the `build/lambda_package/` directory. This happens automatically as part of `make deploy` and `make test`.

- **`make bootstrap`**: (Run once per AWS Account/Region) Bootstraps the AWS environment for CDK deployment.

  - **Why?:** CDK needs certain AWS resources (like an S3 bucket) to store deployment assets and manage deployments. Bootstrapping creates these shared resources.

  ```bash
  # Example using the default region from Makefile/AWS config
  make bootstrap
  # Example overriding region
  make bootstrap AWS_REGION=us-east-1
  ```

- **`make deploy`**: Builds the Lambda package and deploys the entire stack (`RagMcpStack`) using `cdk deploy`.

  - **Prerequisites:** Valid AWS credentials, correctly configured OpenAI Secret in Secrets Manager, and CDK bootstrap completed for the target region.
  - **Process:** CDK synthesizes the stack definition into a CloudFormation template and deploys it. This creates/updates all the necessary AWS resources. It may take several minutes, especially the first time or when OpenSearch resources are created/updated.
  - **Output:** Upon successful completion, the API Gateway endpoint URL will be shown in the stack outputs.

  ```bash
  make deploy
  # Example overriding region and profile
  make deploy AWS_REGION=us-east-1 AWS_PROFILE=my-dev-profile
  ```

- **`make test`**: Builds the package (if needed) and runs the unit and infrastructure tests using `pytest`.

- **`make logs`**: Tails the CloudWatch logs for the deployed Lambda function in real-time. Requires the stack to be deployed successfully. Press Ctrl+C to stop.

- **`make destroy`**: Destroys all AWS resources created by the CDK stack via CloudFormation. Use with caution, as this is irreversible.

- **`make clean`**: Removes local build artifacts (`build/`, `cdk.out`, etc.). Does not affect deployed AWS resources.

- **`make invoke`**: Shows example `curl` commands for interacting with the deployed API.
  - First, set the API_KEY and API_URL environment variables as shown by the command output.
  - Then, run the example `curl` commands.
  - Note that POST requests use example JSON files from the `example_payloads/` directory.
  - **Example Deployed URL (from last successful deployment):** `https://9h8ob953ge.execute-api.eu-west-3.amazonaws.com/` (Note: Always use the URL from the `make invoke` output or CloudFormation outputs for the _current_ deployment).

## Architecture Overview

1.  **API Gateway (HTTP API):** Receives incoming HTTP requests for `/mcp` (GET for discovery, POST for execution).
2.  **Lambda Function:** Processes requests from API Gateway. Parses MCP calls, fetches secrets, generates embeddings (using OpenAI), interacts with OpenSearch Serverless and S3, and potentially calls OpenAI for generation.
3.  **OpenSearch Serverless:** Stores document embeddings and metadata. Provides k-NN vector search capabilities for the RAG retrieval step.
4.  **S3 Bucket:** Stores the original text content of added documents.
5.  **Secrets Manager:** Securely stores the OpenAI API key.
6.  **IAM:** Defines permissions for the Lambda function to access other AWS services (S3, Secrets Manager, OpenSearch, CloudWatch Logs).
7.  **CloudWatch:** Collects logs from the Lambda function.

## Development Notes

- **Testing:** Use `make test` to run unit tests with mocked AWS/OpenAI/OpenSearch dependencies. True end-to-end testing typically involves deploying to a development AWS environment.
- **Dependencies:** Add Python dependencies to `pyproject.toml` and run `make deps`.
- **Infrastructure:** Modify AWS resources by editing `stack/rag_mpc_stack.py`.
- **Application Logic:** Modify Lambda behavior by editing files within the `src/` directory.

## Running the Example Script

An example Python script (`example.py`) demonstrates how to interact with the deployed API:

1.  **Deploy the Stack:** Ensure the stack is deployed (`make deploy`).
2.  **Set Environment Variables:** You need to provide the deployed API URL and your App API Key as environment variables. You can get these using `make invoke` or from the CloudFormation stack outputs.

    ```bash
    # Get the URL (example)
    export API_URL=$(aws cloudformation describe-stacks --stack-name RagMcpStack --query "Stacks[0].Outputs[?OutputKey=='ApiGatewayEndpoint'].OutputValue" --output text --profile <YOUR_PROFILE> --region <YOUR_REGION>)

    # Set your key (replace with the actual key from Secrets Manager)
    export API_KEY="<YOUR_APP_API_KEY>"
    ```

3.  **Run the Script:**
    ```bash
    python example.py
    ```
    The script will call the discovery endpoint, add two documents, list documents, and perform a query, printing the requests and responses.
    _Note:_ The script requires the `requests` library (`pip install requests` if you don't have it, though it should be installed via `make deps`).

## Common Troubleshooting Tips

- **`ExpiredToken` / `InvalidClientTokenId` errors:** Refresh AWS credentials (`aws sso login`).
- **Deployment fails mentioning Secrets Manager:** Check:
  - Secret names in CDK match AWS exactly.
  - Secrets exist in the _same region_ as deployment.
  - Secret values are correctly formatted (OpenAI key needs `OPENAI_API_KEY` field, App API Key should be plaintext).
  - Deployer credentials have `secretsmanager:GetSecretValue` permission.
- **Deployment fails with IAM errors:** Check deployer permissions.
- **API Gateway returns 401 Unauthorized:** Ensure the client is sending the correct API key value in the `X-API-Key` header.
- **API Gateway returns 5xx errors:** Check Lambda logs (`make logs`).
