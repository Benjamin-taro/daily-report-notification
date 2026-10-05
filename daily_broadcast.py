import os
import json
import sys
import uuid
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo  # Python 3.9+

from comment import generate_tomorrow_note
from line_client import LineClient, build_text_message
from tz import WEEKDAY_JA
from weather import get_daily_forecasts

# ===============================
# Cities
# ===============================
CITIES = [
    {"name": "Glasgow", "lat": 55.8642, "lon": -4.2518},
    {"name": "秋田", "lat": 39.7186, "lon": 140.1024},
    {"name": "さいたま", "lat": 35.8617, "lon": 139.6455},
]

JST = ZoneInfo("Asia/Tokyo")

# ===============================
# Forecast aggregation
# ===============================
def get_tomorrow_forecasts(cities: list[dict], target_date: date) -> list[dict]:
    """各都市の target_date（現地の日付）の予報を返す。取得できなかった都市は含めない。"""
    try:
        results = get_daily_forecasts([(c["lat"], c["lon"]) for c in cities], target_date)
    except Exception as e:
        # 失敗しても全体を止めない
        print(f"[weather] failed err={e}", file=sys.stderr)
        return []

    forecasts = []
    for city, f in zip(cities, results):
        if f is None:
            print(f"[weather] no data city={city['name']} date={target_date}", file=sys.stderr)
            continue
        forecasts.append({"name": city["name"], **f})
    return forecasts

# ===============================
# Message builder
# ===============================
def _short_date(d: date) -> str:
    return f"{d.month}/{d.day}({WEEKDAY_JA[d.weekday()]})"


def format_forecast_block(forecasts: list[dict]) -> str:
    lines = []
    for f in forecasts:
        pop = f"{f['precip_prob']}%" if f["precip_prob"] is not None else "不明"
        lines.append(
            f"【{f['name']}】\n"
            f"{f['icon']} {f['weather']}\n"
            f"最高 {f['temp_max']:.0f}℃ / 最低 {f['temp_min']:.0f}℃ / 降水確率 {pop}"
        )
    return "\n\n".join(lines)


def build_message() -> dict:
    now_jst = datetime.now(timezone.utc).astimezone(JST)
    target_date = (now_jst + timedelta(days=1)).date()
    forecasts = get_tomorrow_forecasts(CITIES, target_date)

    sections = [
        "こんばんは！",
        "今日も一日お疲れ様でした🙌",
        f"{now_jst.strftime('%Y-%m-%d %H:%M')}（日本時間）",
        f"🌅 明日 {_short_date(target_date)} の天気",
    ]
    if forecasts:
        sections.append(format_forecast_block(forecasts))
    else:
        sections.append("（天気情報の取得に失敗しました🙏）")
    note = generate_tomorrow_note(target_date)
    if note:
        sections.append(f"📅 明日は何の日\n{note}")
    sections.append("✍️ 今日の日報を投稿しましょう！")

    return build_text_message("\n\n".join(sections))


# ===============================
# Entry point
# ===============================
def main():
    if "--dry-run" in sys.argv[1:]:
        # 送信せずにメッセージの中身だけ確認する
        print(json.dumps([build_message()], ensure_ascii=False, indent=2))
        return

    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("Missing LINE_CHANNEL_ACCESS_TOKEN")
    client = LineClient(token)

    test_mode = os.environ.get("LINE_TEST_MODE", "").lower() in ("true", "1", "yes")
    messages = [build_message()]

    if test_mode:
        user_id = os.environ.get("TEST_LINE_USER_ID")
        if not user_id:
            raise RuntimeError("Missing TEST_LINE_USER_ID")
        client.send_push(user_id, messages)
        print("TEST mode: sent to yourself")
    else:
        # 日付（日本時間）から決まるキーを付けて、同じ日の2回目以降の配信を LINE 側で弾いてもらう
        today_jst = datetime.now(timezone.utc).astimezone(JST).date()
        retry_key = str(uuid.uuid5(uuid.NAMESPACE_URL, f"daily-report-notification/{today_jst.isoformat()}"))
        if client.send_broadcast(messages, retry_key=retry_key):
            print("PROD mode: broadcast sent")
        else:
            print(f"PROD mode: already sent today ({today_jst}), skipped")

if __name__ == "__main__":
    main()
