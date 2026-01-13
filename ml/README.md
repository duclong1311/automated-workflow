# PhoBERT Task Parser - Training Guide

## Setup

1. **Install dependencies**:
```bash
cd /home/anhld/teams-jira-ai
pip install -r ml/requirements.txt
```

2. **Generate synthetic training data** (nếu chưa có real data):
```bash
python ml/generate_data.py --num 500
```

Hoặc collect real data từ Gemini API (khuyến nghị để có data tốt hơn).

## Collect Real Data

Để collect data từ Gemini API responses, thêm vào `handlers/teams_handler.py`:

```python
from ml.data_collector import DataCollector

collector = DataCollector()

# Trong ask_gemini_to_parse_task, sau khi có result:
collector.add_sample(text, result)
```

## Training

1. **Check dataset statistics**:
```bash
python ml/data_collector.py
```

2. **Train model**:
```bash
# Basic training
python ml/train.py

# Custom parameters
python ml/train.py --epochs 20 --batch-size 16 --lr 3e-5
```

Training sẽ mất khoảng:
- **CPU**: 2-3 giờ (10 epochs)
- **GPU**: 15-30 phút (10 epochs)

3. **Monitor progress**:
- Train loss, validation loss
- Issue type accuracy
- Priority accuracy

## Usage

Sau khi training xong, model tự động được sử dụng trong `ask_gemini_to_parse_task()`:
- Ưu tiên dùng ML model
- Fallback to Gemini nếu model fail

## Model Files

- `ml/models/task_parser/model.pt`: Trained weights
- `ml/data/training_data.jsonl`: Training dataset

## Performance Expectations

- **Accuracy**: 85-95% (phụ thuộc vào dataset)
- **Speed**: ~50ms inference (CPU), ~10ms (GPU)
- **Model size**: ~500MB

## Continuous Improvement

1. Collect thêm data từ production
2. Retrain định kỳ với data mới
3. Fine-tune parameters dựa trên metrics

## Troubleshooting

### Out of Memory
- Giảm `batch_size`
- Dùng `max_length=256` thay vì 512

### Low Accuracy
- Cần thêm training data
- Tăng số epochs
- Check data quality

### Slow Training
- Dùng GPU nếu có
- Giảm `max_length`
- Dùng smaller batch size
