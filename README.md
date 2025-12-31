# CostReports360

Web application to generate Excel cost comparison reports for AWS accounts.

## Features

- Compare 2-6 months of AWS costs
- Excel reports with color-coded headers and detailed breakdowns
- Three deployment modes:
  - **AWS Cloud**: Full-featured web application with Lambda, API Gateway, S3
  - **Local Web Server**: Full web interface running on localhost:5000
  - **Local CLI**: Command-line tool using AWS CLI credentials
- Three authentication methods:
  - IAM Role (for cross-account access)
  - AWS Credentials (direct access)
  - AWS CLI credentials (local modes)
- Excludes tax from cost calculations
- Uses AWS Cost Explorer API

## Deployment Options

### Option 1: AWS Cloud Deployment

Full-featured web application hosted on AWS.

**Features:**
- Web-based UI hosted on S3
- Cross-account IAM role support
- AWS credentials authentication
- Shareable frontend URL

**Requirements:**
- AWS CLI configured with admin permissions
- Ability to create CloudFormation stacks, Lambda, S3, API Gateway, IAM roles

### Option 2: Local Web Server (Recommended for Local Use)

Full web interface running locally on your Linux machine.

**Features:**
- Same web UI as AWS Cloud deployment
- Runs on http://localhost:5000
- Start/stop with simple commands
- Auto-start on system boot
- Enter AWS credentials directly in the web form

**Requirements:**
- Python 3.8+
- AWS credentials with IAM permissions: `ce:GetCostAndUsage`, `ce:GetCostForecast`

### Option 3: Local CLI Only

Command-line tool that runs locally on your machine.

**Features:**
- No web interface
- Uses AWS CLI credentials
- Generates same Excel reports as other modes
- Works on any Linux system or WSL

**Requirements:**
- Python 3.8+
- AWS CLI configured with valid credentials
- IAM permissions: `ce:GetCostAndUsage`, `ce:GetCostForecast`

## Quick Start

### Interactive Installer

Run the deploy script and choose your deployment mode:

```bash
./deploy.sh
```

The installer will prompt you to choose:
1. **AWS Cloud Deployment** - Full web application on AWS
2. **Local Installation** - Web server or CLI on your machine

### Direct Local Installation

For local installation only:

```bash
cd local
./install.sh
```

The installer will ask if you want:
1. **Web Server Mode** - Full web interface on localhost:5000
2. **CLI Only Mode** - Command-line tool only

### Direct AWS Deployment

For AWS deployment only (skip the menu):

```bash
# Set deployment to AWS mode
STACK_NAME="costreports360"
REGION="${AWS_REGION:-ap-south-1}"
./deploy.sh <<< "1"
```

## Local Web Server Usage

### Starting the Server

```bash
# Start the web server (runs in background, auto-starts on boot)
./local/serve-costapp
```

This will:
- Start the server on http://localhost:5000
- Run in the background
- Configure auto-start on system boot (via systemd)

### Stopping the Server

```bash
# Stop the web server and disable auto-start
./local/stop-costapp
```

This will:
- Stop the running server
- Disable auto-start on boot
- Clean up log files

### Server Management

| Command | Description |
|---------|-------------|
| `./local/serve-costapp` | Start server, enable auto-start |
| `./local/stop-costapp` | Stop server, disable auto-start |

### Web Interface

Once started, access the web interface at:
- **Frontend**: http://localhost:5000
- **API**: http://localhost:5000/api/generate

Enter your AWS credentials directly in the web form to generate reports. Credentials are used only for the request and are not stored.

## Local CLI Usage (Linux/WSL)

After local installation:

```bash
# Basic usage
./local/costreport --client "Client Name" --months 2024-10 2024-11 2024-12

# With specific AWS profile
./local/costreport --profile production --client "Client A" --months 2024-09 2024-10

# Save to specific directory
./local/costreport --client "Client B" --months 2024-11 2024-12 --output /path/to/reports

# Show help
./local/costreport --help
```

### Local CLI Options

| Option | Description |
|--------|-------------|
| `--client, -c` | Client name (used in report filename) |
| `--months, -m` | Months to compare (2-6, format: YYYY-MM) |
| `--profile, -p` | AWS CLI profile to use |
| `--region, -r` | AWS region (default: us-east-1) |
| `--output, -o` | Output directory (default: current directory) |

## AWS Cloud Architecture

- **Frontend**: Static HTML/JS hosted on S3
- **Backend**: Lambda function with Cost Explorer integration
- **API**: API Gateway HTTP API
- **Output**: Excel (.xlsx) files with formatted cost comparisons

### For Cross-Account Access (AWS Cloud only)

Deploy the read-only role in target accounts:

```bash
aws cloudformation deploy \
    --template-file target-account-role.yaml \
    --stack-name cost-report-readonly-role \
    --parameter-overrides TrustedAccountId=<LAMBDA_ACCOUNT_ID> \
    --capabilities CAPABILITY_NAMED_IAM \
    --region us-east-1
```

## AWS Cloud Usage

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

### For Local Installation
- `ce:GetCostAndUsage`
- `ce:GetCostForecast`

### Lambda Execution Role (AWS Cloud)
- `ce:GetCostAndUsage`
- `ce:GetCostForecast`
- `sts:AssumeRole` (for cross-account)

### Target Account Role (AWS Cloud, Optional)
- `ce:GetCostAndUsage` (read-only)

## Cost Considerations

### Local Installation
- **Free** - No AWS infrastructure costs
- Cost Explorer API: First 1000 requests free, then $0.01 per request

### AWS Cloud Deployment
- Lambda: ~$0.20 per 1000 requests
- API Gateway: ~$1 per million requests
- S3: Minimal (static hosting)
- Cost Explorer API: First 1000 requests free, then $0.01 per request

## Troubleshooting

### Local Web Server

- **"Server already running"**: Run `./local/stop-costapp` first, then start again
- **"Port 5000 in use"**: Set a different port: `PORT=8080 ./local/serve-costapp`
- **"systemd not available"**: Auto-start won't work, but server will still run

### Local CLI

- **"Authentication failed"**: Run `aws configure` to set up credentials
- **"Cost Explorer not enabled"**: Enable Cost Explorer in AWS Console (Billing → Cost Explorer)
- **"Access Denied"**: Ensure IAM user/role has `ce:GetCostAndUsage` permission

### AWS Cloud Deployment

- **CORS errors**: Check API Gateway CORS configuration
- **Authentication errors**: Verify IAM role trust relationships
- **No data**: Ensure Cost Explorer is enabled in target account
- **Timeout**: Increase Lambda timeout for large date ranges
