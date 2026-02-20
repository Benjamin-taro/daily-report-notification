import os
import json
import sys
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo  # Python 3.9+
import urllib.request

# weather.pyから天気取得ロジックをインポート
from weather import (
    weather_icon_from_code,
    get_tomorrow_morning_forecast_open_meteo,
)

# ===============================
# LINE API
# ===============================
LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"

# ===============================
# Cities
# ===============================
CITIES = [
    {"name": "横浜", "lat": 35.4437, "lon": 139.6380},
    {"name": "松山", "lat": 33.8392, "lon": 132.7657},
    {"name": "鹿児島", "lat": 31.5966, "lon": 130.5571},
    {"name": "秋田", "lat": 39.7186, "lon": 140.1024},
]

# ===============================
# Forecast aggregation
# ===============================
def get_tomorrow_forecasts(cities: list[dict], target_hour: int = 7) -> dict:
    now_jst = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Tokyo"))
    tomorrow_date = (now_jst + timedelta(days=1)).strftime("%Y-%m-%d")

    items = []
    for city in cities:
        try:
            f = get_tomorrow_morning_forecast_open_meteo(city["lat"], city["lon"], target_hour)
            items.append({
                "name": city["name"],
                "icon": weather_icon_from_code(f["code"]),
                "weather": f["weather"],
                "temp": f["temp"],
                "pop": f["precip_prob"],
                "ok": True,
            })
        except Exception as e:
            # 失敗しても全体を止めない
            print(f"[weather] failed city={city['name']} err={e}", file=sys.stderr)
            items.append({
                "name": city["name"],
                "icon": "❓",
                "weather": "取得失敗",
                "temp": 0.0,
                "pop": None,
                "ok": False,
            })

    return {"date": tomorrow_date, "time": f"{target_hour:02d}:00", "items": items}


def format_forecast_block(forecasts: dict) -> str:
    lines = []
    for item in forecasts["items"]:
        pop = f"{item['pop']}%" if item["pop"] is not None else "不明"
        lines.append(
            f"【{item['name']}】\n"
            f"{item['icon']} {item['weather']}\n"
            f"気温: {item['temp']:.1f}℃ / 降水確率: {pop}"
        )
    return "\n\n".join(lines)

# ===============================
# Message builder
# ===============================
def build_text_message() -> dict:
    now_jst = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Tokyo"))
    today = now_jst.strftime("%Y-%m-%d %H:%M")

    forecasts = get_tomorrow_forecasts(CITIES, target_hour=7)

    # 全都市失敗なら、天気セクションを軽くする
    any_ok = any(item.get("ok") for item in forecasts["items"])

    if any_ok:
        forecast_block = format_forecast_block(forecasts)
        weather_section = (
            f"🌅 明日（{forecasts['date']}）の朝 {forecasts['time']} の天気\n\n"
            f"{forecast_block}\n\n"
        )
    else:
        weather_section = (
            f"🌅 明日（{forecasts['date']}）の朝 {forecasts['time']} の天気\n\n"
            "（天気情報の取得に失敗しました🙏）\n\n"
        )

    text = (
        "こんばんは！\n\n"
        "今日も一日お疲れ様でした🙌\n\n"
        f"{today}（日本時間）\n\n"
        f"{weather_section}"
        "✍️ 今日の日報を投稿しましょう！"
    )

    return {"type": "text", "text": text}


# ===============================
# LINE send helpers
# ===============================
def _post_json(url: str, token: str, payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )

    with urllib.request.urlopen(req, timeout=20) as res:
        print(f"OK: {res.status}")

def send_broadcast(token: str, messages: list[dict]) -> None:
    _post_json(LINE_BROADCAST_URL, token, {"messages": messages})

def send_push(token: str, user_id: str, messages: list[dict]) -> None:
    _post_json(LINE_PUSH_URL, token, {"to": user_id, "messages": messages})

# ===============================
# Entry point
# ===============================
def main():
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("Missing LINE_CHANNEL_ACCESS_TOKEN")

    test_mode = os.environ.get("LINE_TEST_MODE", "").lower() in ("true", "1", "yes")
    messages = [build_text_message()]

    if test_mode:
        user_id = os.environ.get("TEST_LINE_USER_ID")
        if not user_id:
            raise RuntimeError("Missing TEST_LINE_USER_ID")
        send_push(token, user_id, messages)
        print("TEST mode: sent to yourself")
    else:
        send_broadcast(token, messages)
        print("PROD mode: broadcast sent")

if __name__ == "__main__":
    main()
