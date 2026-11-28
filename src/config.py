"""Configuration : lit .env une seule fois, sans planter si une variable manque."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    slack_bot_token: str
    slack_app_token: str
    slack_channel_id: str
    jira_base_url: str
    jira_email: str
    jira_api_token: str
    jira_project_key: str
    jira_status_in_progress: str
    jira_status_done: str
    groq_api_key: str
    groq_model: str
    github_token: str
    github_repo: str
    workspace_dir: str
    base_branch: str
    test_command: str
    db_path: str

    @property
    def jira_enabled(self) -> bool:
        """Faux si JIRA_BASE_URL est vide : jira_client passe en mode factice (§8)."""
        return bool(self.jira_base_url and "<site>" not in self.jira_base_url)


def load_config() -> Config:
    """Relit l'environnement à chaque appel (pratique pour les tests)."""
    g = lambda k, d="": os.getenv(k, d).strip()
    return Config(
        slack_bot_token=g("SLACK_BOT_TOKEN"),
        slack_app_token=g("SLACK_APP_TOKEN"),
        slack_channel_id=g("SLACK_CHANNEL_ID"),
        jira_base_url=g("JIRA_BASE_URL").rstrip("/"),
        jira_email=g("JIRA_EMAIL"),
        jira_api_token=g("JIRA_API_TOKEN"),
        jira_project_key=g("JIRA_PROJECT_KEY", "AGT"),
        jira_status_in_progress=g("JIRA_STATUS_IN_PROGRESS", "En cours"),
        jira_status_done=g("JIRA_STATUS_DONE", "Terminé"),
        groq_api_key=g("GROQ_API_KEY"),
        groq_model=g("GROQ_MODEL"),
        github_token=g("GITHUB_TOKEN"),
        github_repo=g("GITHUB_REPO"),
        workspace_dir=g("WORKSPACE_DIR", "./workspace/shop-ecommerce"),
        base_branch=g("BASE_BRANCH", "main"),
        test_command=g("TEST_COMMAND", "pytest -q"),
        db_path=g("TASK_DB_PATH", "agent.db"),
    )