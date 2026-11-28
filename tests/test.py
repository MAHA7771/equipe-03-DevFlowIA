# scripts/check_slack.py (partie 2, à lancer à la place de la partie 1)
import os
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

load_dotenv()
app = App(token=os.environ["SLACK_BOT_TOKEN"])

@app.command("/agent")
def on_agent(ack, command, client):
    ack()                                   # obligatoire en moins de 3 s
    print("command payload :", command)     # note : pas de thread_ts ici
    root = client.chat_postMessage(
        channel=command["channel_id"],
        text=f"🤖 Demande reçue : `{command.get('text', '')}`",
    )
    ts = root["ts"]                         # c'est ce ts qui devient ton thread_ts
    client.chat_postMessage(
        channel=command["channel_id"], thread_ts=ts,
        text=f"Réponse dans le fil (thread_ts={ts})",
    )

if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()