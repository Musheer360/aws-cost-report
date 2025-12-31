# AWS Cost Report Generator - Deployment Guide

This guide covers both AWS Cloud deployment and Local installation options.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Local Installation (Linux/WSL)](#local-installation-linuxwsl)
- [AWS Cloud Deployment](#aws-cloud-deployment)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### For Local Installation
- Python 3.8+
- AWS CLI configured with credentials
- IAM permissions: `ce:GetCostAndUsage`, `ce:GetCostForecast`

### For AWS Cloud Deployment
- AWS CLI configured with admin credentials
- IAM permissions to create:
  - Lambda functions
  - S3 buckets
  - API Gateway
  - IAM roles

---

## Local Installation (Linux/WSL)

Local installation runs the cost report generator as a command-line tool on your machine.

### Quick Install

```bash
cd aws-cost-report
./deploy.sh
# Select option 2 for local installation
```

Or directly:

```bash
cd aws-cost-report/local
./install.sh
```

### What the Installer Does

1. Checks for Python 3 and pip
2. Verifies AWS CLI installation
3. Optionally creates a Python virtual environment
4. Installs required dependencies (boto3, openpyxl)
5. Creates a convenience wrapper script

### Usage

After installation:

```bash
# Generate a cost report
./local/costreport --client "Acme Corp" --months 2024-10 2024-11 2024-12

# Use a specific AWS profile
./local/costreport --profile production --client "Client A" --months 2024-09 2024-10

# Save to a specific directory
./local/costreport --client "Client B" --months 2024-11 2024-12 --output ~/reports

# Show all options
./local/costreport --help
```

### CLI Options

| Option | Short | Required | Description |
|--------|-------|----------|-------------|
| `--client` | `-c` | Yes | Client name (used in filename) |
| `--months` | `-m` | Yes | 2-6 months in YYYY-MM format |
| `--profile` | `-p` | No | AWS CLI profile name |
| `--region` | `-r` | No | AWS region (default: us-east-1) |
| `--output` | `-o` | No | Output directory (default: current) |

### Manual Installation

If you prefer manual installation:

```bash
cd aws-cost-report/local

# Create virtual environment (optional)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run directly
python3 cost_report_cli.py --client "Test" --months 2024-11 2024-12
```

### Local Installation Limitations

- **No cross-account IAM role support**: The local version can only use AWS CLI credentials configured on your machine
- **No web interface**: Command-line only
- **Single account access**: Can only access accounts where you have credentials configured

### Required IAM Permissions

The AWS user/role configured in your CLI needs these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ce:GetCostAndUsage",
        "ce:GetCostForecast"
      ],
      "Resource": "*"
    }
  ]
}
```

---

## AWS Cloud Deployment

### Option 1: Automated Deployment (Recommended)

### Using the Deploy Script

```bash
cd aws-cost-report
./deploy.sh
# Select option 1 for AWS Cloud deployment
```

This script will:
1. Deploy CloudFormation stack
2. Package Lambda function with dependencies
3. Upload Lambda code
4. Upload frontend to S3
5. Output the frontend URL and API endpoint

**Outputs:**
- Frontend URL: `http://cost-report-frontend-{ACCOUNT_ID}.s3-website-{REGION}.amazonaws.com`
- API Endpoint: Automatically configured in frontend

---

### Option 2: CloudFormation Template Deployment

### Step 1: Deploy Infrastructure

```bash
aws cloudformation deploy \
    --template-file cloudformation.yaml \
    --stack-name cost-report-generator \
    --capabilities CAPABILITY_NAMED_IAM \
    --region ap-south-1
```

### Step 2: Get Stack Outputs

```bash
aws cloudformation describe-stacks \
    --stack-name cost-report-generator \
    --region ap-south-1 \
    --query 'Stacks[0].Outputs'
```

Note the following outputs:
- `FrontendURL` - S3 website URL
- `ApiEndpoint` - API Gateway endpoint
- `LambdaFunctionName` - Lambda function name

### Step 3: Package Lambda Function

```bash
cd lambda
pip install -r requirements.txt -t .
zip -r ../lambda.zip .
cd ..
```

### Step 4: Deploy Lambda Code

