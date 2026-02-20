import os
import json
import urllib.request
import urllib.error

# ===============================
# LINE API URLs
# ===============================
LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"

class LineClient:
    """LINE Messaging API クライアント"""
    
    def __init__(self, access_token: str):
        self.access_token = access_token
    
    def _post_json(self, url: str, payload: dict) -> None:
        """JSONデータをPOST送信"""
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
        )
        
        with urllib.request.urlopen(req, timeout=20) as res:
            if res.status != 200:
                raise RuntimeError(f"LINE API error: status={res.status}")
    
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
    
    def send_broadcast(self, messages: list[dict]) -> None:
        """Broadcast APIでメッセージを配信"""
        payload = {
            "messages": messages
        }
        self._post_json(LINE_BROADCAST_URL, payload)

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
