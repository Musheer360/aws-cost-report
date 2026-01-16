# ExamOnline Budget Breach Analysis Tool

A specialized AWS cost analysis tool that generates comprehensive Word document reports when budget thresholds are exceeded. Designed specifically for ExamOnline to analyze cost increases, identify root causes, and provide actionable recommendations.

## Purpose

This tool is designed to be run **24 hours after** receiving an AWS budget breach notification. The delay allows AWS Cost Explorer data to fully populate, ensuring accurate analysis.

The generated Word report includes:
- **Executive Summary** with key metrics and budget status
- **Cost Drivers Analysis** identifying primary contributors to cost increases
- **Detailed Service Analysis** with usage type breakdowns
- **Regional Cost Analysis** showing geographic cost distribution
- **Recommendations** for immediate, short-term, and long-term optimizations
- **Appendix** with complete cost increase data

## Features

- 📊 **Word Document Output**: Professionally formatted .docx reports
- 🔍 **Focused Analysis**: Only shows services with cost increases
- 📈 **Root Cause Identification**: Detailed breakdown of cost drivers
- 💡 **Actionable Recommendations**: Specific steps to reduce costs
- 🔐 **Flexible Authentication**: IAM Role or AWS Credentials
- 🌍 **Regional Insights**: Cost distribution across AWS regions

## Architecture

- **Frontend**: Static HTML/JS hosted on S3
- **Backend**: Lambda function with Cost Explorer integration
- **API**: API Gateway HTTP API
- **Output**: Word (.docx) documents with formatted analysis

## Deployment

### Prerequisites

- AWS CLI configured
- Permissions to create CloudFormation stacks, Lambda, S3, API Gateway, IAM roles

### Deploy Main Stack

```bash
cd examonline-budget-breach-analysis
./deploy.sh
```

This will:
1. Create S3 bucket for frontend
2. Deploy Lambda function with python-docx
3. Create API Gateway
4. Upload frontend to S3

### For Cross-Account Access

Deploy the read-only role in the target account:

```bash
aws cloudformation deploy \
    --template-file target-account-role.yaml \
    --stack-name examonline-cost-analysis-role \
    --parameter-overrides TrustedAccountId=<LAMBDA_ACCOUNT_ID> \
    --capabilities CAPABILITY_NAMED_IAM \
    --region us-east-1
```

## Usage

### When to Use

1. Receive AWS Budget breach notification via email/SNS
2. **Wait 24 hours** for Cost Explorer data to populate
3. Open the ExamOnline Budget Breach Analysis tool
4. Enter the budget amount and breach date
5. Select the analysis period (previous month vs current month)
6. Authenticate and generate the report
7. Download and review the Word document
8. Share with stakeholders as needed

### Input Parameters

| Parameter | Description |
|-----------|-------------|
| Budget Amount | The budget threshold that was exceeded (USD) |
| Breach Date | Date when the budget breach occurred |
| Previous Month | Baseline month for comparison |
| Current Month | Month when budget was exceeded |
| AWS Credentials | Access Key ID and Secret Key, OR |
| IAM Role ARN | Cross-account role for Cost Explorer access |

## Report Structure

### 1. Cover Page
- ExamOnline branding
- Analysis period
- Budget threshold
- Confidential marking

### 2. Table of Contents
- Quick navigation to all sections

### 3. Executive Summary
- Key financial metrics table
- Budget status (exceeded/within)
- Top 5 cost increase drivers

### 4. Cost Drivers Analysis
- Contribution breakdown by service
- Impact level ratings (Critical/High/Medium/Low)
- Root cause analysis for top drivers

### 5. Detailed Service Analysis
- Per-service cost breakdowns
- Usage type analysis
- Root cause explanations

### 6. Regional Analysis
- Cost increases by AWS region
- Geographic distribution of spend

### 7. Recommendations
- Immediate actions (this week)
- Short-term optimizations (1-2 weeks)
- Long-term strategy

### 8. Appendix
- Complete data table of all cost increases

## IAM Permissions

### Lambda Execution Role
- `ce:GetCostAndUsage`
- `ce:GetCostForecast`
- `sts:AssumeRole` (for cross-account)

### Target Account Role (Optional)
- `ce:GetCostAndUsage`
- `ce:GetCostForecast`

## Dependencies

- boto3==1.34.0
- python-docx==1.1.0

## Cost Considerations

- Lambda: ~$0.20 per 1000 requests
- API Gateway: ~$1 per million requests
- S3: Minimal (static hosting)
- Cost Explorer API: First 1000 requests free, then $0.01 per request

## Troubleshooting

| Issue | Solution |
|-------|----------|
| CORS errors | Check API Gateway CORS configuration |
| Authentication errors | Verify IAM role trust relationships |
| No data returned | Ensure Cost Explorer is enabled in target account |
| Timeout | Increase Lambda timeout for large date ranges |
| Empty report | Verify dates have cost data; try different months |

## Security Notes

- Never store AWS credentials in the browser
- Use IAM roles with least-privilege permissions
- The tool only has read-only access to Cost Explorer
- No data is stored server-side after report generation

## Support

For issues or questions regarding this tool, contact your system administrator.

---

*ExamOnline Budget Breach Analysis Tool - Confidential*
