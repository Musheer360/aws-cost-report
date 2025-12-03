#!/bin/bash
set -e

echo "=== AWS Cost Report Generator Deployment ==="

# Variables
STACK_NAME="cost-report-generator"
REGION="${AWS_REGION:-ap-south-1}"

# Step 1: Deploy CloudFormation stack
echo "Deploying CloudFormation stack..."
aws cloudformation deploy \
    --template-file cloudformation.yaml \
    --stack-name $STACK_NAME \
    --capabilities CAPABILITY_NAMED_IAM \
    --region $REGION

# Get outputs
echo "Getting stack outputs..."
BUCKET_NAME=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`FrontendURL`].OutputValue' \
    --output text | sed 's|http://||' | sed 's|.s3-website.*||')

API_ENDPOINT=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
    --output text)

LAMBDA_NAME=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`LambdaFunctionName`].OutputValue' \
    --output text)

# Step 2: Package Lambda function
echo "Packaging Lambda function..."
cd lambda
pip install -r requirements.txt -t .
zip -r ../lambda.zip . -x "*.pyc" -x "__pycache__/*"
cd ..

# Step 3: Deploy Lambda code
echo "Deploying Lambda function..."
aws lambda update-function-code \
    --function-name $LAMBDA_NAME \
    --zip-file fileb://lambda.zip \
    --region $REGION

# Step 4: Update frontend with API endpoint
echo "Updating frontend with API endpoint..."
sed -i "s|PLACEHOLDER_API_ENDPOINT|$API_ENDPOINT|g" frontend/index.html

# Step 5: Upload frontend to S3
echo "Uploading frontend to S3..."
aws s3 cp frontend/index.html s3://$BUCKET_NAME/ --region $REGION

# Cleanup
rm lambda.zip

echo ""
echo "=== Deployment Complete ==="
echo "Frontend URL: http://$BUCKET_NAME.s3-website-$REGION.amazonaws.com"
echo "API Endpoint: $API_ENDPOINT"
echo ""
echo "To create a read-only role in target accounts, deploy target-account-role.yaml"
