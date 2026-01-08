"""
Data models cho task information
"""
from typing import Optional, List
from dataclasses import dataclass

@dataclass
class TaskInfo:
    """Thông tin task được parse từ AI"""
    summary: str
    issuetype: str
    description: str
    priority: Optional[str] = None
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    epic_link: Optional[str] = None
    assignee: Optional[str] = None
    media_urls: List[str] = None
    
    def __post_init__(self):
        if self.media_urls is None:
            self.media_urls = []
    
    @classmethod
    def from_dict(cls, data: dict) -> 'TaskInfo':
        """Tạo TaskInfo từ dict"""
        return cls(
            summary=data.get('summary', 'No summary'),
            issuetype=data.get('issuetype', 'Task'),
            description=data.get('description', 'No description'),
            priority=data.get('priority'),
            start_date=data.get('start_date'),
            due_date=data.get('due_date'),
            epic_link=data.get('epic_link'),
            assignee=data.get('assignee'),
            media_urls=data.get('media_urls', [])
        )
    
    def to_dict(self) -> dict:
        """Chuyển TaskInfo thành dict"""
        return {
            'summary': self.summary,
            'issuetype': self.issuetype,
            'description': self.description,
            'priority': self.priority,
            'start_date': self.start_date,
            'due_date': self.due_date,
            'epic_link': self.epic_link,
            'assignee': self.assignee,
            'media_urls': self.media_urls
        }
