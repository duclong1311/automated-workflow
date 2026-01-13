"""
Training script cho PhoBERT task parser
"""
import json
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer, get_linear_schedule_with_warmup
from torch.optim import AdamW
from pathlib import Path
import logging
from tqdm import tqdm
import numpy as np

from task_parser import TaskParserModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TaskDataset(Dataset):
    """Dataset cho task parsing"""
    
    def __init__(self, data_file, tokenizer, max_length=256):
        self.tokenizer = tokenizer
        self.max_length = max_length
        
        # Load data
        self.samples = []
        with open(data_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    self.samples.append(json.loads(line))
        
        # Label mappings
        self.issue_types = ['Task', 'Epic', 'Bug', 'Story', 'Sub-task']
        self.priorities = ['Low', 'Medium', 'High']
        self.ner_labels = ['O', 'B-ASSIGNEE', 'I-ASSIGNEE', 'B-EPIC', 'I-EPIC', 'B-SUMMARY', 'I-SUMMARY']
        
        logger.info(f"Loaded {len(self.samples)} samples")
    
    def __len__(self):
        return len(self.samples)
    
    def __getitem__(self, idx):
        sample = self.samples[idx]
        text = sample['input']
        output = sample['output']
        
        # Tokenize - không dùng return_tensors để tránh dimension issues
        encoding = self.tokenizer(
            text,
            max_length=self.max_length,
            padding='max_length',
            truncation=True,
            return_tensors=None  # Trả về list thay vì tensor
        )
        
        # Labels
        issue_type = output.get('issuetype', 'Task')
        priority = output.get('priority', 'Medium')
        
        issue_type_label = self.issue_types.index(issue_type) if issue_type in self.issue_types else 0
        priority_label = self.priorities.index(priority) if priority in self.priorities else 1
        
        # NER labels (simplified - just tag as O for now, cần improve later)
        # TODO: Implement proper NER labeling
        ner_labels = [0] * self.max_length  # All 'O'
        
        return {
            'input_ids': torch.tensor(encoding['input_ids']),
            'attention_mask': torch.tensor(encoding['attention_mask']),
            'issue_type_label': torch.tensor(issue_type_label),
            'priority_label': torch.tensor(priority_label),
            'ner_labels': torch.tensor(ner_labels)
        }


def train_model(
    data_file='ml/data/training_data.jsonl',
    output_dir='ml/models/task_parser',
    epochs=10,
    batch_size=8,
    learning_rate=2e-5
):
    """Train PhoBERT model"""
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    logger.info(f"Using device: {device}")
    
    # Create output dir
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained("vinai/phobert-base")
    
    # Create dataset
    dataset = TaskDataset(data_file, tokenizer)
    
    # Split train/val
    train_size = int(0.8 * len(dataset))
    val_size = len(dataset) - train_size
    train_dataset, val_dataset = torch.utils.data.random_split(
        dataset, [train_size, val_size]
    )
    
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size)
    
    # Create model
    model = TaskParserModel()
    model.to(device)
    
    # Optimizer
    optimizer = AdamW(model.parameters(), lr=learning_rate)
    
    # Scheduler
    total_steps = len(train_loader) * epochs
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=int(0.1 * total_steps),
        num_training_steps=total_steps
    )
    
    # Loss functions
    criterion_cls = nn.CrossEntropyLoss()
    criterion_ner = nn.CrossEntropyLoss(ignore_index=-100)
    
    # Training loop
    best_val_loss = float('inf')
    
    for epoch in range(epochs):
        logger.info(f"\nEpoch {epoch + 1}/{epochs}")
        
        # Train
        model.train()
        train_loss = 0
        
        for batch in tqdm(train_loader, desc='Training'):
            optimizer.zero_grad()
            
            # Move to device
            input_ids = batch['input_ids'].to(device)
            attention_mask = batch['attention_mask'].to(device)
            issue_type_labels = batch['issue_type_label'].to(device)
            priority_labels = batch['priority_label'].to(device)
            ner_labels = batch['ner_labels'].to(device)
            
            # Forward
            outputs = model(input_ids, attention_mask)
            
            # Calculate losses
            loss_issue_type = criterion_cls(outputs['issue_type_logits'], issue_type_labels)
            loss_priority = criterion_cls(outputs['priority_logits'], priority_labels)
            loss_ner = criterion_ner(
                outputs['ner_logits'].view(-1, outputs['ner_logits'].size(-1)),
                ner_labels.view(-1)
            )
            
            # Combined loss
            loss = loss_issue_type + loss_priority + 0.5 * loss_ner
            
            # Backward
            loss.backward()
            optimizer.step()
            scheduler.step()
            
            train_loss += loss.item()
        
        avg_train_loss = train_loss / len(train_loader)
        logger.info(f"Train Loss: {avg_train_loss:.4f}")
        
        # Validation
        model.eval()
        val_loss = 0
        correct_issue_type = 0
        correct_priority = 0
        total = 0
        
        with torch.no_grad():
            for batch in tqdm(val_loader, desc='Validation'):
                input_ids = batch['input_ids'].to(device)
                attention_mask = batch['attention_mask'].to(device)
                issue_type_labels = batch['issue_type_label'].to(device)
                priority_labels = batch['priority_label'].to(device)
                ner_labels = batch['ner_labels'].to(device)
                
                outputs = model(input_ids, attention_mask)
                
                loss_issue_type = criterion_cls(outputs['issue_type_logits'], issue_type_labels)
                loss_priority = criterion_cls(outputs['priority_logits'], priority_labels)
                loss_ner = criterion_ner(
                    outputs['ner_logits'].view(-1, outputs['ner_logits'].size(-1)),
                    ner_labels.view(-1)
                )
                
                loss = loss_issue_type + loss_priority + 0.5 * loss_ner
                val_loss += loss.item()
                
                # Accuracy
                pred_issue_type = torch.argmax(outputs['issue_type_logits'], dim=-1)
                pred_priority = torch.argmax(outputs['priority_logits'], dim=-1)
                
                correct_issue_type += (pred_issue_type == issue_type_labels).sum().item()
                correct_priority += (pred_priority == priority_labels).sum().item()
                total += issue_type_labels.size(0)
        
        avg_val_loss = val_loss / len(val_loader)
        acc_issue_type = correct_issue_type / total
        acc_priority = correct_priority / total
        
        logger.info(f"Val Loss: {avg_val_loss:.4f}")
        logger.info(f"Issue Type Accuracy: {acc_issue_type:.4f}")
        logger.info(f"Priority Accuracy: {acc_priority:.4f}")
        
        # Save best model
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'val_loss': avg_val_loss,
            }, output_path / 'model.pt')
            logger.info(f"✅ Saved best model (val_loss: {avg_val_loss:.4f})")
    
    logger.info(f"\n✅ Training completed! Best val loss: {best_val_loss:.4f}")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', default='ml/data/training_data.jsonl', help='Training data file')
    parser.add_argument('--output', default='ml/models/task_parser', help='Output directory')
    parser.add_argument('--epochs', type=int, default=10, help='Number of epochs')
    parser.add_argument('--batch-size', type=int, default=8, help='Batch size')
    parser.add_argument('--lr', type=float, default=2e-5, help='Learning rate')
    
    args = parser.parse_args()
    
    train_model(
        data_file=args.data,
        output_dir=args.output,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr
    )
