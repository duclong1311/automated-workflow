"""
Data models cho Bitbucket webhook events
"""
import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
import logging
import requests
from config.settings import settings


def _fetch_commit_message_for_repo(repository: Dict[str, Any], commit_hash: str) -> Optional[str]:
    """Try to fetch commit message from Bitbucket (Server or Cloud) using repository info and commit hash.
    Returns message string or None.
    """
    if not settings.BITBUCKET_BASE_URL:
        return None

    base = settings.BITBUCKET_BASE_URL.rstrip('/')
    auth = None
    if settings.BITBUCKET_USER and settings.BITBUCKET_TOKEN:
        auth = (settings.BITBUCKET_USER, settings.BITBUCKET_TOKEN)

    # Try Bitbucket Server endpoint first if repo has project.key and slug
    try_urls = []
    project_key = None
    slug = None
    if isinstance(repository, dict):
        project_key = (repository.get('project') or {}).get('key') if repository.get('project') else None
        slug = repository.get('slug') or repository.get('name') or repository.get('fullName')

    if project_key and slug:
        try_urls.append(f"{base}/rest/api/1.0/projects/{project_key}/repos/{slug}/commits/{commit_hash}")

    # Bitbucket Cloud style: /2.0/repositories/{workspace}/{repo_slug}/commit/{commit}
    # repository.get('fullName') might be 'workspace/repo'
    full = repository.get('fullName') or repository.get('full_name') if isinstance(repository, dict) else None
    if full and '/' in full:
        try_urls.append(f"{base}/2.0/repositories/{full}/commit/{commit_hash}")

    # Fallback: try base + /commits/{hash}
    try_urls.append(f"{base}/commits/{commit_hash}")

    headers = {}
    for url in try_urls:
        try:
            resp = requests.get(url, auth=auth, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                # Try common fields
                msg = None
                if isinstance(data, dict):
                    msg = data.get('message') or data.get('commit', {}).get('message') if data.get('commit') else None
                    if not msg:
                        msg = data.get('rendered', {}).get('message') if data.get('rendered') else None
                    if not msg:
                        # Bitbucket Cloud returns 'message' at top-level for commit object
                        msg = data.get('message')
                if msg:
                    return msg
        except Exception:
            continue

    return None


@dataclass
class BitbucketEvent:
    """Base class cho Bitbucket webhook events"""
    event_type: str
    repository: Dict[str, Any]
    actor: Dict[str, Any]
    
    def extract_issue_keys(self) -> List[str]:
        """Extract Jira issue keys từ commit messages, branch names, PR titles"""
        issue_keys = []
        
        # Pattern để tìm issue keys: PROJ-123, DXAI-456, ERBUIL23-3193 etc.
        # Allow letters and digits in project key section (e.g., ERBUIL23)
        pattern = r'\b([A-Za-z][A-Za-z0-9]*-\d+)\b'

        # Override trong các subclass
        return issue_keys


@dataclass
class PushEvent(BitbucketEvent):
    """Event khi có push hoặc create branch"""
    changes: List[Dict[str, Any]]
    
    def extract_issue_keys(self) -> List[str]:
        """Extract issue keys từ commit messages và branch names"""
        issue_keys = []
        pattern = r'\b([A-Za-z][A-Za-z0-9]*-\d+)\b'
        
        # Tìm trong branch names
        for change in self.changes:
            # Branch name can be under change['new']['name'] or change.get('ref', {}).get('displayId')
            if 'new' in change and 'name' in change['new']:
                branch_name = change['new']['name']
                matches = re.findall(pattern, branch_name, re.IGNORECASE)
                issue_keys.extend(matches)
            elif 'ref' in change and isinstance(change['ref'], dict):
                branch_name = change['ref'].get('displayId') or change['ref'].get('id')
                if branch_name:
                    matches = re.findall(pattern, branch_name, re.IGNORECASE)
                    issue_keys.extend(matches)
            
            # Tìm trong commit messages
            if 'commits' in change:
                for commit in change.get('commits', []):
                    # Commit message may be under 'message' or 'displayMessage' depending on payload
                    msg = commit.get('message') or commit.get('displayMessage') or commit.get('comment') or ''
                    if msg:
                        matches = re.findall(pattern, msg, re.IGNORECASE)
                        issue_keys.extend(matches)
        
        # Normalize to uppercase, remove duplicates và return
        normalized = {m.upper() for m in issue_keys}

        if not normalized:
            # Debug: log shape of changes to help troubleshooting
            logger = logging.getLogger(__name__)
            try:
                change_count = len(self.changes) if self.changes is not None else 0
                preview = None
                if change_count > 0:
                    first = self.changes[0]
                    preview = {
                        'keys': list(first.keys()) if isinstance(first, dict) else None,
                        'new': first.get('new') if isinstance(first, dict) else None,
                        'ref': first.get('ref') if isinstance(first, dict) else None,
                        'commits_sample': []
                    }
                    commits = first.get('commits') or first.get('values') or []
                    for c in (commits[:3] if isinstance(commits, list) else []):
                        preview['commits_sample'].append({
                            'message': c.get('message') if isinstance(c, dict) else None,
                            'displayMessage': c.get('displayMessage') if isinstance(c, dict) else None
                        })
                logger.info(f"ℹ️ PushEvent.extract_issue_keys found 0 keys; changes_count={change_count}; preview={preview}")
            except Exception:
                logger.exception("⚠️ Lỗi khi log preview của PushEvent")

            # Nếu không tìm thấy keys trong payload, thử lấy commit messages bằng API
            try:
                fetched_msgs = []
                for ch in (self.changes or []):
                    # Try to get the target commit hash (toHash/to) from various payload shapes
                    to_hash = None
                    if isinstance(ch, dict):
                        to_hash = ch.get('toHash') or ch.get('to') or (ch.get('new') or {}).get('target', {}).get('hash') if ch.get('new') else None
                        # Bitbucket Server may use 'ref' -> 'latestCommit'
                        if not to_hash and 'ref' in ch and isinstance(ch['ref'], dict):
                            to_hash = ch['ref'].get('latestCommit') or ch['ref'].get('id')

                    if to_hash:
                        msg = _fetch_commit_message_for_repo(self.repository, to_hash)
                        if msg:
                            fetched_msgs.append(msg)

                # Scan fetched messages for issue keys
                for msg in fetched_msgs:
                    matches = re.findall(pattern, msg, re.IGNORECASE)
                    for m in matches:
                        normalized.add(m.upper())

            except Exception:
                logger.exception("⚠️ Lỗi khi fetch commit messages từ Bitbucket API")

        return list(normalized)


@dataclass
class PullRequestEvent(BitbucketEvent):
    """Event khi có pull request (created, updated, merged)"""
    pullrequest: Dict[str, Any]
    
    def extract_issue_keys(self) -> List[str]:
        """Extract issue keys từ PR title, description, branch names"""
        issue_keys = []
        pattern = r'\b([A-Za-z][A-Za-z0-9]*-\d+)\b'
        
        pr = self.pullrequest
        
        # Tìm trong title
        if 'title' in pr and pr['title']:
            matches = re.findall(pattern, pr['title'], re.IGNORECASE)
            issue_keys.extend(matches)
        
        # Tìm trong description
        if 'description' in pr and pr['description']:
            matches = re.findall(pattern, pr['description'], re.IGNORECASE)
            issue_keys.extend(matches)
        
        # Tìm trong source branch
        # Source branch can be nested differently across Bitbucket variants
        source_branch = None
        if 'source' in pr and isinstance(pr['source'], dict):
            src = pr['source']
            if 'branch' in src and isinstance(src['branch'], dict):
                source_branch = src['branch'].get('name') or src['branch'].get('displayId')
            else:
                # try common keys
                source_branch = src.get('branch') or src.get('ref')
        if source_branch:
            matches = re.findall(pattern, source_branch, re.IGNORECASE)
            issue_keys.extend(matches)
        
        normalized = {m.upper() for m in issue_keys}

        if not normalized:
            logger = logging.getLogger(__name__)
            try:
                preview = {
                    'title': pr.get('title'),
                    'description_present': bool(pr.get('description')),
                    'source_branch': None
                }
                if 'source' in pr and isinstance(pr['source'], dict):
                    src = pr['source']
                    if 'branch' in src and isinstance(src['branch'], dict):
                        preview['source_branch'] = src['branch'].get('name') or src['branch'].get('displayId')
                    else:
                        preview['source_branch'] = src.get('branch') or src.get('ref')
                logger.info(f"ℹ️ PullRequestEvent.extract_issue_keys found 0 keys; preview={preview}")
            except Exception:
                logger.exception("⚠️ Lỗi khi log preview của PullRequestEvent")

        return list(normalized)
    
    def is_merged(self) -> bool:
        """Kiểm tra xem PR đã được merge chưa"""
        pr = self.pullrequest
        return pr.get('state') == 'MERGED' or pr.get('state') == 'merged'
    
    def is_created(self) -> bool:
        """Kiểm tra xem PR mới được tạo"""
        # Bitbucket thường gửi event với state = 'OPEN' khi tạo mới
        pr = self.pullrequest
        return pr.get('state') == 'OPEN' or pr.get('state') == 'open'


def parse_bitbucket_event(data: Dict[str, Any]) -> Optional[BitbucketEvent]:
    """
    Parse Bitbucket webhook payload thành event object
    """
    try:
        event_type = data.get('eventKey', '')
        
        if 'push' in event_type.lower() or 'repo:refs_changed' in event_type.lower():
            # Push hoặc create branch event
            # Try to locate changes in several common payload shapes
            changes = data.get('changes') or []
            if not changes:
                # Bitbucket Cloud/Server may nest under 'push' key
                push = data.get('push') or {}
                if isinstance(push, dict):
                    changes = push.get('changes') or []
            if not changes:
                # Some payloads use 'refChanges' or similar
                changes = data.get('refChanges') or data.get('changes', [])

            return PushEvent(
                event_type=event_type,
                repository=data.get('repository', {}),
                actor=data.get('actor', {}),
                changes=changes or []
            )
        
        elif 'pullrequest' in event_type.lower() or 'pr:' in event_type.lower():
            # Pull request event
            # Try to find pullrequest object under several possible keys (pullrequest, pullRequest, pull_request)
            pr_obj = data.get('pullrequest') or data.get('pullRequest') or data.get('pull_request')
            if not pr_obj:
                # Try to locate any dict key that starts with 'pull'
                for k, v in data.items():
                    if k.lower().startswith('pull') and isinstance(v, dict):
                        pr_obj = v
                        break

            return PullRequestEvent(
                event_type=event_type,
                repository=data.get('repository', {}),
                actor=data.get('actor', {}),
                pullrequest=pr_obj or {}
            )
        
        else:
            # Unknown event type
            return None
            
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"❌ Lỗi khi parse Bitbucket event: {e}")
        return None

