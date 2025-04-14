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
```

## Setup & Configuration

1.  **Install Dependencies:** From the project root, install Python dependencies for the application and development (including CDK libraries).

    ```bash
    make deps
    ```

    This uses `pip install -e ".[dev]"` based on `pyproject.toml`.

2.  **AWS Credentials & Permissions:**

    - Ensure your configured AWS CLI profile (default or specified via `AWS_PROFILE` env var/Makefile) is active and has sufficient permissions.
    - **Permissions Needed:** The deployment (`make deploy`) will create/modify resources like Lambda, API Gateway, OpenSearch Serverless, S3, IAM Roles/Policies, Secrets Manager (reading), CloudFormation, and CloudWatch Logs.
    - **For initial setup/development:** Using an AWS profile with **AdministratorAccess** is often the simplest way to avoid permission issues, although it's **not recommended for production environments**.
    - **For production:** Follow the principle of least privilege, creating a dedicated IAM role/user with only the specific permissions required by CDK to manage these resources.

3.  **OpenAI API Key Secret in AWS Secrets Manager:**

    - **Why?:** Storing secrets like API keys directly in code or environment variables is insecure. AWS Secrets Manager provides a secure way to store and retrieve them.
    - **Steps:**
      1.  Log in to the **AWS Management Console**.
      2.  Navigate to **Secrets Manager**.
      3.  Ensure you are in the **correct AWS Region** where you intend to deploy the stack (e.g., `eu-west-3`). This _must_ match the deployment region.
      4.  Click **"Store a new secret"**.
      5.  Select **"Other type of secret"**.
      6.  Under **"Secret key/value"**, create **one** key-value pair:
          - **Key:** `OPENAI_API_KEY`
          - **Value:** Enter your actual OpenAI API key (e.g., `sk-YourActualOpenAiApiKey`). It should be the key itself, not wrapped in extra quotes _within this field_.
      7.  Click **Next**.
      8.  Enter a **Secret name**. The CDK stack expects the name `AI/MCP_SERVERS/RAG_SERVER` by default.
          - If you use a **different name**, you **must** update the `openai_secret_name` variable in `stack/rag_mpc_stack.py` before deploying.
      9.  Click **Next** (you can skip rotation settings for now).
      10. Review and click **"Store"**.

4.  **Environment Variables (Local Use):**
    - The `.env` file (copied from `.env.example`) is primarily for documenting required variables or potentially for advanced local testing/debugging scenarios if you manually configure access to AWS services locally.
    - Unit tests (`make test`) mock these variables and external services, so a `.env` file is not strictly required for running tests.
    - The deployed Lambda function gets its configuration directly from environment variables set by the CDK stack during deployment.

## Deployment and Management via Makefile

The `Makefile` provides convenient targets for managing the application lifecycle. You can override the default AWS region and profile using environment variables if needed (e.g., `AWS_REGION=us-east-1 make deploy`).

**Typical Workflow:**

1.  `make deps` (Install dependencies, needed once or after changes to `pyproject.toml`)
2.  `make bootstrap` (Bootstrap CDK, needed once per AWS account/region)
3.  Create the OpenAI Secret in AWS Secrets Manager (see Setup section above).
4.  `make deploy` (Builds and deploys the stack to AWS)
5.  `make invoke` / `make logs` / Use the application via its API endpoint.
6.  `make destroy` (When you want to remove the AWS resources)

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

- **`make invoke`**: Shows example `curl` commands (using the deployed API Gateway endpoint fetched from stack outputs) to test the MCP discovery and execution endpoints.

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

## Common Troubleshooting Tips

- **`ExpiredToken` / `InvalidClientTokenId` errors during `make deploy`/`bootstrap`/etc.:** Your AWS credentials have expired. Refresh them (e.g., `aws sso login`) and try the command again.
- **Deployment fails mentioning Secrets Manager:** Double-check:
  - The secret name in `stack/rag_mpc_stack.py` _exactly_ matches the name in AWS Secrets Manager.
  - The secret exists in the _same region_ you are deploying to.
  - The secret value contains the correct key (`OPENAI_API_KEY`).
  - The AWS credentials used for deployment have `secretsmanager:GetSecretValue` permission (usually covered by AdministratorAccess).
- **Deployment fails with IAM errors:** Ensure the AWS credentials used for deployment have sufficient permissions to create/modify all the required resources (see Permissions Needed in Setup section).
- **API Gateway returns 5xx errors after deployment:** Check the Lambda function logs using `make logs` for specific errors within the application code.
