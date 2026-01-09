"""Webhook handler for Bitbucket events.

Provides a modular `process_bitbucket_event` function that parses incoming
Bitbucket webhook payloads and updates Jira via `JiraService`.

Features:
- Extract Jira issue keys from branch/commit/PR texts
- Map Bitbucket events to Jira transitions
- Add informative comments with commit summaries and KLoC estimates
- Optionally compute KLoC from commit metadata
- Estimate simple bug-rate from commit messages
"""
import logging
import re
from typing import Dict, List, Optional
from datetime import datetime

from models.bitbucket_event import parse_bitbucket_event, BitbucketEvent, PushEvent, PullRequestEvent
from services.jira_service import JiraService
from config.settings import settings

logger = logging.getLogger(__name__)

jira_service = JiraService()

# Map Bitbucket events (substr match) -> Jira transition name (or None to skip)
EVENT_STATUS_MAPPING = {
    'push': 'in Progress',
    'repo:refs_changed': 'in Progress',
    'branch_created': 'in Progress',
    'pr:opened': 'resolve',
    'pr:created': 'resolve',
    'pr:from_ref_updated': 'in progress',
    'pr:merged': 'Deploy',
    'pr:declined': None,
    'pr:deleted': None,
}


ISSUE_KEY_PATTERN = re.compile(r"\b([A-Z][A-Z0-9]*-\d+)\b")


def compute_kloc_from_commits(commits: List[Dict]) -> Optional[float]:
    """Estimate KLoC from commit metadata when available."""
    if not commits:
        return None
    total_added = 0
    found = False
    for commit in commits:
        added = None
        for key in ('linesAdded', 'lines_added', 'added', 'lines_added_count'):
            v = commit.get(key)
            if isinstance(v, int):
                added = v
                break

        if added is None:
            stats = commit.get('stats') or commit.get('properties') or {}
            if isinstance(stats, dict):
                for key in ('added', 'linesAdded', 'lines_added'):
                    v = stats.get(key)
                    if isinstance(v, int):
                        added = v
                        break

        if added is None:
            files = commit.get('files') or commit.get('diffs') or commit.get('values')
            if isinstance(files, list) and files:
                s = 0
                for f in files:
                    if isinstance(f, dict):
                        for key in ('linesAdded', 'lines_added', 'added'):
                            v = f.get(key)
                            if isinstance(v, int):
                                s += v
                if s > 0:
                    added = s

        if isinstance(added, int):
            total_added += added
            found = True

    if not found:
        return None

    return total_added / 1000.0


def compute_bug_rate_from_commits(commits: List[Dict]) -> Optional[float]:
    """Estimate bug-rate as fraction of commits that mention bug-related keywords."""
    if not commits:
        return None
    bug_keywords = re.compile(r'\b(bug|fix|fixes|fixed|bugfix|hotfix|repair|patch)\b', re.IGNORECASE)
    bug_count = 0
    for c in commits:
        msg = (c.get('message') or c.get('displayMessage') or '')
        if msg and bug_keywords.search(str(msg)):
            bug_count += 1
    try:
        return bug_count / len(commits)
    except Exception:
        return None


def build_commit_comment(commits: List[Dict], max_messages: int = 5) -> str:
    if not commits:
        return ''
    messages = []
    for c in commits[:max_messages]:
        msg = c.get('message') or c.get('displayMessage') or ''
        msg = str(msg).split('\n')[0]
        msg = re.sub(r'#time\s+\d+h(?:\s+\d+m)?|#time\s+\d+m', '', msg, flags=re.IGNORECASE).strip()
        if msg:
            messages.append(msg)
    return '\n'.join(messages)


def map_event_to_status(event_type: str) -> Optional[str]:
    et = (event_type or '').lower()
    for key, status in EVENT_STATUS_MAPPING.items():
        if key in et:
            return status
    return None


