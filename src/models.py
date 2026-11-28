"""Schémas Pydantic du contrat (§6).

PROPOSITION de P3 : à valider en équipe et à committer dans une PR dédiée
(règle §10 : models.py ne se modifie que dans une PR dédiée).
"""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Mode = Literal["task", "fix", "docs", "audit", "ask", "analyze"]
Severity = Literal["critical", "high", "medium", "low"]
Grade = Literal["A", "B", "C", "D", "E"]


class SlackInfo(BaseModel):
    channel_id: str
    thread_ts: str
    user_id: str


class Task(BaseModel):  # §6.2  P1 -> P2
    task_id: str
    mode: Mode
    description: str
    params: dict[str, Any] = Field(default_factory=dict)
    jira_key: Optional[str] = None
    slack: SlackInfo
    branch: Optional[str] = None
    repo_path: str
    revision: int = 0
    feedback: Optional[str] = None


class AgentTests(BaseModel):
    ran: bool
    passed: bool
    output: str = ""


class AgentResult(BaseModel):  # §6.3  P2 -> P1
    task_id: str
    status: Literal["success", "failed"]
    summary: str = ""
    explanation: Optional[str] = None
    files_changed: list[str] = Field(default_factory=list)
    tests: AgentTests
    error: Optional[str] = None
    iterations: int = 0


class FileDiff(BaseModel):
    path: str
    additions: int
    deletions: int


class DiffReport(BaseModel):  # §6.4  P3 -> P1
    task_id: str
    files: list[FileDiff] = Field(default_factory=list)
    diff_text: str = ""


class ReviewDecision(BaseModel):  # §6.5  P3 -> P1
    task_id: str
    decision: Literal["approved", "rejected"]
    feedback: Optional[str] = None
    reviewer_slack_id: str


class PRResult(BaseModel):  # §6.6  P3 -> P1
    task_id: str
    commit_sha: str
    branch: str
    pr_number: int
    pr_url: str


class Checkpoint(BaseModel):  # §6.10  P3
    checkpoint_id: str
    task_id: str
    label: str
    ref: str
    commit: str
    files_changed: int
    created_at: str


class Finding(BaseModel):  # §6.8  scanners -> runner -> P1
    finding_id: str = ""
    rule: Literal[
        "sql_injection", "xss", "exposed_secret", "hardcoded_password",
        "misconfiguration", "auth_issue", "authz_issue",
        "vulnerable_dependency", "outdated_dependency",
        "bug", "complexity", "bad_practice", "duplicate_code",
    ]
    backlog_task: str = ""
    severity: Severity
    file: str
    line: int = 0
    title: str
    evidence: str = ""
    recommendation: str = ""
    confidence: float = 0.5
    source: Literal["regex", "llm", "hybrid", "osv", "radon"] = "regex"


class Score(BaseModel):  # §6.9  valeur et note du Security Score
    value: int
    grade: Grade


class SecurityReport(BaseModel):  # §6.9  P1
    report_id: str
    task_id: str
    generated_at: str
    findings: list[Finding] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)  # critical, high, medium, low
    score: Score


class RepoFile(BaseModel):
    path: str
    reason: str


class RepoAnswer(BaseModel):  # §6.11
    question: str
    answer: str
    files: list[RepoFile] = Field(default_factory=list)