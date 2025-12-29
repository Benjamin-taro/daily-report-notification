import os
import json
import sys
from datetime import datetime, timezone
import urllib.request
from zoneinfo import ZoneInfo  # Python 3.9+

LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"

def build_text_message() -> dict:
    # 日本時間（JST）
    now_jst = datetime.now(timezone.utc).astimezone(
        ZoneInfo("Asia/Tokyo")
    )

    date_str = now_jst.strftime("%Y-%m-%d")
    time_str = now_jst.strftime("%H:%M")

    text = (
        "こんばんは！\n\n"
        f"{date_str} (日本時間) \n\n"
        "✍️ 今日の日報を投稿しましょう！"
    )

    return {
        "type": "text",
        "text": text
    }

def send_broadcast(channel_access_token: str, messages: list[dict]) -> None:
    payload = json.dumps({"messages": messages}).encode("utf-8")

    req = urllib.request.Request(
        LINE_BROADCAST_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {channel_access_token}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            # 成功時は 200 でボディが空のことが多い
            status = res.status
            body = res.read().decode("utf-8", errors="replace")
            print(f"OK: status={status}, body={body}")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"HTTPError: status={e.code}, body={err_body}", file=sys.stderr)
        raise
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        raise

def main():
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    # token = LINE_CHANNEL_ACCESS_TOKEN
    if not token:
        raise RuntimeError("Missing env var: LINE_CHANNEL_ACCESS_TOKEN")

    messages = [build_text_message()]
    send_broadcast(token, messages)

if __name__ == "__main__":
    main()
