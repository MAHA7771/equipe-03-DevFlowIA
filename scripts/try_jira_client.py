"""Essai manuel du client Jira : crée une issue AGT, la commente, la passe en Terminé."""
from src import jira_client as jc
from src.models import SlackInfo, Task

task = Task(task_id="T-9999", mode="task", description="Essai du client Jira (à supprimer)",
            slack=SlackInfo(channel_id="C0", thread_ts="0.0", user_id="U0"),
            branch="agent/T-9999-essai", repo_path=".")

key = jc.create_issue(task)
print("Issue créée :", key)
jc.add_comment(key, "Commentaire de test depuis jira_client.py")
jc.transition(key, "done")
print("Passée en Terminé : vérifie dans Jira")