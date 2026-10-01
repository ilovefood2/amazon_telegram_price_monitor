import os
import json
import requests

token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
if not token:
    raise SystemExit("Set TELEGRAM_BOT_TOKEN first.")

url = f"https://api.telegram.org/bot{token}/getUpdates"
r = requests.get(url, timeout=20)
r.raise_for_status()
data = r.json()

if not data.get("ok"):
    raise SystemExit(json.dumps(data, indent=2))

found = []
for item in data.get("result", []):
    msg = item.get("message") or item.get("channel_post") or {}
    chat = msg.get("chat") or {}
    if chat.get("id") is not None:
        found.append({
            "chat_id": chat.get("id"),
            "type": chat.get("type"),
            "username": chat.get("username"),
            "first_name": chat.get("first_name"),
            "title": chat.get("title"),
        })

if not found:
    print("No chat found yet. Send your bot a message in Telegram, then run this again.")
else:
    seen = set()
    for x in found:
        if x["chat_id"] in seen:
            continue
        seen.add(x["chat_id"])
        print(json.dumps(x, ensure_ascii=False))
