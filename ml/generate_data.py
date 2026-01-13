"""
Script để generate synthetic training data
Dùng khi chưa có đủ real data
"""
import json
import random
from pathlib import Path


# Template patterns
TEMPLATES = [
    # Task templates
    {
        'pattern': 'Tạo task {summary}\nGán cho {assignee}\nPriority: {priority}',
        'type': 'Task',
        'has_assignee': True,
        'has_epic': False
    },
    {
        'pattern': 'Hãy tạo task {summary}\n{description}\nAssign to {assignee}',
        'type': 'Task',
        'has_assignee': True,
        'has_epic': False
    },
    {
        'pattern': '{summary}\n{description}\nPriority {priority}',
        'type': 'Task',
        'has_assignee': False,
        'has_epic': False
    },
    
    # Epic templates
    {
        'pattern': 'Tạo Epic {summary}\n{description}',
        'type': 'Epic',
        'has_assignee': False,
        'has_epic': False
    },
    {
        'pattern': 'Hãy tạo Epic {summary}\nGán cho {assignee}\n{description}',
        'type': 'Epic',
        'has_assignee': True,
        'has_epic': False
    },
    
    # Task with epic link
    {
        'pattern': 'Tạo task {summary}\nEpic link đến {epic}\nGán cho {assignee}',
        'type': 'Task',
        'has_assignee': True,
        'has_epic': True
    },
    {
        'pattern': '{summary}\n{description}\nLink to epic {epic}',
        'type': 'Task',
        'has_assignee': False,
        'has_epic': True
    },
]

# Sample data
SUMMARIES = [
    '[MS-T1][B-802] Fix bug login page',
    '[MS-T2][FEAT-101] Implement user authentication',
    '[BACKEND][DB-55] Design database schema',
    '[DEVOPS][CICD-23] Setup CI/CD pipeline',
    '[DOC][API-12] Create API documentation',
    '[PERF][SQL-88] Optimize query performance',
    '[TEST][UNIT-45] Add unit tests',
    '[REFACTOR][LEGACY-99] Refactor legacy code',
    '[UI][UX-234] Improve UI/UX',
    '[SECURITY][CVE-567] Fix security vulnerability',
    '[MS-T1][B-803] Cải thiện tính năng search',
    '[PAYMENT][GATEWAY-44] Tích hợp payment gateway',
    '[DASHBOARD][CHART-77] Xây dựng dashboard',
    '[PERF][OPTIMIZE-33] Tối ưu hiệu suất',
    '[MOBILE][UI-456] Sửa lỗi hiển thị trên mobile',
    '[Ưu tiên cao][BLD-3637] Tuyệt vời quá',
    '[High Priority][FEAT-888] New feature implementation',
]

DESCRIPTIONS = [
    '*[Nội dung đối ứng]*\n* Cần implement feature này để cải thiện trải nghiệm người dùng\n** Chi tiết yêu cầu\n*** Thêm validation cho form\n*** Improve error messages',
    '*[Bối cảnh]*\n* Bug đang ảnh hưởng đến production, cần fix gấp\n** Steps to reproduce\n*** Login với user A\n*** Click button X\n** Expected: No error\n** Actual: Error 500',
    '*[Mục tiêu]*\n* Refactor code để dễ maintain hơn\n** Current issues\n*** Code quá phức tạp\n*** Khó test\n* Giải pháp đề xuất\n** Break down thành modules nhỏ',
    '*[TODO]*\n* Thêm test cases để đảm bảo quality\n** Unit tests\n*** Test happy path\n*** Test edge cases\n** Integration tests',
    'Optimize để giảm thời gian load\n\nCác bước thực hiện:\n- Profile code hiện tại\n- Identify bottlenecks\n- Apply caching\n- Reduce DB queries',
    '*[Requirements]*\n* Implement theo design mới từ team UX\n** UI Changes\n*** New button layout\n*** Color scheme update\n* Backend changes needed\n** Update API response format',
    'Fix theo yêu cầu của client\n\nChiết tiết:\n- Thay đổi flow A→B→C\n- Thêm validation mới\n- Update documentation',
    '*[Specification]*\n* Update theo specification mới\n** API version 2.0\n*** Breaking changes\n*** Migration guide\n* Timeline: 2 weeks',
]

ASSIGNEES = [
    'Nguyễn Văn A',
    'Trần Thị B',
    'Lê Văn C',
    'Phạm Thị D',
    'Hoàng Văn E',
    'Trần Đức Long',
    'Nguyễn Thị Tú Anh',
]

EPICS = [
    'User Management',
    'Payment Integration',
    'Mobile App',
    'Dashboard Development',
    'API Refactoring',
    'Performance Optimization',
]

PRIORITIES = ['Low', 'Medium', 'High']


def generate_sample(template):
    """Generate một training sample từ template"""
    
    summary = random.choice(SUMMARIES)
    description = random.choice(DESCRIPTIONS)
    priority = random.choice(PRIORITIES)
    assignee = random.choice(ASSIGNEES) if template['has_assignee'] else None
    epic = random.choice(EPICS) if template['has_epic'] else None
    
    # Fill template
    text = template['pattern'].format(
        summary=summary,
        description=description,
        priority=priority,
        assignee=assignee or '',
        epic=epic or ''
    )
    
    # Create output
    output = {
        'summary': summary,
        'issuetype': template['type'],
        'description': description,
        'priority': priority,
    }
    
    if assignee:
        output['assignee'] = assignee
    if epic:
        output['epic_link'] = epic
    
    return {
        'input': text.strip(),
        'output': output
    }


def generate_dataset(num_samples=100, output_file='ml/data/training_data.jsonl'):
    """Generate synthetic dataset"""
    
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    samples = []
    for _ in range(num_samples):
        template = random.choice(TEMPLATES)
        sample = generate_sample(template)
        samples.append(sample)
    
    # Save
    with open(output_path, 'w', encoding='utf-8') as f:
        for sample in samples:
            f.write(json.dumps(sample, ensure_ascii=False) + '\n')
    
    print(f"✅ Generated {num_samples} samples to {output_path}")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--num', type=int, default=100, help='Number of samples')
    parser.add_argument('--output', default='ml/data/training_data.jsonl', help='Output file')
    
    args = parser.parse_args()
    
    generate_dataset(args.num, args.output)
