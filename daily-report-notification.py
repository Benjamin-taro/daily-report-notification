import os
import json
import sys
from datetime import datetime, timezone, timedelta
import urllib.request
import urllib.error
from zoneinfo import ZoneInfo  # Python 3.9+

LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"

# ざっくり天気コード→日本語（必要なら増やせる）
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
def get_tomorrow_morning_forecast_open_meteo(
    lat: float,
    lon: float,
    target_hour: int = 7,  # “翌朝”の時刻（7時にしてるけど自由に変えてOK）
) -> dict:
    """
    Open-Meteoから “明日の target_hour:00(JST)” の予報を1点だけ取る。
    返り値: {"time": "...", "temp": float, "precip_prob": int|None, "weather": str}
    """
    # timezone=Asia/Tokyo を指定すると time がJSTで返ってくるので楽
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&hourly=temperature_2m,precipitation_probability,weathercode"
        "&timezone=Asia%2FTokyo"
    )

    with urllib.request.urlopen(url, timeout=20) as res:
        data = json.loads(res.read().decode("utf-8"))

    hourly = data["hourly"]
    times = hourly["time"]  # 例: "2026-01-04T07:00"
    temps = hourly["temperature_2m"]
    pops  = hourly.get("precipitation_probability")  # 無い場合もある
    wcodes = hourly["weathercode"]

    now_jst = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Tokyo"))
    tomorrow = (now_jst + timedelta(days=1)).date()
    target_time_str = f"{tomorrow.isoformat()}T{target_hour:02d}:00"

    # 該当時刻を探す
    try:
        idx = times.index(target_time_str)
    except ValueError:
        # もし見つからなければ、明日分の中で一番近い時刻を選ぶ（保険）
        tomorrow_prefix = tomorrow.isoformat()
        candidates = [i for i, t in enumerate(times) if t.startswith(tomorrow_prefix)]
        if not candidates:
            raise RuntimeError("No forecast data for tomorrow found.")
        idx = candidates[0]

    temp = float(temps[idx])
    pop = int(pops[idx]) if pops is not None and pops[idx] is not None else None
    wcode = int(wcodes[idx])
    weather = WEATHERCODE_JA.get(wcode, f"天気コード:{wcode}")

    return {
        "time": times[idx],
        "temp": temp,
        "precip_prob": pop,
        "weather": weather,
    }

def build_text_message() -> dict:
    now_jst = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Tokyo"))
    date_str = now_jst.strftime("%Y-%m-%d")
    time_str = now_jst.strftime("%H:%M")

    # 例：東京（必要ならあなたの地域の緯度経度に変更）
    forecast = get_tomorrow_morning_forecast_open_meteo(lat=35.6812, lon=139.7671, target_hour=7)

    pop_text = f"{forecast['precip_prob']}%" if forecast["precip_prob"] is not None else "不明"

    text = (
        "こんばんは！\n\n"
        f"{date_str} {time_str}（日本時間）\n\n"
        f"🌅 明日の朝 {forecast['time'][-5:]} の天気\n"
        f"天気：{forecast['weather']}\n"
        f"気温：{forecast['temp']:.1f}℃\n"
        f"降水確率：{pop_text}\n\n"
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
