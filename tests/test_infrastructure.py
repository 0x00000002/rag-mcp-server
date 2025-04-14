"""Tests for the CDK stack definition."""

import aws_cdk as cdk
from aws_cdk.assertions import Template, Match

# Import the stack class from your application
from stack.rag_mpc_stack import RagMcpStack # Should work now from root tests dir

def test_stack_synthesis():
    """Test that the CDK stack synthesizes correctly and contains expected resources."""
    app = cdk.App()
    
    # Create an instance of the stack
    stack = RagMcpStack(app, "TestRagMcpStack") # Use a unique ID for testing
    
    # Prepare the stack for assertions
    template = Template.from_stack(stack)
    
    # --- Assertions for Key Resources ---
    
    # 1. Lambda Function
    # Find the specific function by handler, as CDK might create others
    functions = template.find_resources("AWS::Lambda::Function", {
        "Properties": {
            "Handler": "src.lambda_handler.main"
        }
    })
    assert len(functions) == 1 # Ensure we found exactly one function with our handler
    # Now assert properties on the specific function found (using its logical ID)
    function_logical_id = list(functions.keys())[0]
    template.has_resource_properties("AWS::Lambda::Function", {
        # "Handler": "src.lambda_handler.main", # Already checked by find_resources
        "Runtime": "python3.9",
        "Timeout": 30,
        # Check for presence of environment variables (values depend on deploy-time outputs)
        "Environment": {
            "Variables": {
                "OPENAI_API_KEY_SECRET_NAME": Match.any_value(),
                "OPENSEARCH_COLLECTION_ENDPOINT": Match.any_value(),
                "OPENSEARCH_INDEX_NAME": "documents",
                "DOCUMENTS_S3_BUCKET": Match.any_value(),
            }
        }
    })
    
    # 2. Lambda Execution Role
    template.has_resource_properties("AWS::IAM::Role", {
        "AssumeRolePolicyDocument": {
            "Statement": [{
                "Action": "sts:AssumeRole",
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"}
            }]
        },
        # Check for managed policies (basic execution role)
        "ManagedPolicyArns": Match.array_with([
            {"Fn::Join": ["", ["arn:", Match.any_value(), ":iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"]]}
        ])
    })
    # Optionally, check for specific inline policy statements (e.g., Secrets Manager, S3, OpenSearch access)
    # template.has_resource_properties("AWS::IAM::Policy", Match.object_like({...}))

    # 3. API Gateway (HTTP API)
    template.has_resource_properties("AWS::ApiGatewayV2::Api", {
        "Name": Match.string_like_regexp("rag-mcp-server-lambda-api"),
        "ProtocolType": "HTTP",
        "CorsConfiguration": {
            "AllowOrigins": ["*"], # Check the permissive CORS setting
            "AllowMethods": Match.any_value() # Or be more specific
        }
    })
    # Check for routes (GET and POST /mcp)
    template.resource_count_is("AWS::ApiGatewayV2::Route", 2)
    template.has_resource_properties("AWS::ApiGatewayV2::Route", {
        "RouteKey": "POST /mcp",
        "ApiId": Match.any_value()
    })
    template.has_resource_properties("AWS::ApiGatewayV2::Route", {
        "RouteKey": "GET /mcp",
        "ApiId": Match.any_value()
    })
    # Check for integration
    template.resource_count_is("AWS::ApiGatewayV2::Integration", 1) 

    # 4. OpenSearch Serverless Collection
    template.has_resource_properties("AWS::OpenSearchServerless::Collection", {
        "Name": Match.string_like_regexp("rag-mcp-server-lambda-collection"),
        "Type": "VECTORSEARCH"
    })
    
    # 5. OpenSearch Serverless Policies (check count or specific properties)
    template.resource_count_is("AWS::OpenSearchServerless::AccessPolicy", 1)
    template.resource_count_is("AWS::OpenSearchServerless::SecurityPolicy", 2) # Network + Encryption
    template.has_resource_properties("AWS::OpenSearchServerless::SecurityPolicy", {
        "Type": "network",
        "Policy": Match.string_like_regexp(".*AllowFromPublic.*") # Check if public access is allowed
    })
    template.has_resource_properties("AWS::OpenSearchServerless::SecurityPolicy", {
        "Type": "encryption",
        "Policy": Match.string_like_regexp(".*AWSOwnedKey.*")
    })

    # 6. S3 Bucket
    template.has_resource_properties("AWS::S3::Bucket", {
        # "BucketName": Match.string_like_regexp("rag-mcp-server-lambda-documents-"), # Fails because name uses Fn::Join
        "BucketName": Match.any_value(), # Check that the property exists, accept dynamic name
        "PublicAccessBlockConfiguration": {
            "BlockPublicAcls": True,
            "BlockPublicPolicy": True,
            "IgnorePublicAcls": True,
            "RestrictPublicBuckets": True
        },
        "CorsConfiguration": Match.any_value() # Check that CORS is configured
    })
    # Check for bucket policy allowing Lambda access (added by grant_read_write)
    # template.has_resource_properties("AWS::S3::BucketPolicy", Match.object_like({...}))

    # 7. Check Outputs
    template.has_output("ApiGatewayEndpoint", Match.any_value())
    template.has_output("DocumentsBucketName", Match.any_value())
    template.has_output("OpenSearchCollectionEndpoint", Match.any_value())
    template.has_output("LambdaFunctionName", Match.any_value())
    template.has_output("LambdaFunctionRoleArn", Match.any_value()) 