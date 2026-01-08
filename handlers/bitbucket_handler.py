"""
Webhook handler cho Bitbucket events
Tự động chuyển trạng thái Jira và log work dựa trên sự kiện Bitbucket
"""
import logging
import re
from typing import Dict, List, Optional
from datetime import datetime

from models.bitbucket_event import parse_bitbucket_event, BitbucketEvent, PushEvent, PullRequestEvent
from services.jira_service import JiraService

logger = logging.getLogger(__name__)

# Initialize service
jira_service = JiraService()

# Mapping sự kiện Bitbucket với trạng thái Jira
EVENT_STATUS_MAPPING = {
    'push': 'in Progress',
    'repo:refs_changed': 'in Progress',
    'branch_created': 'in Progress',
    'pr:opened': 'resolve',
    'pr:created': 'resolve',
    'pr:from_ref_updated': 'in progress',
    'pr:merged': 'Deploy',
    'pr:declined': None,  # Không đổi trạng thái nếu PR bị decline
    'pr:deleted': None,
}


def extract_issue_keys_from_text(text: str) -> List[str]:
    """Extract Jira issue keys từ text (branch name, commit message, PR title)"""
    if not text:
        return []
    
    # Pattern: PROJ-123, DXAI-456, etc.
    # Allow digits inside project key (e.g., ERBUIL23-3193)
    pattern = r'\b([A-Z][A-Z0-9]*-\d+)\b'
    matches = re.findall(pattern, text, re.IGNORECASE)
    return list(set(matches))  # Remove duplicates


def extract_time_from_commit_messages(commits: List[Dict]) -> Optional[str]:
    """
    Extract thời gian từ commit messages nếu có #time <TIME>
    Nếu không có, trả về None (không tự động tính toán)
    Format: #time 2h 30m, #time 1h, #time 30m
    """
    if not commits:
        return None
    
    # Tìm #time trong commit messages
    time_pattern = r'#time\s+(\d+h(?:\s+\d+m)?|\d+m)'
    
    for commit in commits:
        message = commit.get('message', '')
        if message:
            match = re.search(time_pattern, message, re.IGNORECASE)
            if match:
                time_spent = match.group(1)
                logger.info(f"⏱️ Tìm thấy #time trong commit: {time_spent}")
                return time_spent
    # Không có #time => không tự động log work
    return None


def compute_kloc_from_commits(commits: List[Dict]) -> Optional[float]:
    """Ước lượng KLoC (kilo lines of code) từ metadata của commits.
    Trả về tổng KLoC (float) hoặc None nếu không có thông tin.
    """
    if not commits:
        return None

    total_added = 0
    found = False

    for commit in commits:
        # Try common fields
        added = None
        for key in ('linesAdded', 'lines_added', 'added', 'lines_added_count'):
            v = commit.get(key)
            if isinstance(v, int):
                added = v
                break

        # stats block
        if added is None:
            stats = commit.get('stats') or commit.get('properties') or {}
            if isinstance(stats, dict):
                for key in ('added', 'linesAdded', 'lines_added'):
                    v = stats.get(key)
                    if isinstance(v, int):
                        added = v
                        break

        # files list
        if added is None:
            files = commit.get('files') or commit.get('diffs') or commit.get('values')
            if isinstance(files, list) and files:
                s = 0
                for f in files:
                    for key in ('linesAdded', 'lines_added', 'added'):
                        v = f.get(key) if isinstance(f, dict) else None
                        if isinstance(v, int):
                            s += v
                if s > 0:
                    added = s

        if isinstance(added, int):
            total_added += added
            found = True

    if not found:
        return None

    kloc = total_added / 1000.0
    return kloc


