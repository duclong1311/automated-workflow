from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class TaskInfo:
    summary: str = ""
    description: str = ""
    issuetype: str = "Task"
    priority: Optional[str] = None
    epic_link: Optional[str] = None
    assignee: Optional[str] = None
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    media_urls: Optional[List[str]] = field(default_factory=list)