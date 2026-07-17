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

## Local Development on WSL

This section provides step-by-step instructions for setting up and running the project locally on Windows Subsystem for Linux (WSL).

### Prerequisites

#### 1. Install WSL 2

If you haven't installed WSL yet, open PowerShell as Administrator and run:

```powershell
wsl --install
```

This installs WSL 2 with Ubuntu by default. After installation, restart your computer.

#### 2. Update Ubuntu Packages

Open your WSL terminal (Ubuntu) and update packages:

```bash
sudo apt update && sudo apt upgrade -y
```

#### 3. Install Python 3.11+

Install Python 3.11 and required tools:

```bash
sudo apt install -y python3.11 python3.11-venv python3-pip
```

Verify the installation:

```bash
python3.11 --version
```

#### 4. Install AWS CLI

Install AWS CLI v2:

```bash
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
sudo apt install -y unzip
unzip awscliv2.zip
sudo ./aws/install
rm -rf awscliv2.zip aws
```

Verify the installation:

```bash
aws --version
```

#### 5. Configure AWS Credentials

Set up your AWS credentials:

```bash
aws configure
```

Enter your:
- AWS Access Key ID
- AWS Secret Access Key
- Default region (e.g., `ap-south-1`)
- Default output format (e.g., `json`)

### Clone the Repository

```bash
git clone https://github.com/Musheer360/aws-cost-report.git
cd aws-cost-report
```

### Setting Up the Lambda Function Locally

#### 1. Create a Virtual Environment

```bash
cd lambda
python3.11 -m venv venv
source venv/bin/activate
```

#### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

#### 3. Test the Lambda Function Locally

You can test the Lambda function locally by creating a test script in the `lambda` directory:

```bash
cat > test_local.py << 'EOF'
import os
import json
from lambda_function import lambda_handler

# Use environment variables for credentials (never hardcode!)
# These are read from your AWS CLI configuration or environment
test_event = {
    "body": json.dumps({
        "budget_amount": 1000,
        "previous_month": "2024-01",
        "current_month": "2024-02",
        "use_role": False,
        "access_key_id": os.environ.get("AWS_ACCESS_KEY_ID", ""),
        "secret_access_key": os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    })
}

# Run the handler
response = lambda_handler(test_event, None)
print(f"Status Code: {response['statusCode']}")
EOF

# Set credentials from your AWS CLI configuration
export AWS_ACCESS_KEY_ID=$(aws configure get aws_access_key_id)
export AWS_SECRET_ACCESS_KEY=$(aws configure get aws_secret_access_key)

python test_local.py
```

**⚠️ Security Warning:** Never commit actual AWS credentials to version control. The example above uses environment variables which are read from your AWS CLI configuration. Always use environment variables or IAM roles instead of hardcoding credentials.

### Serving the Frontend Locally

#### 1. Install a Simple HTTP Server

Python includes a built-in HTTP server:

```bash
cd ../frontend
```

#### 2. Update the API Endpoint (Optional)

If you want to test against a deployed API, edit `index.html` and replace:

```javascript
const API_ENDPOINT = 'PLACEHOLDER_API_ENDPOINT';
```

With your actual API Gateway endpoint URL.

#### 3. Start the Local Server

```bash
python3 -m http.server 8000
```

#### 4. Access the Frontend

Open your browser and navigate to:

```
http://localhost:8000
```

**Note:** If you're using WSL 2, you can access this from your Windows browser using the same URL.

### Full Local Testing Workflow

1. **Set up the Lambda environment:**
   ```bash
   cd lambda
   python3.11 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Serve the frontend:**
   ```bash
   cd ../frontend
   python3 -m http.server 8000
   ```

3. **Test from browser:**
   Open `http://localhost:8000` in your Windows browser.

### Deploying from WSL

Once you've tested locally, deploy to AWS:

```bash
cd /path/to/aws-cost-report
chmod +x deploy.sh
./deploy.sh
```

### Troubleshooting WSL Issues

| Issue | Solution |
|-------|----------|
| `python3.11: command not found` | Run `sudo apt install python3.11` |
| AWS CLI not found | Reinstall using the curl command above |
| Permission denied on `deploy.sh` | Run `chmod +x deploy.sh` |
| Cannot access localhost from Windows | Use `ip addr show eth0` to get WSL IP and access via that IP |
| pip install fails with SSL error | Run `sudo apt install ca-certificates` |
| Virtual environment not activating | Ensure you're in the correct directory and run `source venv/bin/activate` |

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
