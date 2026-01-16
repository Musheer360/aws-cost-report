# ExamOnline Budget Breach Analysis Tool - Deployment Guide

## Prerequisites

- AWS CLI configured with appropriate credentials
- Admin or sufficient IAM permissions to create:
  - Lambda functions
  - S3 buckets
  - API Gateway
  - IAM roles
- Python 3.11+ (for local testing)

---

## Quick Deployment (Recommended)

### Using the Deploy Script

```bash
cd examonline-budget-breach-analysis
./deploy.sh
```

This script will:
1. Deploy CloudFormation stack
2. Package Lambda function with python-docx dependency
3. Upload Lambda code
4. Upload frontend to S3
5. Output the application URL and API endpoint

**Outputs:**
- Application URL: `http://examonline-budget-analysis-{ACCOUNT_ID}.s3-website-{REGION}.amazonaws.com`
- API Endpoint: Automatically configured in frontend

---

## Manual Deployment

### Step 1: Deploy Infrastructure

```bash
aws cloudformation deploy \
    --template-file cloudformation.yaml \
    --stack-name examonline-budget-analysis \
    --capabilities CAPABILITY_NAMED_IAM \
    --region ap-south-1
```

### Step 2: Get Stack Outputs

```bash
aws cloudformation describe-stacks \
    --stack-name examonline-budget-analysis \
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
    --function-name ExamOnlineBudgetBreachAnalysis \
    --zip-file fileb://lambda.zip \
    --region ap-south-1
```

### Step 5: Update Frontend with API Endpoint

Edit `frontend/index.html` and replace:
```javascript
const API_ENDPOINT = 'PLACEHOLDER_API_ENDPOINT';
```

With your actual API Gateway endpoint from Step 2.

### Step 6: Upload Frontend to S3

```bash
BUCKET_NAME=$(aws cloudformation describe-stacks \
    --stack-name examonline-budget-analysis \
    --region ap-south-1 \
    --query 'Stacks[0].Outputs[?OutputKey==`FrontendURL`].OutputValue' \
    --output text | sed 's|http://||' | sed 's|.s3-website.*||')

aws s3 cp frontend/index.html s3://$BUCKET_NAME/ --region ap-south-1
aws s3 cp frontend/target-account-role.yaml s3://$BUCKET_NAME/ --region ap-south-1
```

---

## Cross-Account Setup

For analyzing costs in a different AWS account, deploy the IAM role in the target account:

### Option 1: CloudFormation (Recommended)

```bash
aws cloudformation deploy \
    --template-file target-account-role.yaml \
    --stack-name examonline-cost-analysis-role \
    --parameter-overrides TrustedAccountId=<LAMBDA_ACCOUNT_ID> \
    --capabilities CAPABILITY_NAMED_IAM \
    --region us-east-1
```

### Option 2: Download from Application

Users can download the CloudFormation template directly from the application UI.

---

## Updating the Application

### Update Lambda Code

```bash
cd lambda
pip install -r requirements.txt -t .
zip -r ../lambda.zip .
cd ..

aws lambda update-function-code \
    --function-name ExamOnlineBudgetBreachAnalysis \
    --zip-file fileb://lambda.zip \
    --region ap-south-1
```

### Update Frontend

```bash
aws s3 cp frontend/index.html s3://{BUCKET_NAME}/ --region ap-south-1
```

---

## Cleanup/Deletion

### Using CloudFormation

```bash
aws cloudformation delete-stack \
    --stack-name examonline-budget-analysis \
    --region ap-south-1
```

---

## Troubleshooting

### Lambda Timeout
If reports take too long, increase timeout:
```bash
aws lambda update-function-configuration \
    --function-name ExamOnlineBudgetBreachAnalysis \
    --timeout 600 \
    --region ap-south-1
```

### CORS Issues
Verify API Gateway CORS configuration allows your S3 origin.

### Cost Explorer Access
Ensure the IAM role has `ce:GetCostAndUsage` permission.

### Check Lambda Logs
```bash
aws logs tail /aws/lambda/ExamOnlineBudgetBreachAnalysis --follow --region ap-south-1
```

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
   Word Report
   (.docx)
```

---

## Cost Considerations

| Service | Free Tier | After Free Tier |
|---------|-----------|-----------------|
| Lambda | 1M requests/month | ~$0.0002/request |
| S3 | 5GB, 20K requests | Minimal |
| API Gateway | 1M requests (12 months) | $1/million |
| Cost Explorer | 1,000 requests/month | $0.01/request |

**Estimated monthly cost:** < $5 for typical usage (10-50 reports)