```bash
aws lambda update-function-code \
    --function-name CostReportGenerator \
    --zip-file fileb://lambda.zip \
    --region ap-south-1
```

### Step 5: Update Frontend with API Endpoint

Edit `frontend/index.html` and replace:
```javascript
const API_ENDPOINT = 'YOUR_API_GATEWAY_URL';
```

With your actual API Gateway endpoint from Step 2.

### Step 6: Upload Frontend to S3

```bash
BUCKET_NAME=$(aws cloudformation describe-stacks \
    --stack-name cost-report-generator \
    --region ap-south-1 \
    --query 'Stacks[0].Outputs[?OutputKey==`FrontendURL`].OutputValue' \
    --output text | sed 's|http://||' | sed 's|.s3-website.*||')

aws s3 cp frontend/index.html s3://$BUCKET_NAME/ --region ap-south-1
```

---

## Option 3: Manual Deployment (No CloudFormation)

### Step 1: Create S3 Bucket for Frontend

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET_NAME="cost-report-frontend-${ACCOUNT_ID}"

aws s3 mb s3://$BUCKET_NAME --region ap-south-1

aws s3 website s3://$BUCKET_NAME \
    --index-document index.html

# Enable public access
aws s3api put-public-access-block \
    --bucket $BUCKET_NAME \
    --public-access-block-configuration \
    "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false"