def process_bitbucket_event(event_data: Dict) -> Dict:
    """
    Xử lý Bitbucket webhook event
    Returns: dict với thông tin kết quả
    """
    try:
        # Parse event
        event = parse_bitbucket_event(event_data)
        if not event:
            logger.warning(f"⚠️ Không thể parse event hoặc event type không được hỗ trợ")
            return {
                "success": False,
                "message": "Event type không được hỗ trợ"
            }
        
        # Extract issue keys từ event
        issue_keys = event.extract_issue_keys()
        
        if not issue_keys:
            logger.info("ℹ️ Không tìm thấy issue keys trong event")
            return {
                "success": True,
                "message": "Không tìm thấy issue keys để xử lý"
            }
        
        logger.info(f"📋 Tìm thấy {len(issue_keys)} issue keys: {', '.join(issue_keys)}")
        
        # Xác định trạng thái Jira dựa trên event type
        event_type = event.event_type.lower()
        target_status = None
        
        # Tìm mapping phù hợp
        for key, status in EVENT_STATUS_MAPPING.items():
            if key in event_type:
                target_status = status
                break
        
        # Xử lý từng issue
        results = []
        for issue_key in issue_keys:
            issue_result = {
                "issue_key": issue_key,
                "transitioned": False,
                "worklogged": False
            }
            
            # 1. Chuyển trạng thái nếu có target_status
            if target_status:
                transitioned = jira_service.transition_issue(issue_key, target_status)
                issue_result["transitioned"] = transitioned
                issue_result["target_status"] = target_status
                if transitioned:
                    logger.info(f"✅ Đã chuyển {issue_key} → {target_status}")
            
            # 2. Log work nếu là push event (có commits)
            if isinstance(event, PushEvent):
                # Lấy tất cả commits
                all_commits = []
                for change in event.changes:
                    if 'commits' in change:
                        all_commits.extend(change.get('commits', []))
                # Nếu có commits, thêm comment chi tiết (KLoC + messages)
                if all_commits:
                    # Compute KLoC estimation if possible
                    kloc = compute_kloc_from_commits(all_commits)

                    # Tạo comment từ commit messages (loại bỏ #time để comment sạch hơn)
                    commit_messages = []
                    for c in all_commits[:5]:
                        msg = c.get('message') or c.get('displayMessage') or ''
                        msg = str(msg).split('\n')[0]
                        # Loại bỏ #time từ message khi hiển thị
                        msg = re.sub(r'#time\s+\d+h(?:\s+\d+m)?|#time\s+\d+m', '', msg, flags=re.IGNORECASE).strip()
                        if msg:
                            commit_messages.append(msg)

                    comment = f"Bitbucket: {len(all_commits)} commit(s)"
                    if commit_messages:
                        comment += "\n" + "\n".join(commit_messages)
                    if kloc is not None:
                        comment += f"\nEstimated KLoC: {kloc:.3f}"

                    # ALWAYS add comment; DO NOT log work
                    try:
                        added = jira_service.add_comment(issue_key, comment)
                        if added:
                            logger.info(f"✅ Đã thêm comment chi tiết cho {issue_key}")
                        else:
                            logger.warning(f"⚠️ Không thể thêm comment cho {issue_key}")
                    except Exception:
                        logger.exception(f"⚠️ Lỗi khi thêm comment cho {issue_key}")
                    # Keep worklogged flag False (we no longer auto-log work)
                    issue_result["worklogged"] = False
                else:
                    # Không có commits trong payload (ví dụ refs_changed)
                    # Thêm comment ngắn ghi nhận branch push/creation
                    branch_names = []
                    for change in event.changes:
                        if isinstance(change, dict):
                            # try ref.displayId, new.name, ref.id
                            ref = change.get('ref') or {}
                            if isinstance(ref, dict):
                                name = ref.get('displayId') or ref.get('id')
                                if name:
                                    branch_names.append(name)
                            new = change.get('new') or {}
                            if isinstance(new, dict):
                                name = new.get('name') or (new.get('displayId') if isinstance(new.get('displayId'), str) else None)
                                if name:
                                    branch_names.append(name)

                    branch_names = list(dict.fromkeys([b for b in branch_names if b]))
                    comment = f"Bitbucket: event={event.event_type}"
                    if branch_names:
                        comment += f" - branch(s): {', '.join(branch_names)}"
                    try:
                        added = jira_service.add_comment(issue_key, comment)
                        if added:
                            logger.info(f"✅ Đã thêm comment branch cho {issue_key}")
                        else:
                            logger.warning(f"⚠️ Không thể thêm comment branch cho {issue_key}")
                    except Exception:
                        logger.exception("⚠️ Lỗi khi thêm comment branch")
                    issue_result["worklogged"] = False
            
            # 3. PR merged: thêm comment (không auto log work)
            elif isinstance(event, PullRequestEvent) and event.is_merged():
                comment = f"Bitbucket: PR merged - {event.pullrequest.get('title', 'N/A')}"
                try:
                    added = jira_service.add_comment(issue_key, comment)
                    if added:
                        logger.info(f"✅ Đã thêm comment PR merged cho {issue_key}")
                    else:
                        logger.warning(f"⚠️ Không thể thêm comment PR merged cho {issue_key}")
                except Exception:
                    logger.exception("⚠️ Lỗi khi thêm comment PR merged")
                issue_result["worklogged"] = False
            
            results.append(issue_result)
        
        # Tổng kết
        transitioned_count = sum(1 for r in results if r.get("transitioned"))
        worklogged_count = sum(1 for r in results if r.get("worklogged"))
        
        message = f"Đã xử lý {len(issue_keys)} issue(s): {transitioned_count} chuyển trạng thái, {worklogged_count} ghi worklog"
        
        return {
            "success": True,
            "message": message,
            "results": results
        }
        
    except Exception as e:
        logger.error(f"❌ Lỗi khi xử lý Bitbucket event: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "message": f"Lỗi: {str(e)}"
        }



