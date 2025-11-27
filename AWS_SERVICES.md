# AWS Services Used - Cost Report Generator

## Overview

This application uses **6 AWS services** deployed in the **ap-south-1 (Mumbai)** region. All services are serverless and scale automatically.

---

## Services Breakdown

### 1. Amazon S3 (Simple Storage Service)

**Resource Created:**
- Bucket Name: `cost-report-frontend-162290422654`
- Type: Static Website Hosting

**Purpose:**
- Hosts the frontend HTML/JavaScript application
- Serves the web interface to users

**Configuration:**
- Public read access enabled
- Website hosting enabled with `index.html` as index document
- Bucket policy allows public GetObject access

**Cost:**
- FREE tier: 5 GB storage, 20,000 GET requests/month
- Actual usage: ~12 KB (negligible)

**Access:**
- URL: `http://cost-report-frontend-162290422654.s3-website.ap-south-1.amazonaws.com`

---

### 2. AWS Lambda

**Resource Created:**
- Function Name: `CostReportGenerator`
- Runtime: Python 3.11
- Handler: `lambda_function.lambda_handler`

**Purpose:**
- Backend processing engine
- Fetches cost data from Cost Explorer API
- Generates Excel reports with multiple sheets
- Returns base64-encoded Excel file to frontend

**Configuration:**
- Memory: 512 MB
- Timeout: 300 seconds (5 minutes)
- Code Size: ~30 MB (includes dependencies)
- Environment: Python 3.11 with boto3, openpyxl

**Dependencies:**
- boto3 (AWS SDK)
- openpyxl (Excel generation)

**Cost:**
- FREE tier: 1 million requests/month, 400,000 GB-seconds compute
- Estimated: ~800 free reports/month
- After free tier: ~$0.0002 per invocation

---

### 3. Amazon API Gateway

**Resource Created:**
- API Name: `CostReportAPI`
- Type: HTTP API (v2)
- API ID: `j2y2zt3ak6`

**Purpose:**
- Provides REST endpoint for frontend-backend communication
- Routes POST requests to Lambda function
- Handles CORS for cross-origin requests

**Configuration:**
- Protocol: HTTPS
- Stage: `prod` (auto-deploy enabled)
- Route: `POST /generate`
- Integration: AWS_PROXY to Lambda
- CORS: Allows all origins, POST method

**Endpoint:**
- `https://j2y2zt3ak6.execute-api.ap-south-1.amazonaws.com/prod/generate`

**Cost:**
- FREE tier: 1 million requests/month (first 12 months)
- After free tier: $1.00 per million requests

---

### 4. AWS IAM (Identity and Access Management)

**Resources Created:**
- Role Name: `cost-report-generator-LambdaExecutionRole-*`
- Type: Lambda execution role

**Purpose:**
- Grants Lambda function permissions to:
  - Access Cost Explorer API
  - Write logs to CloudWatch
  - Execute within AWS environment

**Policies Attached:**
1. **AWSLambdaBasicExecutionRole** (AWS Managed)
   - CloudWatch Logs: CreateLogGroup, CreateLogStream, PutLogEvents

2. **CostExplorerAccess** (Inline Policy)
   ```json
   {
     "Effect": "Allow",
     "Action": [
       "ce:GetCostAndUsage",
       "ce:GetCostForecast"
     ],
     "Resource": "*"
   }
   ```

**Trust Relationship:**
- Allows Lambda service to assume this role

**Cost:**
- FREE (no charge for IAM)

---

### 5. Amazon CloudWatch Logs

**Resource Created:**
- Log Group: `/aws/lambda/CostReportGenerator`
- Retention: Default (never expire)

**Purpose:**
- Stores Lambda execution logs
- Captures errors, warnings, and debug information
- Used for troubleshooting and monitoring

**Log Contents:**
- Function start/end events
- Execution duration and memory usage
- Error stack traces
- Custom log messages

