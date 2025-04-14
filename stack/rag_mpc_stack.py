from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_apigatewayv2 as apigwv2, # Using HTTP API (v2) for cost/simplicity
    aws_apigatewayv2_integrations as apigwv2_integrations,
    aws_opensearchserverless as opensearchserverless,
    aws_secretsmanager as secretsmanager,
    aws_logs as logs,
    Duration,
    RemovalPolicy,
    CfnOutput
)
import json
from constructs import Construct
# Removed aws_ec2, aws_ecs, aws_ecs_patterns, aws_ecr as they are no longer needed

class RagMcpStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- Configuration ---
        app_name = "rag-mcp-server-lambda" # Updated app name
        # Ensure you have this secret created in AWS Secrets Manager
        openai_secret_name = "AI/MCP_SERVERS/RAG_SERVER" # <-- CONFIRM OR REPLACE
        opensearch_collection_name = f"{app_name}-collection"
        opensearch_index_name = "documents" # Index within the collection
        openai_embedding_model = "text-embedding-ada-002"
        openai_chat_model = "gpt-3.5-turbo"

        # --- Secrets --- # Group secrets together
        # OpenAI API Key Secret
        openai_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "OpenAiApiKeySecret",
            secret_name=openai_secret_name
        )
        # Application API Key Secret (User needs to create this manually)
        # Ensure this secret exists in the target region before deploying!
        app_api_key_secret_name = "AI/MCP_SERVERS/RAG_SERVER_API_KEY" # <-- User specified name
        app_api_key_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "AppApiKeySecret",
            secret_name=app_api_key_secret_name
        )

        # --- S3 Bucket ---
        documents_bucket = s3.Bucket(
            self, "DocumentsBucket",
            bucket_name=f"{app_name}-documents-{self.account}-{self.region}",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            versioned=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            cors=[ # Add CORS configuration if API Gateway needs to call S3 directly (unlikely here)
                  # or if your frontend needs direct access (more likely)
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.GET, s3.HttpMethods.PUT, s3.HttpMethods.POST, s3.HttpMethods.DELETE, s3.HttpMethods.HEAD],
                    allowed_origins=["*"], # Be more specific in production!
                    allowed_headers=["*"],
                    max_age=3000
                )
            ]
        )

        # --- OpenSearch Serverless Collection ---
        # Data Access Policy for Lambda
        # Shorten name to comply with ^[a-z][a-z0-9-]{2,31}$ (max 32 chars)
        lambda_access_policy_name = f"{app_name}-data-pol"
        lambda_access_policy = opensearchserverless.CfnAccessPolicy(
            self, "LambdaAccessPolicy",
            name=lambda_access_policy_name,
            type="data",
            # Simplify policy to only grant necessary index permissions
            policy=json.dumps([
                {
                    "Rules": [
                        # Removed invalid collection-level rule
                        {
                             "ResourceType": "index", # Must be literal "index"
                             "Resource": [f"index/{opensearch_collection_name}/{opensearch_index_name}*"],
                             "Permission": ["aoss:*"] # Grant broad index permissions for simplicity
                        }
                    ],
                    # Placeholder updated below after role creation
                    "Principal": ["PLACEHOLDER_LAMBDA_ROLE_ARN"],
                    "Description": "Policy granting Lambda index access"
                }
            ])
        )

        # Network Access Policy
        # Shorten name to comply with constraints
        network_policy_name = f"{app_name}-net-pol"
        network_policy = opensearchserverless.CfnSecurityPolicy(
            self, "NetworkPolicy",
            name=network_policy_name,
            type="network",
            policy=json.dumps([
                 {
                    "Rules": [
                        {
                            "ResourceType": "collection",
                            "Resource": [f"collection/{opensearch_collection_name}"]
                        }
                    ],
                    "AllowFromPublic": True # Restrict in production!
                    # Add VpcEndpointIds here if using VPC access
                }
            ])
        )

        # Encryption Policy
        # Shorten name to comply with constraints
        encryption_policy_name = f"{app_name}-enc-pol"
        encryption_policy = opensearchserverless.CfnSecurityPolicy(
            self, "EncryptionPolicy",
            name=encryption_policy_name,
            type="encryption",
            policy=json.dumps({
                "Rules": [
                    {
                        "ResourceType": "collection",
                        "Resource": [f"collection/{opensearch_collection_name}"]
                    }
                ],
                "AWSOwnedKey": True
            })
        )

        # OpenSearch Serverless Collection itself
        collection = opensearchserverless.CfnCollection(
            self, "OpenSearchCollection",
            name=opensearch_collection_name,
            type="VECTORSEARCH",
            description=f"OpenSearch Serverless collection for {app_name}",
            # Standby replicas default to 0 for VECTORSEARCH, adjust if needed
        )
        collection.add_dependency(network_policy)
        collection.add_dependency(encryption_policy)
        # Note: Access policy needs principals added, often done in a second step or manually


        # --- IAM Role for Lambda ---
        lambda_role = iam.Role(
            self, "AppLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole" # Basic CloudWatch Logs access
                ),
                # Add policy for VPC access if Lambda needs to run in VPC
                # iam.ManagedPolicy.from_aws_managed_policy_name(
                #     "service-role/AWSLambdaVPCAccessExecutionRole"
                # )
            ],
            # Add inline policies for specific access
            inline_policies={
                "OpenSearchAccessPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=[
                                "aoss:APIAccessAll" # Broad permissions for simplicity, refine if needed
                                # Actions needed depend on opensearch-py client usage
                                # e.g., aoss:BatchGetCollection, aoss:GetSecurityPolicy, aoss:ListIndexes etc.
                            ],
                            resources=[collection.attr_arn], # Access to the collection
                            effect=iam.Effect.ALLOW
                        )
                    ]
                ),
                "SecretAccessPolicy": iam.PolicyDocument(
                     statements=[
                        # Grant access to OpenAI secret (both base ARN and wildcard ARN)
                        iam.PolicyStatement(
                            actions=["secretsmanager:GetSecretValue"],
                            resources=[
                                openai_secret.secret_arn,
                                f"{openai_secret.secret_arn}-*" # Add wildcard version explicitly
                            ],
                            effect=iam.Effect.ALLOW
                        ),
                        # Grant access to App API Key secret (both base ARN and wildcard ARN)
                        iam.PolicyStatement(
                            actions=["secretsmanager:GetSecretValue"],
                            resources=[
                                app_api_key_secret.secret_arn,
                                f"{app_api_key_secret.secret_arn}-*" # Add wildcard version explicitly
                            ],
                            effect=iam.Effect.ALLOW
                        )
                    ]
                )
                # S3 Access will be granted below using grant_read_write
            }
        )

        # Grant S3 permissions to Lambda Role
        documents_bucket.grant_read_write(lambda_role)


        # --- Lambda Function ---
        # Define environment variables for the Lambda function
        lambda_environment = {
            "DOCUMENTS_S3_BUCKET": documents_bucket.bucket_name,
            "OPENAI_API_KEY_SECRET_NAME": openai_secret.secret_name, # Lambda needs name to fetch value
            "APP_API_KEY_SECRET_NAME": app_api_key_secret.secret_name, # Add the app API key secret name
            "OPENAI_EMBEDDING_MODEL": openai_embedding_model,
            "OPENAI_CHAT_MODEL": openai_chat_model,
            "OPENSEARCH_COLLECTION_ENDPOINT": collection.attr_collection_endpoint,
            "OPENSEARCH_INDEX_NAME": opensearch_index_name,
            "LOG_LEVEL": "INFO" # Example: Control logging level
        }

        # Define the Lambda function
        app_lambda = lambda_.Function(
            self, "AppLambda",
            runtime=lambda_.Runtime.PYTHON_3_9, # Choose appropriate Python runtime
            handler="src.lambda_handler.main",  # Assuming handler structure is src/lambda_handler.py -> main()
            code=lambda_.Code.from_asset("../build/lambda_package"), # CORRECTED: Path relative to infrastructure/ up to root build dir
                                               # Requires a build step to install deps into a specific folder or use layers/containers
            role=lambda_role,
            environment=lambda_environment,
            timeout=Duration.seconds(30), # Adjust timeout as needed (max 15 mins)
            memory_size=512, # Adjust memory as needed (affects cost and CPU proportionally)
            log_retention=logs.RetentionDays.ONE_MONTH # Configure log retention
            # Add VPC configuration if Lambda needs to access resources in a VPC (like OpenSearch)
            # vpc=vpc,
            # vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            # security_groups=[your_lambda_security_group]
        )

        # --- API Gateway (HTTP API) ---
        http_api = apigwv2.HttpApi(
            self, "HttpApi",
            cors_preflight=apigwv2.CorsPreflightOptions( # Configure CORS for your frontend domain
                allow_headers=["*"],
                allow_methods=[apigwv2.CorsHttpMethod.ANY],
                allow_origins=["*"], # VERY permissive, restrict in production!
                max_age=Duration.days(10),
            ),
            api_name=f"{app_name}-api",
            description=f"API Gateway for {app_name}"
        )

        # Create Lambda integration
        lambda_integration = apigwv2_integrations.HttpLambdaIntegration("LambdaIntegration", app_lambda)

        # Define routes
        http_api.add_routes(
            path="/mcp",
            methods=[apigwv2.HttpMethod.POST],
            integration=lambda_integration
        )
        # Optional: Add GET /mcp for discovery if needed, potentially different Lambda or logic within main handler
        http_api.add_routes(
            path="/mcp",
            methods=[apigwv2.HttpMethod.GET],
            integration=lambda_integration # Can point to the same lambda, handler differentiates method
        )

        # --- Update OpenSearch Access Policy with Lambda Role ARN ---
        # NOTE: This creates a deployment dependency cycle.
        # Common solutions:
        # 1. Manually update the policy after first deployment.
        # 2. Use CDK Custom Resources to perform the update.
        # 3. Output the Lambda Role ARN and update the policy definition outside CDK.
        # For now, we output the ARN and indicate manual update needed.
        # Or, we can grant access to the AWS account root and rely on IAM permissions (less secure).
        # Let's try granting to the role directly, CDK might handle the dependency.

        # Re-fetch the CfnAccessPolicy to modify it (or modify the definition before instantiation)
        # This is tricky as policy is defined above. Let's modify the definition directly:
        lambda_access_policy.policy = json.dumps([
                {
                    "Rules": [
                        {
                            "ResourceType": "index",
                            "Resource": [f"index/{opensearch_collection_name}/{opensearch_index_name}*"],
                            "Permission": ["aoss:*"]
                        }
                    ],
                    "Principal": [lambda_role.role_arn], # Use the actual ARN now
                    "Description": "Policy granting Lambda index access"
                }
            ])

        # Add dependency explicitly?
        lambda_access_policy.add_dependency(collection) # Policy depends on collection ARN? No.
        # Policy Principal depends on Lambda Role. Collection depends on Policy. Lambda Role depends on Collection (for inline policy).
        # This might deploy correctly if CloudFormation/CDK resolve it, but often requires workarounds.


        # --- Outputs ---
        CfnOutput(self, "ApiGatewayEndpoint", value=http_api.url) # Output the API endpoint URL
        CfnOutput(self, "DocumentsBucketName", value=documents_bucket.bucket_name)
        CfnOutput(self, "OpenSearchCollectionEndpoint", value=collection.attr_collection_endpoint)
        CfnOutput(self, "OpenSearchCollectionARN", value=collection.attr_arn)
        CfnOutput(self, "LambdaFunctionName", value=app_lambda.function_name)
        CfnOutput(self, "LambdaFunctionRoleArn", value=lambda_role.role_arn, description="ARN of the Lambda execution role. Use this if manual update of OpenSearch access policy principal is needed.")


# Removed previous ECS/ECR/ALB resources and outputs
