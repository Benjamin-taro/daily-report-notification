import os
import hmac
import hashlib
import base64
from typing import List, Dict, Any
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import Response
import json

from line_client import LineClient, build_text_message, build_quick_reply_message, build_postback_action
from state_store import state_store
from weather import get_tomorrow_weather_9_to_21, weather_icon_from_code
from tz import calculate_timezone_difference, get_current_time_in_timezone, format_datetime_ja
from geocode import resolve_place

app = FastAPI()

# 環境変数から設定を取得
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
PORT = int(os.environ.get("PORT", "8000"))

if not LINE_CHANNEL_ACCESS_TOKEN:
    raise RuntimeError("Missing LINE_CHANNEL_ACCESS_TOKEN")
if not LINE_CHANNEL_SECRET:
    raise RuntimeError("Missing LINE_CHANNEL_SECRET")

line_client = LineClient(LINE_CHANNEL_ACCESS_TOKEN)

def verify_signature(body: bytes, signature: str) -> bool:
    """LINE Webhookの署名を検証"""
    hash_value = hmac.new(
        LINE_CHANNEL_SECRET.encode("utf-8"),
        body,
        hashlib.sha256
    ).digest()
    expected_signature = base64.b64encode(hash_value).decode("utf-8")
    return hmac.compare_digest(expected_signature, signature)

def handle_menu_command(user_id: str, reply_token: str):
    """メニューコマンドを処理"""
    quick_reply_items = [
        build_postback_action("時差計算", "mode=tz", "時差計算"),
        build_postback_action("天気", "mode=weather", "天気"),
    ]
    
    message = build_quick_reply_message(
        "何をお手伝いしましょうか？",
        quick_reply_items
    )
    line_client.send_reply(reply_token, [message])
    state_store.clear_state(user_id)

def handle_postback(user_id: str, data: str, reply_token: str):
    """Postbackイベントを処理"""
    if data == "mode=tz":
        state_store.set_state(user_id, {
            "mode": "tz",
            "step": "from",
            "from_place": None,
            "to_place": None,
        })
        message = build_text_message("あなたの地点の地名や郵便番号を入力してください（例：横浜、Berlin、100-0001）")
        line_client.send_reply(reply_token, [message])
    
    elif data == "mode=weather":
        state_store.set_state(user_id, {
            "mode": "weather",
            "step": "location",
            "location": None,
        })
        message = build_text_message("地名や郵便番号を入力するか、位置情報を送ってください（例：札幌、Osaka、NYC）")
        line_client.send_reply(reply_token, [message])

def handle_text_message(user_id: str, text: str, reply_token: str):
    """テキストメッセージを処理"""
    text_lower = text.strip().lower()
    
    # メニューコマンド
    if text_lower in ("メニュー", "menu", "help", "ヘルプ"):
        handle_menu_command(user_id, reply_token)
        return
    
    # 状態を取得
    state = state_store.get_state(user_id)
    
    if not state:
        # 状態がない場合はメニューを表示
        handle_menu_command(user_id, reply_token)
        return
    
    mode = state.get("mode")
    
    if mode == "tz":
        step = state.get("step")
        
        if step == "from":
            # 出発地をGeocodingで解決
            place = resolve_place(text)
            if not place:
                message = build_text_message(
                    f"「{text}」に該当する場所が見つかりませんでした。\n"
                    "2文字以上の地名や郵便番号で入力してください。"
                )
                line_client.send_reply(reply_token, [message])
                return
            
            state_store.update_state(user_id, from_place=place, step="to")
            message = build_text_message(
                f"あなたの地点：{place['display_name']}\n\n"
                "時差を知りたい都市の地名や郵便番号を入力してください。"
            )
            line_client.send_reply(reply_token, [message])
        
        elif step == "to":
            # 時差を知りたい都市をGeocodingで解決して時差計算
            place = resolve_place(text)
            if not place:
                message = build_text_message(
                    f"「{text}」に該当する場所が見つかりませんでした。\n"
                    "2文字以上の地名や郵便番号で入力してください。"
                )
                line_client.send_reply(reply_token, [message])
                return
            
            from_place = state.get("from_place")
            to_place = place
            from_tz = from_place["timezone"]
            to_tz = to_place["timezone"]
            
            hours_diff, diff_str = calculate_timezone_difference(from_tz, to_tz)
            time_yours = format_datetime_ja(from_tz)
            time_dest = format_datetime_ja(to_tz)
            
            result_text = (
                "【時差計算結果】\n\n"
                f"あなたの地点：{from_place['display_name']} ({from_tz})\n"
                f"{time_yours}\n\n"
                f"目的地：{to_place['display_name']} ({to_tz})\n"
                f"{time_dest}\n\n"
                f"時差：{diff_str}\n\n"
                "もう一度計算する場合は「メニュー」と入力してください。"
            )
            
            message = build_text_message(result_text)
            line_client.send_reply(reply_token, [message])
            state_store.clear_state(user_id)
    
    elif mode == "weather":
        # 天気モード：入力からGeocodingで場所を取得
        place = resolve_place(text)
        if not place:
            message = build_text_message(
                f"「{text}」に該当する場所が見つかりませんでした。\n"
                "2文字以上の地名や郵便番号を入力するか、位置情報を送ってください。"
            )
            line_client.send_reply(reply_token, [message])
            return
        
        try:
            forecasts, date_label, header_label = get_tomorrow_weather_9_to_21(
                place["lat"], place["lon"], place["timezone"]
            )
            lines = [
                f"こちら{header_label}の天気です。",
                f"【{date_label}｜{place['display_name']}の天気】",
            ]
            for f in forecasts:
                pop_str = f"{f['precip_prob']}%" if f['precip_prob'] is not None else "不明"
                lines.append(f"{f['time']} {f['icon']} {f['weather']} 気温: {f['temp']:.1f}℃ / 降水確率: {pop_str}")
            result_text = "\n".join(lines)
            result_text += "\n\nもう一度検索する場合は「メニュー」と入力してください。"
            
            message = build_text_message(result_text)
            line_client.send_reply(reply_token, [message])
            state_store.clear_state(user_id)
        
        except Exception as e:
            message = build_text_message(f"天気情報の取得に失敗しました: {str(e)}")
            line_client.send_reply(reply_token, [message])
            state_store.clear_state(user_id)

