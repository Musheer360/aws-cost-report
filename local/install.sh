#!/bin/bash
set -e

echo ""
echo "========================================"
echo "CostReports360 - Local Installation"
echo "========================================"
echo ""

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "✗ Python 3 is required but not installed."
    echo "  Please install Python 3.8 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✓ Found Python $PYTHON_VERSION"

# Check for pip
if ! command -v pip3 &> /dev/null && ! python3 -m pip --version &> /dev/null; then
    echo "✗ pip is required but not installed."
    echo "  Please install pip for Python 3."
    exit 1
fi
echo "✓ Found pip"

# Check for AWS CLI
if ! command -v aws &> /dev/null; then
    echo ""
    echo "⚠ AWS CLI is not installed."
    echo "  The tool requires AWS CLI to be configured with valid credentials."
    echo ""
    read -p "Do you want to continue anyway? (y/n): " continue_without_aws
    if [[ ! "$continue_without_aws" =~ ^[Yy]$ ]]; then
        echo ""
        echo "Please install AWS CLI first:"
        echo "  https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
        exit 1
    fi
else
    echo "✓ Found AWS CLI"
    
    # Check if AWS credentials are configured
    if aws sts get-caller-identity &> /dev/null; then
        ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
        echo "✓ AWS credentials configured (Account: $ACCOUNT_ID)"
    else
        echo ""
        echo "⚠ AWS credentials are not configured or invalid."
        echo "  Run 'aws configure' to set up your credentials."
        echo ""
    fi
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Create virtual environment (optional but recommended)
echo ""
read -p "Create a virtual environment? (recommended) (y/n): " create_venv

if [[ "$create_venv" =~ ^[Yy]$ ]]; then
    VENV_DIR="$SCRIPT_DIR/venv"
    
    if [ -d "$VENV_DIR" ]; then
        echo "Virtual environment already exists at $VENV_DIR"
        read -p "Remove and recreate? (y/n): " recreate_venv
        if [[ "$recreate_venv" =~ ^[Yy]$ ]]; then
            rm -rf "$VENV_DIR"
        fi
    fi
    
    if [ ! -d "$VENV_DIR" ]; then
        echo ""
        echo "▶ Creating virtual environment..."
        python3 -m venv "$VENV_DIR"
        echo "✓ Virtual environment created"
    fi
    
    echo "▶ Activating virtual environment..."
    source "$VENV_DIR/bin/activate"
    echo "✓ Virtual environment activated"
    
    PIP_CMD="pip"
else
    PIP_CMD="pip3"
fi

# Install dependencies
echo ""
echo "▶ Installing Python dependencies..."
$PIP_CMD install -r "$SCRIPT_DIR/requirements.txt" -q
echo "✓ Dependencies installed"

# Make CLI script executable
chmod +x "$SCRIPT_DIR/cost_report_cli.py"

# Create convenience wrapper script
WRAPPER_SCRIPT="$SCRIPT_DIR/costreport"
create_wrapper() {
    local use_venv=$1
    local wrapper_path=$2
    
    echo '#!/bin/bash' > "$wrapper_path"
    echo 'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"' >> "$wrapper_path"
    
    if [[ "$use_venv" == "true" ]]; then
        echo 'source "$SCRIPT_DIR/venv/bin/activate"' >> "$wrapper_path"
    fi
    
    echo 'python3 "$SCRIPT_DIR/cost_report_cli.py" "$@"' >> "$wrapper_path"
}

if [[ "$create_venv" =~ ^[Yy]$ ]]; then
    create_wrapper "true" "$WRAPPER_SCRIPT"
else
    create_wrapper "false" "$WRAPPER_SCRIPT"
fi
chmod +x "$WRAPPER_SCRIPT"
echo "✓ Created convenience wrapper: $WRAPPER_SCRIPT"

# Add to PATH suggestion
echo ""
echo "========================================"
echo "✓ Installation Complete!"
echo "========================================"
echo ""
echo "Usage:"
echo "  $WRAPPER_SCRIPT --client \"Client Name\" --months 2024-10 2024-11 2024-12"
echo ""
echo "Or run directly:"
if [[ "$create_venv" =~ ^[Yy]$ ]]; then
    echo "  source $VENV_DIR/bin/activate"
fi
echo "  python3 $SCRIPT_DIR/cost_report_cli.py --help"
echo ""
echo "To add to PATH (optional):"
echo "  echo 'export PATH=\"\$PATH:$SCRIPT_DIR\"' >> ~/.bashrc"
echo "  source ~/.bashrc"
echo ""
echo "Prerequisites:"
echo "  1. AWS CLI configured with credentials: aws configure"
echo "  2. IAM permissions: ce:GetCostAndUsage, ce:GetCostForecast"
echo "  3. Cost Explorer enabled in your AWS account"
echo ""
