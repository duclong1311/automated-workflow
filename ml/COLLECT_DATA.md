"""
Script để collect real data từ Gemini API responses
Thêm vào handlers/teams_handler.py để collect training data
"""

# Add to handlers/teams_handler.py after imports:
from ml.data_collector import DataCollector

# Initialize collector (add after jira_service initialization):
try:
    data_collector = DataCollector()
except Exception as e:
    logger.warning(f"⚠️ Could not initialize data collector: {e}")
    data_collector = None

# In ask_gemini_to_parse_task function, after getting result from Gemini:
# Add this code BEFORE returning result:
"""
if data_collector and result:
    try:
        data_collector.add_sample(text, result)
        logger.debug("✅ Saved sample to training data")
    except Exception as e:
        logger.debug(f"⚠️ Could not save sample: {e}")
"""

# After collecting ~100-200 real samples, retrain:
# python3 ml/train.py --epochs 10 --batch-size 4
