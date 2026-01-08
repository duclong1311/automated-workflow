#!/bin/bash
# Setup script cho Teams Jira AI Bot v2.0

echo "=========================================="
echo "Teams Jira AI Bot v2.0 - Setup"
echo "=========================================="

# Check Python
echo ""
echo "📌 Checking Python..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo "✅ $PYTHON_VERSION"
else
    echo "❌ Python3 not found. Please install Python 3.8+"
    exit 1
fi

# Check pip
echo ""
echo "📌 Checking pip..."
if command -v pip3 &> /dev/null; then
    echo "✅ pip3 found"
    PIP_CMD="pip3"
elif command -v pip &> /dev/null; then
    echo "✅ pip found"
    PIP_CMD="pip"
else
    echo "⚠️  pip not found. Installing pip..."
    sudo apt update
    sudo apt install -y python3-pip
    PIP_CMD="pip3"
fi

# Create virtual environment (recommended)
echo ""
echo "📌 Setting up virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "ℹ️  Virtual environment already exists"
fi

# Activate venv
echo "📌 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo ""
echo "📌 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✅ Dependencies installed successfully"
else
    echo "❌ Failed to install dependencies"
    exit 1
fi

# Check .env
echo ""
echo "📌 Checking .env file..."
if [ -f ".env" ]; then
    echo "✅ .env file exists"
    
    # Check required vars
    if grep -q "JIRA_SERVER=" .env && \
       grep -q "JIRA_API_TOKEN=" .env && \
       grep -q "JIRA_PROJECT_KEY=" .env && \
       grep -q "GEMINI_API_KEY=" .env; then
        echo "✅ All required environment variables found"
    else
        echo "⚠️  Some environment variables missing in .env"
        echo "   Please check: JIRA_SERVER, JIRA_API_TOKEN, JIRA_PROJECT_KEY, GEMINI_API_KEY"
    fi
else
    echo "⚠️  .env file not found"
    echo "   Creating .env template..."
    cat > .env << EOF
JIRA_SERVER=https://your-domain.atlassian.net
JIRA_API_TOKEN=your_jira_api_token
JIRA_PROJECT_KEY=PROJ
GEMINI_API_KEY=your_gemini_api_key
EOF
    echo "✅ .env template created. Please edit it with your credentials."
fi

# Test imports
echo ""
echo "📌 Testing imports..."
python3 test_samples.py

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✅ Setup completed successfully!"
    echo "=========================================="
    echo ""
    echo "Next steps:"
    echo "1. Edit .env file with your credentials"
    echo "2. Run: source venv/bin/activate"
    echo "3. Run: python3 main_new.py"
    echo ""
else
    echo ""
    echo "⚠️  Setup completed with warnings"
    echo "   Please check the errors above"
fi
