"""Point d'entrée : lance le bot Slack en Socket Mode.   Commande : python -m src.main"""
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from src import pipeline, review, slack_app
from src.config import load_config


def main() -> None:
    cfg = load_config()
    missing = [n for n, v in (("SLACK_BOT_TOKEN", cfg.slack_bot_token),
                              ("SLACK_APP_TOKEN", cfg.slack_app_token)) if not v]
    if missing:
        raise SystemExit(f"Variables manquantes dans .env : {', '.join(missing)}")

    app = App(token=cfg.slack_bot_token)
    slack_app.register(app)                 # commande /agent + bouton « Corriger » (P1)
    review.register_handlers(app)           # Approuver / Rejeter + modale (P3)

    print("Jira :", "réel" if cfg.jira_enabled else "FACTICE (JIRA_BASE_URL vide)")
    print("Faux temporaires de P2 :", ", ".join(pipeline.STUBS_IN_USE) or "aucun")
    SocketModeHandler(app, cfg.slack_app_token).start()


if __name__ == "__main__":
    main()