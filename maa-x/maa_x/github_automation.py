"""GitHub automation runtime wrappers using gh when available."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass
class GitHubResult:
    ok: bool
    command: str
    stdout: str = ''
    stderr: str = ''
    returncode: int = 0


class GitHubAutomation:
    def __init__(self) -> None:
        self.gh_available = shutil.which('gh') is not None

    def run(self, *args: str) -> GitHubResult:
        cmd = ['gh', *args]
        if not self.gh_available:
            return GitHubResult(False, ' '.join(cmd), stderr='gh not installed', returncode=127)
        p = subprocess.run(cmd, capture_output=True, text=True)
        return GitHubResult(p.returncode == 0, ' '.join(cmd), p.stdout, p.stderr, p.returncode)

    def list_issues(self, repo: str, limit: int = 20) -> GitHubResult:
        return self.run('issue', 'list', '--repo', repo, '--limit', str(limit), '--json', 'number,title,state')

    def list_prs(self, repo: str, limit: int = 20) -> GitHubResult:
        return self.run('pr', 'list', '--repo', repo, '--limit', str(limit), '--json', 'number,title,state')

    def view_issue(self, repo: str, number: int) -> GitHubResult:
        return self.run('issue', 'view', str(number), '--repo', repo, '--json', 'number,title,body,state')

    def view_pr(self, repo: str, number: int) -> GitHubResult:
        return self.run('pr', 'view', str(number), '--repo', repo, '--json', 'number,title,body,state')

    def workflow_runs(self, repo: str, limit: int = 20) -> GitHubResult:
        return self.run('run', 'list', '--repo', repo, '--limit', str(limit), '--json', 'databaseId,status,conclusion,workflowName')


_gh = GitHubAutomation()


def gh_available() -> bool:
    return _gh.gh_available


def list_issues(repo: str, limit: int = 20) -> GitHubResult:
    return _gh.list_issues(repo, limit)


def list_prs(repo: str, limit: int = 20) -> GitHubResult:
    return _gh.list_prs(repo, limit)


def view_issue(repo: str, number: int) -> GitHubResult:
    return _gh.view_issue(repo, number)


def view_pr(repo: str, number: int) -> GitHubResult:
    return _gh.view_pr(repo, number)


def workflow_runs(repo: str, limit: int = 20) -> GitHubResult:
    return _gh.workflow_runs(repo, limit)
