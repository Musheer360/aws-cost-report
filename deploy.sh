#!/bin/bash
set -e

echo ""
echo "=========================================="
echo "   CostReports360 - Deployment Installer"
echo "=========================================="
echo ""
echo "Choose deployment mode:"
echo ""
echo "  1) AWS Cloud Deployment"
echo "     - Deploys Lambda, API Gateway, S3 frontend"
echo "     - Supports cross-account IAM roles"
echo "     - Supports AWS credentials authentication"
echo "     - Requires AWS account with admin permissions"
echo ""
echo "  2) Local Installation (Linux/WSL)"
echo "     - Runs locally on your machine"
echo "     - Uses AWS CLI credentials only"
echo "     - No AWS infrastructure needed"
echo "     - No cross-account role support"
echo ""
read -p "Select deployment mode (1 or 2): " DEPLOY_MODE

case $DEPLOY_MODE in
    1)
        echo ""
        echo "=== AWS Cloud Deployment Selected ==="
        ;;
    2)
        echo ""
        echo "=== Local Installation Selected ==="
        echo ""
        
        # Get the script directory
        SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        
        # Run local installer
        if [ -f "$SCRIPT_DIR/local/install.sh" ]; then
            bash "$SCRIPT_DIR/local/install.sh"
        else
            echo "Error: local/install.sh not found"
            exit 1
        fi
        exit 0
        ;;
    *)
        echo "Invalid option. Please run again and select 1 or 2."
        exit 1
        ;;
esac

# Variables
STACK_NAME="costreports360"
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
pip install -r requirements.txt -t . > /dev/null 2>&1
zip -r ../lambda.zip . -x "*.pyc" -x "__pycache__/*" > /dev/null 2>&1
cd ..

# Step 3: Deploy Lambda code
echo "Deploying Lambda function..."
aws lambda update-function-code \
    --function-name $LAMBDA_NAME \
    --zip-file fileb://lambda.zip \
    --region $REGION \
    --no-cli-pager > /dev/null

# Step 4: Update frontend with API endpoint and Account ID
echo "Updating frontend with API endpoint and Account ID..."
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
LAMBDA_ROLE_NAME="CostReports360LambdaExecutionRole"

# Update frontend HTML
sed -i "s|PLACEHOLDER_API_ENDPOINT|$API_ENDPOINT|g" frontend/index.html
sed -i "s|ACCOUNT_ID_PLACEHOLDER|$ACCOUNT_ID|g" frontend/index.html

# Update role template with Lambda role name
cp target-account-role.yaml frontend/target-account-role.yaml
sed -i "s|LAMBDA_ROLE_NAME_PLACEHOLDER|$LAMBDA_ROLE_NAME|g" frontend/target-account-role.yaml

# Step 5: Upload frontend to S3
echo "Uploading frontend to S3..."
aws s3 cp frontend/index.html s3://$BUCKET_NAME/ --region $REGION
aws s3 cp frontend/target-account-role.yaml s3://$BUCKET_NAME/ --region $REGION

# Cleanup
rm lambda.zip

echo ""
echo "=== Deployment Complete ==="
echo "Frontend URL: http://$BUCKET_NAME.s3-website.$REGION.amazonaws.com"
echo "API Endpoint: $API_ENDPOINT"
echo "Your Account ID: $ACCOUNT_ID"
echo ""
echo "For cross-account access, clients can download the CloudFormation template from the frontend."
