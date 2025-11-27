# AWS Cost Comparison Report Generator

Web application to generate Excel cost comparison reports for AWS accounts.

## Features

- Compare 2-6 months of AWS costs
- Excel reports with color-coded headers and detailed breakdowns
- Two authentication methods:
  - IAM Role (for cross-account access)
  - AWS Credentials (direct access)
- Excludes tax from cost calculations
- Uses AWS Cost Explorer API

## Architecture

- **Frontend**: Static HTML/JS hosted on S3
- **Backend**: Lambda function with Cost Explorer integration
- **API**: API Gateway HTTP API
- **Output**: Excel (.xlsx) files with formatted cost comparisons

## Deployment

### Prerequisites

- AWS CLI configured
- Permissions to create CloudFormation stacks, Lambda, S3, API Gateway, IAM roles

### Deploy Main Stack

```bash
cd aws-cost-report
./deploy.sh
```

This will:
1. Create S3 bucket for frontend
2. Deploy Lambda function
3. Create API Gateway
4. Upload frontend to S3

### For Cross-Account Access

Deploy the read-only role in target accounts:

```bash
aws cloudformation deploy \
    --template-file target-account-role.yaml \
    --stack-name cost-report-readonly-role \
    --parameter-overrides TrustedAccountId=<LAMBDA_ACCOUNT_ID> \
    --capabilities CAPABILITY_NAMED_IAM \
    --region us-east-1
```

## Usage

1. Open the frontend URL (from deployment output)
2. Select 2-6 months to compare
3. Choose authentication method:
   - **IAM Role**: Lambda assumes role in target account
   - **Credentials**: Enter AWS access keys
4. Click "Generate Report"
5. Download the Excel file

## Excel Report Format

- **Column A**: Service names
- **Columns B-G**: Monthly costs (up to 6 months)
- **Column H**: Service total
- **Column I**: Detailed comparison text
- **Column J**: Reason for cost changes

Headers are yellow with bold text, matching the reference format.

## IAM Permissions

### Lambda Execution Role
- `ce:GetCostAndUsage`
- `ce:GetCostForecast`
- `sts:AssumeRole` (for cross-account)

### Target Account Role (Optional)
- `ce:GetCostAndUsage` (read-only)

## Cost Considerations

- Lambda: ~$0.20 per 1000 requests
- API Gateway: ~$1 per million requests
- S3: Minimal (static hosting)
- Cost Explorer API: First 1000 requests free, then $0.01 per request

## Troubleshooting

- **CORS errors**: Check API Gateway CORS configuration
- **Authentication errors**: Verify IAM role trust relationships
- **No data**: Ensure Cost Explorer is enabled in target account
- **Timeout**: Increase Lambda timeout for large date ranges
