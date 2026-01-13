"""
PhoBERT-based task parser
Fine-tuned model để parse task information từ Teams messages
"""
import json
import torch
import torch.nn as nn
from transformers import AutoTokenizer, AutoModel
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class TaskParserModel(nn.Module):
    """
    Multi-task model dựa trên PhoBERT:
    - Classification head cho issue_type (Task/Epic/Bug/etc)
    - Classification head cho priority (High/Medium/Low)
    - Token classification cho NER (assignee, epic_link extraction)
    """
    
    def __init__(self, num_issue_types=5, num_priorities=3, num_ner_labels=7):
        super().__init__()
        
        # Load PhoBERT
        model_name = "vinai/phobert-base"
        self.phobert = AutoModel.from_pretrained(model_name)
        # Resize token embeddings to match tokenizer
        self.phobert.resize_token_embeddings(self.phobert.config.vocab_size)
        hidden_size = self.phobert.config.hidden_size
        
        # Classification heads
        self.issue_type_classifier = nn.Linear(hidden_size, num_issue_types)
        self.priority_classifier = nn.Linear(hidden_size, num_priorities)
        
        # NER head (for extracting assignee, epic_link positions)
        self.ner_classifier = nn.Linear(hidden_size, num_ner_labels)
        
        # Dropout
        self.dropout = nn.Dropout(0.1)
    
    def forward(self, input_ids, attention_mask):
        outputs = self.phobert(
            input_ids=input_ids, 
            attention_mask=attention_mask,
            token_type_ids=None  # PhoBERT không cần token_type_ids
        )
        
        # [CLS] token for classification
        cls_output = outputs.last_hidden_state[:, 0, :]
        cls_output = self.dropout(cls_output)
        
        # Sequence output for NER
        sequence_output = outputs.last_hidden_state
        sequence_output = self.dropout(sequence_output)
        
        # Predictions
        issue_type_logits = self.issue_type_classifier(cls_output)
        priority_logits = self.priority_classifier(cls_output)
        ner_logits = self.ner_classifier(sequence_output)
        
        return {
            'issue_type_logits': issue_type_logits,
            'priority_logits': priority_logits,
            'ner_logits': ner_logits
        }


class TaskParser:
    """Wrapper class cho inference"""
    
    def __init__(self, model_path='ml/models/task_parser'):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model_path = Path(model_path)
        
        # Label mappings
        self.issue_types = ['Task', 'Epic', 'Bug', 'Story', 'Sub-task']
        self.priorities = ['Low', 'Medium', 'High']
        self.ner_labels = ['O', 'B-ASSIGNEE', 'I-ASSIGNEE', 'B-EPIC', 'I-EPIC', 'B-SUMMARY', 'I-SUMMARY']
        
        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained("vinai/phobert-base")
        
        # Load model
        self.model = None
        if self.model_path.exists():
            self.load_model()
    
    def load_model(self):
        """Load trained model"""
        try:
            self.model = TaskParserModel(
                num_issue_types=len(self.issue_types),
                num_priorities=len(self.priorities),
                num_ner_labels=len(self.ner_labels)
            )
            
            checkpoint = torch.load(
                self.model_path / 'model.pt',
                map_location=self.device
            )
            self.model.load_state_dict(checkpoint['model_state_dict'])
            self.model.to(self.device)
            self.model.eval()
            
            logger.info(f"✅ Loaded model from {self.model_path}")
        except Exception as e:
            logger.warning(f"⚠️ Could not load model: {e}")
            self.model = None
    
    def parse(self, text: str) -> dict:
        """
        Parse task information từ text
        
        Returns:
            dict: {
                'summary': str,
                'issuetype': str,
                'description': str,
                'priority': str,
                'epic_link': str,
                'assignee': str
            }
        """
        if self.model is None:
            raise ValueError("Model chưa được load. Hãy train model trước.")
        
        # Tokenize
        inputs = self.tokenizer(
            text,
            return_tensors='pt',
            max_length=256,
            truncation=True,
            padding=True
        )
        
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        # Inference
        with torch.no_grad():
            outputs = self.model(
                input_ids=inputs['input_ids'],
                attention_mask=inputs['attention_mask']
            )
        
        # Decode predictions
        issue_type_idx = torch.argmax(outputs['issue_type_logits'], dim=-1).item()
        priority_idx = torch.argmax(outputs['priority_logits'], dim=-1).item()
        ner_preds = torch.argmax(outputs['ner_logits'], dim=-1)[0].cpu().numpy()
        
        # Extract entities from NER predictions
        tokens = self.tokenizer.convert_ids_to_tokens(inputs['input_ids'][0])
        assignee = self._extract_entity(tokens, ner_preds, 'ASSIGNEE')
        epic_link = self._extract_entity(tokens, ner_preds, 'EPIC')
        summary = self._extract_entity(tokens, ner_preds, 'SUMMARY')
        
        # Build result
        result = {
            'summary': summary or self._extract_first_line(text),
            'issuetype': self.issue_types[issue_type_idx],
            'description': text,
            'priority': self.priorities[priority_idx],
            'epic_link': epic_link,
            'assignee': assignee
        }
        
        return result
    
    def _extract_entity(self, tokens, ner_preds, entity_type):
        """Extract entity từ NER predictions"""
        entity_tokens = []
        in_entity = False
        
        for token, label_idx in zip(tokens, ner_preds):
            label = self.ner_labels[label_idx]
            
            if label == f'B-{entity_type}':
                if entity_tokens:
                    break
                entity_tokens = [token]
                in_entity = True
            elif label == f'I-{entity_type}' and in_entity:
                entity_tokens.append(token)
            elif in_entity:
                break
        
        if entity_tokens:
            # Join tokens và clean up
            entity = ' '.join(entity_tokens)
            entity = entity.replace('@@', '').replace('_', ' ').strip()
            return entity
        
        return None
    
    def _extract_first_line(self, text):
        """Extract first non-empty line as summary"""
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if line and len(line) > 5:
                return line[:200]
        return 'No summary'


# Global instance
_parser = None

def get_parser():
    """Get singleton parser instance"""
    global _parser
    if _parser is None:
        _parser = TaskParser()
    return _parser


def parse_task(text: str) -> dict:
    """
    Parse task từ text sử dụng trained model
    Fallback to rule-based nếu model chưa có
    """
    parser = get_parser()
    
    try:
        if parser.model is not None:
            return parser.parse(text)
        else:
            logger.warning("⚠️ Model chưa trained, sử dụng fallback")
            return None
    except Exception as e:
        logger.error(f"❌ Lỗi khi parse với model: {e}")
        return None
