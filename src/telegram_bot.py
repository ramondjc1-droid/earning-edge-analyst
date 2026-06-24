"""Telegram delivery + polling for slash commands.

Sending uses the Bot API directly over HTTPS (no extra deps). The same module
can long-poll getUpdates to handle the /picks, /status, etc. commands.
"""
from __future__ import annotations

from typing import Optional

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

API = "https://api.telegram.org/bot{token}/{method}"


def configured() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def _call(method: str, payload: dict, timeout: int = 30) -> Optional[dict]:
    if not TELEGRAM_BOT_TOKEN:
        return None
    url = API.format(token=TELEGRAM_BOT_TOKEN, method=method)
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        print(f"[telegram] {method} failed: {exc}")
        return None


def send_message(text: str, chat_id: Optional[str] = None,
                 parse_mode: str = "HTML") -> bool:
    chat_id = chat_id or TELEGRAM_CHAT_ID
    if not (TELEGRAM_BOT_TOKEN and chat_id):
        print("[telegram] not configured — printing instead:\n")
        print(text)
        return False
    # Telegram caps messages at 4096 chars; chunk safely.
    ok = True
    for chunk in _chunk(text, 4000):
        res = _call("sendMessage", {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        })
        ok = ok and bool(res and res.get("ok"))
    return ok


def _chunk(text: str, size: int):
    if len(text) <= size:
        yield text
        return
    lines, buf = text.split("\n"), ""
    for ln in lines:
        if len(buf) + len(ln) + 1 > size:
            yield buf
            buf = ""
        buf += ln + "\n"
    if buf:
        yield buf


def get_updates(offset: Optional[int] = None, timeout: int = 25) -> list[dict]:
    res = _call("getUpdates", {"offset": offset, "timeout": timeout},
                timeout=timeout + 5)
    if not res or not res.get("ok"):
        return []
    return res.get("result", [])


def get_chat_id_hint() -> str:
    """Helper for setup: print the chat id of whoever last messaged the bot."""
    updates = get_updates(timeout=2)
    if not updates:
        return ("No messages found. Open Telegram, send any message to your bot, "
                "then run this again.")
    last = updates[-1]
    msg = last.get("message") or last.get("channel_post") or {}
    chat = msg.get("chat", {})
    return (f"chat_id = {chat.get('id')}  "
            f"(name: {chat.get('first_name') or chat.get('title')})")


if __name__ == "__main__":
    # Quick manual test / chat-id discovery helper.
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "chatid":
        print(get_chat_id_hint())
    else:
        ok = send_message("✅ <b>Earnings Edge Analyst</b> Telegram link test.")
        print("sent" if ok else "not configured / failed")