def handle_location_message(user_id: str, latitude: float, longitude: float, reply_token: str):
    """位置情報メッセージを処理"""
    state = state_store.get_state(user_id)
    
    if not state or state.get("mode") != "weather":
        # 天気モードでない場合はメニューを表示
        handle_menu_command(user_id, reply_token)
        return
    
    # 天気を取得
    try:
        # 位置情報からタイムゾーンを推定（簡易版：緯度経度からは正確なタイムゾーンを取得できないため、デフォルトを使用）
        tz = "Asia/Tokyo"  # 簡易実装
        forecasts, date_label, header_label = get_tomorrow_weather_9_to_21(latitude, longitude, tz)
        lines = [
            f"こちら{header_label}の天気です。",
            f"【{date_label}｜位置情報の天気】",
            f"緯度: {latitude:.4f}, 経度: {longitude:.4f}",
        ]
        for f in forecasts:
            pop_str = f"{f['precip_prob']}%" if f['precip_prob'] is not None else "不明"
            lines.append(f"{f['time']} {f['icon']} {f['weather']} 気温: {f['temp']:.1f}℃ / 降水確率: {pop_str}")
        result_text = "\n".join(lines)
        result_text += "\n\nもう一度検索する場合は「メニュー」と入力してください。"
        
        message = build_text_message(result_text)
        line_client.send_reply(reply_token, [message])
        state_store.clear_state(user_id)
    
    except Exception as e:
        message = build_text_message(f"天気情報の取得に失敗しました: {str(e)}")
        line_client.send_reply(reply_token, [message])
        state_store.clear_state(user_id)

@app.post("/webhook")
async def webhook(request: Request, x_line_signature: str = Header(None)):
    """LINE Webhookエンドポイント"""
    body = await request.body()
    
    # 署名検証
    if not verify_signature(body, x_line_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    data = json.loads(body.decode("utf-8"))
    events = data.get("events", [])
    
    for event in events:
        event_type = event.get("type")
        reply_token = event.get("replyToken")
        source = event.get("source", {})
        user_id = source.get("userId")
        
        if not user_id or not reply_token:
            continue
        
        if event_type == "message":
            message = event.get("message", {})
            message_type = message.get("type")
            
            if message_type == "text":
                handle_text_message(user_id, message.get("text", ""), reply_token)
            
            elif message_type == "location":
                location = message.get("location", {})
                handle_location_message(
                    user_id,
                    location.get("latitude"),
                    location.get("longitude"),
                    reply_token
                )
        
        elif event_type == "postback":
            postback_data = event.get("postback", {}).get("data", "")
            handle_postback(user_id, postback_data, reply_token)
    
    return Response(status_code=200)

@app.get("/health")
async def health():
    """ヘルスチェックエンドポイント"""
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