def handle_push_event(issue_key: str, event: PushEvent) -> Dict:
    result = {"issue_key": issue_key, "transitioned": False, "worklogged": False}
    # Transition if mapping exists
    target_status = map_event_to_status(event.event_type)
    if target_status:
        transitioned = jira_service.transition_issue(issue_key, target_status)
        result['transitioned'] = bool(transitioned)
        result['target_status'] = target_status
        if transitioned:
            logger.info(f"✅ Transitioned {issue_key} -> {target_status}")

    # Collect commits and add comment
    all_commits = []
    for change in getattr(event, 'changes', []) or []:
        if isinstance(change, dict) and 'commits' in change:
            all_commits.extend(change.get('commits', []))

    if all_commits:
        kloc = compute_kloc_from_commits(all_commits)
        bug_rate = compute_bug_rate_from_commits(all_commits)
        commit_msg_block = build_commit_comment(all_commits)

        comment = f"Bitbucket: {len(all_commits)} commit(s)"
        if commit_msg_block:
            comment += '\n' + commit_msg_block
        if kloc is not None:
            comment += f"\nEstimated KLoC: {kloc:.3f}"
        if bug_rate is not None:
            comment += f"\nEstimated bug-rate: {bug_rate:.1%} ({int(bug_rate*100)}% of commits mention bug keywords)"

        # Chỉ thêm comment nếu BITBUCKET_AUTO_COMMENT được bật
        if settings.BITBUCKET_AUTO_COMMENT:
            try:
                added = jira_service.add_comment(issue_key, comment)
                if added:
                    logger.info(f"✅ Đã thêm comment chi tiết cho {issue_key}")
                else:
                    logger.warning(f"⚠️ Không thể thêm comment cho {issue_key}")
            except Exception:
                logger.exception(f"⚠️ Lỗi khi thêm comment cho {issue_key}")
        else:
            logger.info(f"ℹ️ Bỏ qua comment (BITBUCKET_AUTO_COMMENT=false) cho {issue_key}")
        result["worklogged"] = False
    else:
        # No commits: try to extract branch names and estimate added lines from metadata
        branch_names = []
        estimated_added = 0
        found_metadata = False
        for change in getattr(event, 'changes', []) or []:
            if isinstance(change, dict):
                ref = change.get('ref') or {}
                if isinstance(ref, dict):
                    name = ref.get('displayId') or ref.get('id')
                    if name:
                        branch_names.append(name)
                new = change.get('new') or {}
                if isinstance(new, dict):
                    name = new.get('name') or new.get('displayId')
                    if name:
                        branch_names.append(name)

                for key in ('linesAdded', 'lines_added', 'added', 'totalAdded'):
                    v = change.get(key)
                    if isinstance(v, int):
                        estimated_added += v
                        found_metadata = True
                stats = change.get('stats') or change.get('properties') or {}
                if isinstance(stats, dict):
                    for key in ('added', 'linesAdded', 'lines_added'):
                        v = stats.get(key)
                        if isinstance(v, int):
                            estimated_added += v
                            found_metadata = True

        branch_names = list(dict.fromkeys([b for b in branch_names if b]))
        comment = f"Bitbucket: event={event.event_type}"
        if branch_names:
            comment += f" - branch(s): {', '.join(branch_names)}"

        if found_metadata and estimated_added > 0:
            kloc = estimated_added / 1000.0
            comment += f"\nEstimated KLoC (from change metadata): {kloc:.3f} (added {estimated_added} lines)"
        else:
            comment += "\n(No commit metadata available to estimate KLoC)"

        # Chỉ thêm comment nếu BITBUCKET_AUTO_COMMENT được bật
        if settings.BITBUCKET_AUTO_COMMENT:
            try:
                added = jira_service.add_comment(issue_key, comment)
                if added:
                    logger.info(f"✅ Đã thêm comment branch cho {issue_key}")
                else:
                    logger.warning(f"⚠️ Không thể thêm comment branch cho {issue_key}")
            except Exception:
                logger.exception("⚠️ Lỗi khi thêm comment branch")
        else:
            logger.info(f"ℹ️ Bỏ qua comment (BITBUCKET_AUTO_COMMENT=false) cho {issue_key}")
        result["worklogged"] = False

    return result


def handle_pr_event(issue_key: str, event: PullRequestEvent) -> Dict:
    result = {"issue_key": issue_key, "transitioned": False, "worklogged": False}
    if event.is_merged():
        title = event.pullrequest.get('title', 'N/A')
        comment = f"Bitbucket: PR merged - {title}"
        # Chỉ thêm comment nếu BITBUCKET_AUTO_COMMENT được bật
        if settings.BITBUCKET_AUTO_COMMENT:
            try:
                jira_service.add_comment(issue_key, comment)
                logger.info(f"✅ Added PR merged comment to {issue_key}")
            except Exception:
                logger.exception(f"⚠️ Failed to add PR merged comment for {issue_key}")
        else:
            logger.info(f"ℹ️ Bỏ qua comment (BITBUCKET_AUTO_COMMENT=false) cho {issue_key}")
    return result


def process_bitbucket_event(event_data: Dict) -> Dict:
    try:
        event = parse_bitbucket_event(event_data)
        if not event:
            logger.warning("⚠️ Unsupported or unparsable event")
            return {"success": False, "message": "Unsupported event type"}
        issue_keys = event.extract_issue_keys()
        if not issue_keys:
            logger.info("ℹ️ No issue keys found in event")
            return {"success": True, "message": "No issue keys to process"}
        logger.info(f"📋 Found {len(issue_keys)} issue keys: {', '.join(issue_keys)}")
        results = []
        for issue_key in issue_keys:
            if isinstance(event, PushEvent):
                r = handle_push_event(issue_key, event)
            elif isinstance(event, PullRequestEvent):
                r = handle_pr_event(issue_key, event)
            else:
                r = {"issue_key": issue_key, "transitioned": False, "worklogged": False}
                target_status = map_event_to_status(getattr(event, 'event_type', ''))
                if target_status:
                    transitioned = jira_service.transition_issue(issue_key, target_status)
                    r['transitioned'] = bool(transitioned)
                    r['target_status'] = target_status
            results.append(r)
        transitioned_count = sum(1 for r in results if r.get('transitioned'))
        worklogged_count = sum(1 for r in results if r.get('worklogged'))
        message = f"Processed {len(issue_keys)} issue(s): {transitioned_count} transitioned, {worklogged_count} worklogged"
        return {"success": True, "message": message, "results": results}
    except Exception as e:
        logger.error(f"❌ Error processing Bitbucket event: {e}")
        logger.error(e, exc_info=True)
        return {"success": False, "message": f"Error: {str(e)}"}
