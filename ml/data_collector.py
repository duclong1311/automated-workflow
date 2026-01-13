"""
Data collector để tạo training dataset từ Gemini API responses
Chạy script này để collect data từ messages Teams
"""
import json
import os
from datetime import datetime
from pathlib import Path

class DataCollector:
    def __init__(self, data_dir='ml/data'):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.dataset_file = self.data_dir / 'training_data.jsonl'
    
    def add_sample(self, message_text: str, parsed_result: dict):
        """
        Thêm một sample vào dataset
        
        Args:
            message_text: Raw message từ Teams
            parsed_result: Kết quả parse (summary, issuetype, description, priority, epic_link, assignee)
        """
        sample = {
            'timestamp': datetime.now().isoformat(),
            'input': message_text,
            'output': parsed_result
        }
        
        with open(self.dataset_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(sample, ensure_ascii=False) + '\n')
        
        print(f"✅ Đã thêm sample vào {self.dataset_file}")
    
    def load_dataset(self):
        """Load toàn bộ dataset"""
        if not self.dataset_file.exists():
            return []
        
        samples = []
        with open(self.dataset_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    samples.append(json.loads(line))
        
        return samples
    
    def get_statistics(self):
        """Thống kê dataset"""
        samples = self.load_dataset()
        
        stats = {
            'total_samples': len(samples),
            'issue_types': {},
            'has_assignee': 0,
            'has_epic_link': 0,
            'has_priority': 0
        }
        
        for sample in samples:
            output = sample.get('output', {})
            
            # Count issue types
            issuetype = output.get('issuetype', 'Unknown')
            stats['issue_types'][issuetype] = stats['issue_types'].get(issuetype, 0) + 1
            
            # Count fields
            if output.get('assignee'):
                stats['has_assignee'] += 1
            if output.get('epic_link'):
                stats['has_epic_link'] += 1
            if output.get('priority'):
                stats['has_priority'] += 1
        
        return stats


if __name__ == '__main__':
    collector = DataCollector()
    stats = collector.get_statistics()
    
    print("📊 Dataset Statistics:")
    print(json.dumps(stats, indent=2, ensure_ascii=False))
