import os
import json
import sys
import time
from datetime import datetime, timezone, timedelta
import urllib.request
import urllib.error
from zoneinfo import ZoneInfo  # Python 3.9+

# ===============================
# LINE API
# ===============================
LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"

# ===============================
# Weather mapping
# ===============================
WEATHERCODE_JA = {
    0: "快晴",
    1: "晴れ",
    2: "一部くもり",
    3: "くもり",
    45: "霧",
    48: "着氷性の霧",
    51: "霧雨（弱）",
    53: "霧雨（中）",
    55: "霧雨（強）",
    61: "雨（弱）",
    63: "雨（中）",
    65: "雨（強）",
    71: "雪（弱）",
    73: "雪（中）",
    75: "雪（強）",
    80: "にわか雨（弱）",
    81: "にわか雨（中）",
    82: "にわか雨（強）",
}

def weather_icon_from_code(code: int) -> str:
    if code == 0:
        return "☀️"
    if code in (1, 2):
        return "🌤️"
    if code == 3:
        return "☁️"
    if code in (45, 48):
        return "🌫️"
    if 51 <= code <= 57:
        return "🌦️"
    if 61 <= code <= 67 or 80 <= code <= 82:
        return "☂️"
    if 71 <= code <= 77 or 85 <= code <= 86:
        return "❄️"
    if code in (95, 96, 99):
        return "⛈️"
    return "🌡️"

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
# Weather fetch
# ===============================

def fetch_json_with_retry(url: str, timeout: int = 30, retries: int = 3, backoff_sec: float = 1.5) -> dict:
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as res:
                return json.loads(res.read().decode("utf-8"))
        except Exception as e:
            last_err = e
            wait = backoff_sec ** (attempt - 1)
            print(f"[weather] fetch failed attempt={attempt}/{retries} err={e} -> retry in {wait:.1f}s", file=sys.stderr)
            time.sleep(wait)
    raise last_err

def get_tomorrow_morning_forecast_open_meteo(lat: float, lon: float, target_hour: int = 7) -> dict:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&hourly=temperature_2m,precipitation_probability,weathercode"
        "&timezone=Asia%2FTokyo"
    )

    data = fetch_json_with_retry(url, timeout=30, retries=3, backoff_sec=2.0)

    hourly = data["hourly"]
    times = hourly["time"]
    temps = hourly["temperature_2m"]
    pops = hourly.get("precipitation_probability")
    codes = hourly["weathercode"]

    now_jst = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Tokyo"))
    tomorrow = (now_jst + timedelta(days=1)).date()
    target_time = f"{tomorrow.isoformat()}T{target_hour:02d}:00"

    try:
        idx = times.index(target_time)
    except ValueError:
        candidates = [i for i, t in enumerate(times) if t.startswith(tomorrow.isoformat())]
        if not candidates:
            raise RuntimeError("No forecast data for tomorrow")
        idx = candidates[0]

    code = int(codes[idx])
    return {
        "time": times[idx],
        "temp": float(temps[idx]),
        "precip_prob": int(pops[idx]) if pops and pops[idx] is not None else None,
        "weather": WEATHERCODE_JA.get(code, f"天気コード:{code}"),
        "code": code,
    }


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