**Cost:**
- FREE tier: 5 GB ingestion, 5 GB storage/month
- Actual usage: ~10-50 MB/month (negligible)

**Access:**
```bash
aws logs tail /aws/lambda/CostReportGenerator --follow --region ap-south-1
```

---

### 6. AWS Cost Explorer API

**Service Used:**
- API: Cost Explorer
- Operations: `GetCostAndUsage`

**Purpose:**
- Provides detailed cost and usage data
- Returns costs grouped by:
  - Service
  - Usage Type
  - Region
- Excludes tax records
- Uses `NetUnblendedCost` metric (includes discounts/credits)

**Data Retrieved:**
- Monthly cost breakdowns
- Usage quantities
- Service-level details
- Regional cost distribution

**Cost:**
- FREE tier: First 1,000 API requests/month
- After free tier: $0.01 per request
- Each report generation = 2-12 API calls (depending on months selected)

**Example:**
- 2 months comparison = 2 API calls
- 6 months comparison = 6 API calls

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────┐
│                         User                              │
└────────────────────────┬─────────────────────────────────┘
                         │ HTTPS
                         ▼
┌──────────────────────────────────────────────────────────┐
│  Amazon S3 - Static Website Hosting                      │
│  • Bucket: cost-report-frontend-162290422654             │
│  • Content: index.html (Frontend UI)                     │
└────────────────────────┬─────────────────────────────────┘
                         │ POST /generate
                         ▼
┌──────────────────────────────────────────────────────────┐
│  Amazon API Gateway (HTTP API)                           │
│  • Endpoint: j2y2zt3ak6.execute-api.ap-south-1          │
│  • CORS enabled                                          │
└────────────────────────┬─────────────────────────────────┘
                         │ Invoke
                         ▼
┌──────────────────────────────────────────────────────────┐
│  AWS Lambda - CostReportGenerator                        │
│  • Runtime: Python 3.11                                  │
│  • Memory: 512 MB                                        │
│  • Timeout: 300s                                         │
│  • Dependencies: boto3, openpyxl                         │
└────────┬────────────────────────┬────────────────────────┘
         │                        │
         │ Logs                   │ API Calls
         ▼                        ▼
┌─────────────────┐    ┌──────────────────────────────────┐
│ CloudWatch Logs │    │  AWS Cost Explorer API           │
│ • Log Group     │    │  • GetCostAndUsage               │
│ • Debugging     │    │  • NetUnblendedCost metric       │
└─────────────────┘    │  • Service/Region/Usage grouping │
                       └──────────────────────────────────┘
         │
         │ IAM Role
         ▼
┌──────────────────────────────────────────────────────────┐
│  AWS IAM - Lambda Execution Role                         │
│  • Cost Explorer permissions                             │
│  • CloudWatch Logs permissions                           │
└──────────────────────────────────────────────────────────┘
```

---

## Cost Summary

### Free Tier Eligible

| Service | Free Tier | Estimated Usage | Cost |
|---------|-----------|-----------------|------|
| S3 | 5 GB storage, 20K requests | ~12 KB, <100 requests | $0 |
| Lambda | 1M requests, 400K GB-sec | ~100 requests/month | $0 |
| API Gateway | 1M requests (12 months) | ~100 requests/month | $0 |
| CloudWatch Logs | 5 GB ingestion/storage | ~50 MB/month | $0 |
| Cost Explorer | 1,000 requests/month | ~200 requests/month | $0 |
| IAM | Always free | N/A | $0 |

### After Free Tier

| Service | Cost per Unit | Estimated Monthly |
|---------|---------------|-------------------|
| Lambda | $0.0002/request | $0.02 (100 reports) |
| Cost Explorer | $0.01/request | $2.00 (200 reports) |
| API Gateway | $1/million requests | $0.0001 (100 reports) |
| **Total** | | **~$2.02/month** |

**Note:** Costs are negligible for typical usage (10-50 reports/month).

---

## Security Considerations

### Public Access
- **S3 Bucket**: Public read access (required for static website)
- **API Gateway**: Public endpoint (no authentication)

### Credentials
- User AWS credentials are:
  - Sent via HTTPS to API Gateway
  - Used only within Lambda execution
  - Never stored or logged
  - Discarded after report generation

### IAM Permissions
- Lambda role has minimal permissions:
  - Read-only Cost Explorer access
  - CloudWatch Logs write access
  - No access to other AWS resources

### Recommendations
- Use IAM users with Cost Explorer read-only permissions
- Rotate credentials regularly
- Monitor CloudWatch Logs for unusual activity
- Consider adding API Gateway authentication for production

---

## Monitoring & Troubleshooting

### Check Lambda Logs
```bash
aws logs tail /aws/lambda/CostReportGenerator --follow --region ap-south-1
```

### View Recent Executions
```bash
aws lambda list-functions --region ap-south-1 --query 'Functions[?FunctionName==`CostReportGenerator`]'
```

### Check API Gateway Metrics
```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApiGateway \
  --metric-name Count \
  --dimensions Name=ApiId,Value=j2y2zt3ak6 \
  --start-time 2025-11-26T00:00:00Z \
  --end-time 2025-11-26T23:59:59Z \
  --period 3600 \
  --statistics Sum \
  --region ap-south-1
