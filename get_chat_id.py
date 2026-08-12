"""Find the chat id to put in TELEGRAM_CHAT_IDS.

    python get_chat_id.py

Before running it:
  1. Create the group in Telegram and add your bot to it.
  2. Send "/start" in the group. It must be a slash command — Telegram's
     default privacy mode means bots never see ordinary group chatter, so a
     plain "hello" will not show up here.

Groups do not appear in @userinfobot, which is why this exists.
"""

import sys

import httpx

import config

if not config.TELEGRAM_BOT_TOKEN:
    sys.exit("TELEGRAM_BOT_TOKEN is not set in .env — create the bot with "
             "@BotFather first.")

url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates"
resp = httpx.get(url, timeout=20)

if resp.status_code == 401:
    sys.exit("Telegram rejected the token. Check TELEGRAM_BOT_TOKEN in .env.")
resp.raise_for_status()

payload = resp.json()
if not payload.get("ok"):
    sys.exit(f"Telegram error: {payload}")

updates = payload["result"]
if not updates:
    sys.exit(
        "No recent messages.\n\n"
        "If the webhook is already registered, getUpdates stays empty by "
        "design — Telegram will not use both delivery methods at once.\n"
        "Run this before deploying, or clear the webhook first:\n"
        f"  https://api.telegram.org/bot<TOKEN>/deleteWebhook\n\n"
        "Otherwise: add the bot to the group and send /start there."
    )

seen = {}
for update in updates:
    message = (update.get("message") or update.get("channel_post")
               or update.get("my_chat_member", {}).get("chat") and update["my_chat_member"])
    if not message:
        continue
    chat = message.get("chat") or {}
    if chat.get("id") is not None:
        seen[chat["id"]] = chat

if not seen:
    sys.exit("Updates came back but none carried a chat. Send /start in the "
             "group and try again.")

print("\nChats this bot can reach:\n")
for chat_id, chat in seen.items():
    kind = chat.get("type", "?")
    name = chat.get("title") or " ".join(
        filter(None, [chat.get("first_name"), chat.get("last_name")])) or "(no name)"
    note = "  <- your family group" if kind in ("group", "supergroup") else ""
    print(f"  {chat_id:>16}   {kind:<11} {name}{note}")

groups = [cid for cid, c in seen.items()
          if c.get("type") in ("group", "supergroup")]

print("\nPut this in .env:\n")
if groups:
    print(f"  TELEGRAM_CHAT_IDS={','.join(str(g) for g in groups)}")
    print("\nGroup ids are negative — the minus sign is part of the id, keep it.")
    print("Note: if Telegram later upgrades the group to a supergroup, this id "
          "changes and alerts stop. Re-run this if that happens.")
else:
    print(f"  TELEGRAM_CHAT_IDS={','.join(str(c) for c in seen)}")
    print("\nNo group found — those are direct chats. Add the bot to your "
          "group and send /start there.")
print()
