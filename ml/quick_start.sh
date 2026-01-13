#!/bin/bash
# Quick start script để train model

echo "🚀 PhoBERT Task Parser - Quick Start"
echo "======================================"

# Check if in venv
if [ -z "$VIRTUAL_ENV" ]; then
    echo "⚠️  Cảnh báo: Không trong virtual environment"
    echo "Khuyến nghị: source venv/bin/activate"
    read -p "Tiếp tục? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Install dependencies
echo "📦 Installing dependencies..."
pip install -q -r ml/requirements.txt

# Generate data if not exists
if [ ! -f "ml/data/training_data.jsonl" ]; then
    echo "📊 Generating synthetic training data..."
    python ml/generate_data.py --num 500
else
    echo "✅ Training data already exists"
    python ml/data_collector.py
fi

# Train model
echo ""
echo "🎯 Starting training..."
echo "This may take 15-30 minutes on GPU, 2-3 hours on CPU"
echo ""

python ml/train.py --epochs 10 --batch-size 8

echo ""
echo "✅ Training completed!"
echo ""
echo "Model saved to: ml/models/task_parser/model.pt"
echo "The model will be automatically used in the application."
echo ""
echo "To test: Restart the server and send a Teams message."