```

### Monitor Costs
```bash
aws ce get-cost-and-usage \
  --time-period Start=2025-11-01,End=2025-11-30 \
  --granularity MONTHLY \
  --metrics UnblendedCost \
  --filter file://filter.json
```

---

## Resource Identifiers

| Resource Type | Name/ID | ARN/URL |
|---------------|---------|---------|
| S3 Bucket | cost-report-frontend-162290422654 | arn:aws:s3:::cost-report-frontend-162290422654 |
| Lambda Function | CostReportGenerator | arn:aws:lambda:ap-south-1:162290422654:function:CostReportGenerator |
| API Gateway | j2y2zt3ak6 | https://j2y2zt3ak6.execute-api.ap-south-1.amazonaws.com |
| IAM Role | cost-report-generator-LambdaExecutionRole-* | arn:aws:iam::162290422654:role/... |
| CloudWatch Log Group | /aws/lambda/CostReportGenerator | arn:aws:logs:ap-south-1:162290422654:log-group:/aws/lambda/CostReportGenerator |

**Account ID:** 162290422654  
**Region:** ap-south-1 (Mumbai)

---

## Cleanup Instructions

To remove all resources and stop incurring costs:

```bash
# Delete CloudFormation stack (if used)
aws cloudformation delete-stack --stack-name cost-report-generator --region ap-south-1

# Or manually delete:
# 1. Empty and delete S3 bucket
aws s3 rm s3://cost-report-frontend-162290422654 --recursive
aws s3 rb s3://cost-report-frontend-162290422654

# 2. Delete Lambda function
aws lambda delete-function --function-name CostReportGenerator --region ap-south-1

# 3. Delete API Gateway
aws apigatewayv2 delete-api --api-id j2y2zt3ak6 --region ap-south-1

# 4. Delete CloudWatch Logs (optional)
aws logs delete-log-group --log-group-name /aws/lambda/CostReportGenerator --region ap-south-1

# 5. Delete IAM role (get exact name first)
aws iam list-roles --query 'Roles[?contains(RoleName, `cost-report`)].RoleName'
# Then delete policies and role
```

---

## Support & Documentation

- **Deployment Guide**: See `DEPLOYMENT.md`
- **Application README**: See `README.md`
- **AWS Documentation**:
  - [Cost Explorer API](https://docs.aws.amazon.com/cost-management/latest/APIReference/API_GetCostAndUsage.html)
  - [Lambda](https://docs.aws.amazon.com/lambda/)
  - [API Gateway](https://docs.aws.amazon.com/apigateway/)
  - [S3 Static Website](https://docs.aws.amazon.com/AmazonS3/latest/userguide/WebsiteHosting.html)
