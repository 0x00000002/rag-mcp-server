from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_ecr as ecr,
    aws_s3 as s3,
    aws_iam as iam,
    aws_logs as logs,
    aws_secretsmanager as secretsmanager,
    Duration,
    RemovalPolicy,
    CfnOutput
)
from constructs import Construct

class RagMcpStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- Configuration ---
        # Best practice: Pass dynamic values like image tag via context in cdk.json or CLI (-c)
        # Example: cdk deploy -c image_tag=latest
        image_tag = self.node.try_get_context("image_tag") or "latest"
        app_name = "rag-mcp-server"

        # Reference existing resources or define them
        # Using default VPC for simplicity, or lookup/create a specific one
        vpc = ec2.Vpc.from_lookup(self, "Vpc", is_default=True)
        # Or create a new VPC: vpc = ec2.Vpc(self, "AppVpc", max_azs=2)

        # --- ECR Repository ---
        # Option 1: Use an existing repository
        # ecr_repo = ecr.Repository.from_repository_name(self, "AppRepo", f"{app_name}-repo")

        # Option 2: Create a new repository
        ecr_repo = ecr.Repository(
            self, "AppRepo",
            repository_name=f"{app_name}-repo",
            removal_policy=RemovalPolicy.DESTROY, # Or RETAIN
            auto_delete_images=True # Convenient for dev/test
        )

        # --- S3 Bucket ---
        documents_bucket = s3.Bucket(
            self, "DocumentsBucket",
            bucket_name=f"{app_name}-documents-{self.account}-{self.region}", # Globally unique name
            removal_policy=RemovalPolicy.DESTROY, # DESTROY deletes bucket on stack delete (use RETAIN for prod)
            auto_delete_objects=True, # Required if removal_policy is DESTROY
            versioned=False, # Enable if needed
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED
        )

        # --- IAM Roles ---
        # Execution Role (Permissions for ECS Agent to pull image, write logs, etc.)
        # The pattern creates a basic one, but you can customize it
        execution_role = iam.Role(
            self, "EcsTaskExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
                # Add policy statement to allow reading the specific secret if needed
            ]
        )

        # Task Role (Permissions for your application code)
        task_role = iam.Role(
            self, "AppTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com")
        )
        # Grant S3 Put access to the documents bucket
        documents_bucket.grant_write(task_role)

        # --- Secrets Manager ---
        # Reference the existing secret holding the OpenAI API Key
        # Ensure the Execution Role has permission to read this secret
        openai_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "OpenAiApiKeySecret",
            secret_name="YOUR_SECRET_NAME" # <-- REPLACE with your actual Secret name
        )
        # Grant the Execution Role read access (needed by ECS agent to inject secret)
        openai_secret.grant_read(execution_role)

        # --- ECS Cluster ---
        cluster = ecs.Cluster(self, "AppCluster", vpc=vpc)

        # --- Log Group ---
        log_group = logs.LogGroup(
            self, "AppLogGroup",
            log_group_name=f"/ecs/{app_name}",
            removal_policy=RemovalPolicy.DESTROY, # Or RETAIN
            retention=logs.RetentionDays.ONE_MONTH # Adjust as needed
        )

        # --- ECS Fargate Service with Load Balancer ---
        fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "AppFargateService",
            cluster=cluster,
            cpu=1024,  # 1 vCPU
            memory_limit_mib=2048, # 2 GB
            desired_count=1, # Number of tasks to run
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_ecr_repository(ecr_repo, image_tag),
                container_port=8080,
                execution_role=execution_role,
                task_role=task_role,
                log_driver=ecs.LogDrivers.aws_logs(
                    stream_prefix="app", # Container log stream prefix
                    log_group=log_group
                ),
                environment={
                    # Non-sensitive vars
                    "DOCUMENTS_S3_BUCKET": documents_bucket.bucket_name,
                    "CHROMA_HOST": "IP_OR_DNS_OF_CHROMA_SERVICE", # <-- REPLACE
                    "CHROMA_PORT": "8000",
                    "CHROMA_COLLECTION": "documents",
                    "OPENAI_EMBEDDING_MODEL": "text-embedding-ada-002",
                    "OPENAI_CHAT_MODEL": "gpt-3.5-turbo",
                    "AWS_REGION": self.region
                },
                secrets={
                    # Inject sensitive vars from Secrets Manager
                    "OPENAI_API_KEY": ecs.Secret.from_secrets_manager(openai_secret)
                }
            ),
            task_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS), # Run tasks in private subnets
            public_load_balancer=True, # Creates a public ALB
            # listener_port=443, # If using HTTPS, configure certificate
            # certificate=acm.Certificate.from_certificate_arn(...),
            redirect_http=False, # Set true if using HTTPS
            # Configure Health Check if defaults are not suitable
            # health_check=ecs.HealthCheck(...)
        )

        # --- Outputs ---
        CfnOutput(self, "LoadBalancerDNS", value=fargate_service.load_balancer.load_balancer_dns_name)
        CfnOutput(self, "EcrRepositoryUri", value=ecr_repo.repository_uri)
        CfnOutput(self, "DocumentsBucketName", value=documents_bucket.bucket_name)