# Add bucket policy
cat > /tmp/bucket-policy.json << EOF
{
  "Version": "2008-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": "*",
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::${BUCKET_NAME}/*"
  }]
}
EOF

aws s3api put-bucket-policy \
    --bucket $BUCKET_NAME \
    --policy file:///tmp/bucket-policy.json
```

### Step 2: Create IAM Role for Lambda

```bash
# Create trust policy
cat > /tmp/trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "lambda.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
EOF

aws iam create-role \
    --role-name CostReportLambdaRole \
    --assume-role-policy-document file:///tmp/trust-policy.json

# Attach basic execution policy
aws iam attach-role-policy \
    --role-name CostReportLambdaRole \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# Create and attach Cost Explorer policy
cat > /tmp/ce-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "ce:GetCostAndUsage",
      "ce:GetCostForecast"
    ],
    "Resource": "*"
  }]
}
EOF

aws iam put-role-policy \
    --role-name CostReportLambdaRole \
    --policy-name CostExplorerAccess \
    --policy-document file:///tmp/ce-policy.json
```

### Step 3: Create Lambda Function

```bash
# Package Lambda
cd lambda
pip install -r requirements.txt -t .
zip -r ../lambda.zip .
cd ..

# Get role ARN
ROLE_ARN=$(aws iam get-role --role-name CostReportLambdaRole --query 'Role.Arn' --output text)

# Create Lambda function
aws lambda create-function \
    --function-name CostReportGenerator \
    --runtime python3.11 \
    --role $ROLE_ARN \
    --handler lambda_function.lambda_handler \
    --zip-file fileb://lambda.zip \
    --timeout 300 \
    --memory-size 512 \
    --region ap-south-1
```

### Step 4: Create API Gateway

```bash
# Create HTTP API
API_ID=$(aws apigatewayv2 create-api \
    --name CostReportAPI \
    --protocol-type HTTP \
    --cors-configuration AllowOrigins='*',AllowMethods='POST',AllowHeaders='*' \
    --region ap-south-1 \
    --query 'ApiId' \
    --output text)

# Get Lambda ARN
LAMBDA_ARN=$(aws lambda get-function \
    --function-name CostReportGenerator \
    --region ap-south-1 \
    --query 'Configuration.FunctionArn' \
    --output text)

# Create integration
INTEGRATION_ID=$(aws apigatewayv2 create-integration \
    --api-id $API_ID \
    --integration-type AWS_PROXY \
    --integration-uri $LAMBDA_ARN \
    --payload-format-version 2.0 \
    --region ap-south-1 \
    --query 'IntegrationId' \
    --output text)

# Create route
aws apigatewayv2 create-route \
    --api-id $API_ID \
    --route-key 'POST /generate' \
    --target integrations/$INTEGRATION_ID \
    --region ap-south-1

# Create stage
aws apigatewayv2 create-stage \
    --api-id $API_ID \
    --stage-name prod \
    --auto-deploy \
    --region ap-south-1

# Grant API Gateway permission to invoke Lambda
aws lambda add-permission \
    --function-name CostReportGenerator \
    --statement-id apigateway-invoke \
    --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:ap-south-1:${ACCOUNT_ID}:${API_ID}/*" \
    --region ap-south-1

# Get API endpoint
API_ENDPOINT="https://${API_ID}.execute-api.ap-south-1.amazonaws.com/prod/generate"
echo "API Endpoint: $API_ENDPOINT"
```

### Step 5: Update and Upload Frontend

Edit `frontend/index.html` and replace:
```javascript
const API_ENDPOINT = 'YOUR_API_GATEWAY_URL';
```

With your API endpoint from Step 4, then upload:

```bash
aws s3 cp frontend/index.html s3://$BUCKET_NAME/ --region ap-south-1

echo "Frontend URL: http://${BUCKET_NAME}.s3-website.ap-south-1.amazonaws.com"
```

---

## Updating the Application

### Update Lambda Code

```bash
cd lambda
zip -r ../lambda.zip .
cd ..

aws lambda update-function-code \
    --function-name CostReportGenerator \
    --zip-file fileb://lambda.zip \
    --region ap-south-1
```

### Update Frontend

```bash
aws s3 cp frontend/index.html s3://cost-report-frontend-{ACCOUNT_ID}/ --region ap-south-1
```

---

## Cleanup/Deletion

### Using CloudFormation

```bash
aws cloudformation delete-stack \
    --stack-name cost-report-generator \
    --region ap-south-1
```

### Manual Cleanup

```bash
# Delete Lambda
aws lambda delete-function \
    --function-name CostReportGenerator \
    --region ap-south-1

# Delete API Gateway
aws apigatewayv2 delete-api \
    --api-id $API_ID \
    --region ap-south-1

# Empty and delete S3 bucket
aws s3 rm s3://$BUCKET_NAME --recursive
aws s3 rb s3://$BUCKET_NAME

# Delete IAM role
aws iam delete-role-policy \
    --role-name CostReportLambdaRole \
    --policy-name CostExplorerAccess

aws iam detach-role-policy \
    --role-name CostReportLambdaRole \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

aws iam delete-role --role-name CostReportLambdaRole
```

---

## Troubleshooting

### Lambda Timeout
If reports take too long, increase timeout:
```bash
aws lambda update-function-configuration \
    --function-name CostReportGenerator \
    --timeout 600 \
    --region ap-south-1
```

### CORS Issues
Verify API Gateway CORS configuration allows your S3 origin.

### Cost Explorer Access
Ensure the IAM role has `ce:GetCostAndUsage` permission.

### Check Lambda Logs
```bash
aws logs tail /aws/lambda/CostReportGenerator --follow --region ap-south-1
```

---

## Cost Considerations

**Monthly costs (within free tier):**
- Lambda: FREE (1M requests/month)
- S3: FREE (5GB storage, 20K GET requests)
- API Gateway: FREE (first 12 months, 1M requests)
- Cost Explorer API: First 1,000 requests FREE, then $0.01/request

**Estimated cost after free tier:**
- ~$0.02-$0.06 per report (depending on months selected)
- Minimal S3/Lambda costs for low usage

---

## Support

For issues or questions:
1. Check Lambda logs: `aws logs tail /aws/lambda/CostReportGenerator --region ap-south-1`
2. Verify IAM permissions
3. Ensure Cost Explorer is enabled in your account
4. Check API Gateway endpoint is correct in frontend

---

## Architecture

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │ HTTPS
       ▼
┌─────────────┐
│  S3 Static  │
│   Website   │
└──────┬──────┘
       │ POST
       ▼
┌─────────────┐
│ API Gateway │
└──────┬──────┘
       │ Invoke
       ▼
┌─────────────┐      ┌──────────────┐
│   Lambda    │─────▶│ Cost Explorer│
│  Function   │      │     API      │
└─────────────┘      └──────────────┘
       │
       ▼
   Excel Report
```
