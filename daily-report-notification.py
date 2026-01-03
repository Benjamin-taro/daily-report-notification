import os
import json
import sys
from datetime import datetime, timezone
import urllib.request
import urllib.error
from zoneinfo import ZoneInfo  # Python 3.9+

LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


def build_text_message() -> dict:
    now_jst = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Tokyo"))

    date_str = now_jst.strftime("%Y-%m-%d")
    time_str = now_jst.strftime("%H:%M")

    text = (
        "こんばんは！\n\n"
        f"{date_str} {time_str}（日本時間）\n\n"
        "✍️ 今日の日報を投稿しましょう！"
    )

    return {"type": "text", "text": text}


def _post_json(url: str, token: str, payload_obj: dict) -> None:
    payload = json.dumps(payload_obj, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            status = res.status
            body = res.read().decode("utf-8", errors="replace")
            print(f"OK: url={url} status={status} body={body}")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"HTTPError: url={url} status={e.code} body={err_body}", file=sys.stderr)
        raise
    except Exception as e:
        print(f"Error: url={url} err={e}", file=sys.stderr)
        raise


def send_broadcast(token: str, messages: list[dict]) -> None:
    _post_json(LINE_BROADCAST_URL, token, {"messages": messages})


def send_push(token: str, user_id: str, messages: list[dict]) -> None:
    _post_json(LINE_PUSH_URL, token, {"to": user_id, "messages": messages})


def main():
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("Missing env var: LINE_CHANNEL_ACCESS_TOKEN")

    # true / 1 / yes を true 扱い（Actionsで扱いやすい）
    test_mode = os.environ.get("LINE_TEST_MODE", "").strip().lower() in ("true", "1", "yes")

    messages = [build_text_message()]

    if test_mode:
        user_id = os.environ.get("TEST_LINE_USER_ID")
        if not user_id:
            raise RuntimeError("Missing env var: TEST_LINE_USER_ID (required when LINE_TEST_MODE=true)")
        send_push(token, user_id, messages)
        print("Sent in TEST mode (push to a single user).")
    else:
        send_broadcast(token, messages)
        print("Sent in PROD mode (broadcast).")


if __name__ == "__main__":
    main()
