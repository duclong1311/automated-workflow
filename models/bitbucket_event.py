"""Lightweight Bitbucket event models and parser used by the webhook handler.

Provides:
- parse_bitbucket_event(event_data) -> BitbucketEvent | PushEvent | PullRequestEvent | None
- BitbucketEvent base class with `extract_issue_keys()`

This module is intentionally permissive: it extracts issue keys from
branch names, commit messages, PR titles/descriptions and exposes a few
helpers used by the handler.
"""
from typing import Dict, List, Optional, Any
import re


ISSUE_KEY_PATTERN = re.compile(r"\b([A-Z][A-Z0-9]*-\d+)\b")


class BitbucketEvent:
    def __init__(self, raw: Dict[str, Any]):
        self.raw = raw
        # Generic event type string (if present in payload)
        self.event_type = (raw.get('eventKey') or raw.get('event') or raw.get('action') or '').lower()

    def extract_issue_keys(self) -> List[str]:
        """Extract Jira issue keys from common locations in the payload."""
        texts = []
        # Flatten some common locations
        try:
            texts.append(str(self.raw.get('ref', '') or self.raw.get('refChanges', '')))
        except Exception:
            pass

        # Scan the whole payload as fallback
        try:
            texts.append(str(self.raw))
        except Exception:
            pass

        found = set()
        for t in texts:
            for m in ISSUE_KEY_PATTERN.findall(t):
                found.add(m.upper())
        return list(found)


class PushEvent(BitbucketEvent):
    def __init__(self, raw: Dict[str, Any]):
        super().__init__(raw)
        # Bitbucket Cloud sometimes nests under 'push' -> 'changes'
        self.changes = []
        if 'push' in raw and isinstance(raw['push'], dict):
            self.changes = raw['push'].get('changes', []) or []
        elif 'changes' in raw and isinstance(raw['changes'], list):
            self.changes = raw.get('changes', [])
        elif isinstance(raw.get('changes'), dict):
            self.changes = [raw['changes']]
        # event_type fallback
        if not self.event_type:
            self.event_type = 'push'

    def extract_issue_keys(self) -> List[str]:
        found = set()
        # Branch names & commit messages
        for change in self.changes:
            # commits
            for c in (change.get('commits') or []):
                msg = c.get('message') or c.get('displayMessage') or ''
                for m in ISSUE_KEY_PATTERN.findall(str(msg)):
                    found.add(m.upper())
            # new/ref
            ref = change.get('new') or change.get('ref') or {}
            if isinstance(ref, dict):
                name = ref.get('name') or ref.get('displayId') or ref.get('id')
                if name:
                    for m in ISSUE_KEY_PATTERN.findall(str(name)):
                        found.add(m.upper())
            # old ref
            old = change.get('old') or {}
            if isinstance(old, dict):
                name = old.get('name') or old.get('displayId') or old.get('id')
                if name:
                    for m in ISSUE_KEY_PATTERN.findall(str(name)):
                        found.add(m.upper())

        # fallback to scanning raw payload
        if not found:
            for m in ISSUE_KEY_PATTERN.findall(str(self.raw)):
                found.add(m.upper())

        return list(found)


class PullRequestEvent(BitbucketEvent):
    def __init__(self, raw: Dict[str, Any]):
        super().__init__(raw)
        # Support different key names
        self.pullrequest = raw.get('pullrequest') or raw.get('pullRequest') or raw.get('pull_request') or {}
        if not self.event_type:
            # try action field (e.g., "pullrequest:fulfilled")
            self.event_type = (raw.get('eventKey') or raw.get('action') or '').lower() or 'pullrequest'

    def is_merged(self) -> bool:
        # Many payloads have pullrequest['state'] or event action
        state = (self.pullrequest.get('state') or '').lower()
        if state in ('merged', 'fulfilled'):
            return True
        action = (self.raw.get('action') or '').lower()
        if 'merged' in action or 'fulfill' in action:
            return True
        # Some servers provide 'closed' + merged flag
        if self.pullrequest.get('closed') and self.pullrequest.get('merged'):
            return True
        return False

    def extract_issue_keys(self) -> List[str]:
        found = set()
        title = self.pullrequest.get('title') or ''
        desc = self.pullrequest.get('description') or ''
        for m in ISSUE_KEY_PATTERN.findall(str(title)):
            found.add(m.upper())
        for m in ISSUE_KEY_PATTERN.findall(str(desc)):
            found.add(m.upper())

        # Also check source/target branch names
        src = (self.pullrequest.get('source') or {}).get('branch') or {}
        tgt = (self.pullrequest.get('destination') or {}).get('branch') or {}
        for b in (src, tgt):
            if isinstance(b, dict):
                name = b.get('name') or b.get('displayId') or ''
                for m in ISSUE_KEY_PATTERN.findall(str(name)):
                    found.add(m.upper())

        # Fallback scan whole payload
        if not found:
            for m in ISSUE_KEY_PATTERN.findall(str(self.raw)):
                found.add(m.upper())

        return list(found)


def parse_bitbucket_event(event_data: Dict[str, Any]) -> Optional[BitbucketEvent]:
    """Return a specific event model or None if not recognized."""
    if not isinstance(event_data, dict):
        return None

    # Push event (Bitbucket Cloud format)
    if 'push' in event_data or 'changes' in event_data:
        return PushEvent(event_data)

    # PR event
    if 'pullrequest' in event_data or 'pullRequest' in event_data or 'pull_request' in event_data:
        return PullRequestEvent(event_data)

    # Some webhooks include eventKey like 'repo:refs_changed' or 'pr:merged'
    event_key = (event_data.get('eventKey') or event_data.get('event') or '').lower()
    if event_key:
        if 'pr:' in event_key or 'pull' in event_key:
            return PullRequestEvent(event_data)
        if 'repo:' in event_key or 'push' in event_key or 'refs_changed' in event_key:
            return PushEvent(event_data)

    return None
