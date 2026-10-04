import json
import urllib.request
import urllib.error

# ===============================
# LINE API URLs
# ===============================
LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"


class LineApiError(RuntimeError):
    """LINE API がエラー応答を返した"""

    def __init__(self, status: int, detail: str):
        super().__init__(f"LINE API error: status={status} detail={detail}")
        self.status = status


class LineClient:
    """LINE Messaging API クライアント"""

    def __init__(self, access_token: str):
        self.access_token = access_token

    def _post_json(self, url: str, payload: dict, retry_key: str = None) -> None:
        """JSONデータをPOST送信"""
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        if retry_key:
            headers["X-Line-Retry-Key"] = retry_key
        req = urllib.request.Request(url, data=data, method="POST", headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=20):
                pass
        except urllib.error.HTTPError as e:
            raise LineApiError(e.code, e.read().decode("utf-8", errors="replace")) from e

    def send_reply(self, reply_token: str, messages: list[dict]) -> None:
        """Reply APIでメッセージを返信"""
        payload = {
            "replyToken": reply_token,
            "messages": messages
        }
        self._post_json(LINE_REPLY_URL, payload)

    def send_push(self, user_id: str, messages: list[dict]) -> None:
        """Push APIでメッセージを送信"""
        payload = {
            "to": user_id,
            "messages": messages
        }
        self._post_json(LINE_PUSH_URL, payload)

    def send_broadcast(self, messages: list[dict], retry_key: str = None) -> bool:
        """Broadcast APIでメッセージを配信。

        retry_key（UUID）を渡すと、同じキーの配信は24時間のあいだ LINE 側で1回に抑えられる。
        Returns:
            配信したら True。同じ retry_key ですでに配信済みだったら False。
        """
        payload = {
            "messages": messages
        }
        try:
            self._post_json(LINE_BROADCAST_URL, payload, retry_key=retry_key)
        except LineApiError as e:
            if retry_key and e.status == 409:
                return False
            raise
        return True

def build_text_message(text: str) -> dict:
    """テキストメッセージを作成"""
    return {"type": "text", "text": text}

def build_quick_reply_message(text: str, items: list[dict]) -> dict:
    """Quick Reply付きメッセージを作成"""
    return {
        "type": "text",
        "text": text,
        "quickReply": {
            "items": items
        }
    }

def build_postback_action(label: str, data: str, display_text: str = None) -> dict:
    """Postbackアクションを作成"""
    return {
        "type": "action",
        "action": {
            "type": "postback",
            "label": label,
            "data": data,
            "displayText": display_text or label
        }
    }
