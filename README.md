# RAG MCP Server (Cloud Ready)

This project implements a RAG (Retrieval-Augmented Generation) server designed as an MCP (Model Context Protocol) tool, ready for deployment on AWS ECS Fargate.

It uses FastAPI for the web framework, ChromaDB (client) for vector storage, OpenAI for embeddings and generation, and AWS S3 for persistent document storage.

Infrastructure is managed using the AWS Cloud Development Kit (CDK) with Python.

## Prerequisites

Before you begin, ensure you have the following installed:

- **Node.js and npm:** Required for AWS CDK. ([Download](https://nodejs.org/))
- **AWS CDK Toolkit:** `npm install -g aws-cdk`
- **AWS CLI:** Installed and configured (`aws configure`). ([Download](https://aws.amazon.com/cli/))
- **Python:** Version 3.8 or higher.
- **Poetry (Recommended)** or Pip: For managing Python dependencies defined in `pyproject.toml`.
- **Docker:** For building the container image.

## Project Structure

```
/
├── Dockerfile           # Container definition
├── pyproject.toml       # Application dependencies & project metadata
├── .env.example         # Example environment variables for local dev
├── README.md            # This file
├── src/                 # Application source code (FastAPI, utils, config)
├── infrastructure/      # AWS CDK infrastructure code (Python)
│   ├── stacks/          # CDK Stack definitions
│   ├── app.py           # CDK App entrypoint
│   ├── cdk.json         # CDK configuration
│   ├── poetry.lock      # CDK dependency lock file (if using Poetry)
│   └── pyproject.toml   # CDK Python dependencies
└── tests/               # Application tests
```

## Application Setup (Local)

1.  **Install Dependencies:** From the project root, install application dependencies defined in the main `pyproject.toml`.

    ```bash
    # Using Poetry
    poetry install --with dev

    # Or using Pip
    # pip install .[dev]
    ```

2.  **Environment Variables:** Copy `.env.example` to `.env` and fill in the required values (e.g., `OPENAI_API_KEY`, a mock or real `DOCUMENTS_S3_BUCKET`, `CHROMA_HOST` for a local ChromaDB instance).

## Infrastructure Setup (CDK)

1.  **Navigate to Infrastructure Directory:**
    ```bash
    cd infrastructure
    ```
2.  **Install CDK Dependencies:** Install the Python dependencies required _for the CDK code_ (defined in `infrastructure/pyproject.toml`).

    ```bash
    # Activate virtual environment if not already active (created by `cdk init`)
    # source .venv/bin/activate

    # Using Poetry (assuming you have poetry installed globally or manage it)
    poetry install

    # Or using Pip (if infrastructure/pyproject.toml is configured for it)
    # pip install .
    ```

3.  **Configure AWS Credentials:** Ensure your AWS CLI is configured with credentials that have permissions to deploy the necessary resources.

## Deployment via CDK

Deployment involves provisioning the AWS infrastructure using CDK and deploying the application container image.

1.  **Build & Push Docker Image:**

    - This step is typically done in a CI/CD pipeline.
    - Build the image from the **project root**: `docker build -t my-rag-mcp-server .`
    - Tag the image for your ECR repository (the repository URI will be an output after the first CDK deploy, or you can pre-define the name): `docker tag my-rag-mcp-server:latest <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/rag-mcp-server-repo:latest` (replace placeholders).
    - Log in to ECR and push the image: `aws ecr get-login-password ... | docker login ...`, `docker push <ECR_IMAGE_URI>`.

2.  **Bootstrap CDK (First Time Only):**

    - Run this from the `infrastructure` directory for the target AWS account and region:
      ```bash
      # Inside ./infrastructure/
      cdk bootstrap aws://ACCOUNT-ID/REGION
      ```

3.  **Synthesize (Optional):**

    - Review the CloudFormation template CDK will generate:
      ```bash
      # Inside ./infrastructure/
      cdk synth
      ```

4.  **Deploy Infrastructure & Application:**
    - Run the deployment from the `infrastructure` directory. You need to pass the `image_tag` (used in the ECR push) as context.
    - **Important:** Update placeholders in `infrastructure/stacks/rag_mcp_stack.py` (like `YOUR_SECRET_NAME` and `CHROMA_HOST`) before deploying.
      ```bash
      # Inside ./infrastructure/
      export IMAGE_TAG="latest" # Or specific tag like commit SHA
      cdk deploy -c image_tag=${IMAGE_TAG}
      ```
    - CDK will provision/update the resources (S3, ECR repo, ECS Cluster, Task Definition, Service, Load Balancer, etc.) and deploy the specified container image to the ECS service.
    - You might need to approve IAM or Security Group changes during the first deployment.

## Updating the Application

1.  Make code changes in `src/`.
2.  Build and push the new Docker image with a new tag (e.g., commit SHA) to ECR.
3.  Run `cdk deploy` from the `infrastructure` directory, passing the _new_ image tag via context:
    ```bash
    # Inside ./infrastructure/
    export NEW_IMAGE_TAG="new-commit-sha"
    cdk deploy --require-approval never -c image_tag=${NEW_IMAGE_TAG}
    ```
    CDK will create a new Task Definition revision and update the ECS Service to perform a rolling update (or Blue/Green if configured).

## CI/CD Integration

A typical CI/CD pipeline (e.g., GitHub Actions, AWS CodePipeline) would automate the following:

1.  **On code change (e.g., merge to main):**
2.  Run application tests.
3.  Build Docker image (from project root).
4.  Tag image (e.g., with Git commit SHA).
5.  Push image to ECR.
6.  Navigate to `infrastructure/` directory.
7.  Install CDK dependencies (`poetry install` or `pip install .`).
8.  Run `cdk deploy --require-approval never -c image_tag=<commit-sha>`.

## Local Development

- Use the `.env` file (copied from `.env.example`) to configure environment variables.
- You might need a local instance of ChromaDB running or use a development instance in AWS.
- You can run the FastAPI server locally using `uvicorn`: `uvicorn src.server:app --reload` (you might need to uncomment the `if __name__ == '__main__':` block in `src/server.py` or run it differently for local testing).
