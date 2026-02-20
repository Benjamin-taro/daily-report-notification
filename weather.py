import json
import sys
import time
from datetime import datetime, timezone, timedelta
import urllib.request
import urllib.error
from zoneinfo import ZoneInfo  # Python 3.9+

# ===============================
# Weather mapping
# ===============================
WEATHERCODE_JA = {
    0: "快晴",
    1: "晴れ",
    2: "一部くもり",
    3: "くもり",
    24: "くもり",
    45: "霧",
    48: "着氷性の霧",
    51: "霧雨（弱）",
    53: "霧雨（中）",
    55: "霧雨（強）",
    29: "霧雨（強）",
    61: "雨（弱）",
    63: "雨（中）",
    65: "雨（強）",
    32: "雨（強）",
    71: "雪（弱）",
    73: "雪（中）",
    75: "雪（強）",
    35: "雪（強）",
    80: "にわか雨（弱）",
    81: "にわか雨（中）",
    82: "にわか雨（強）",
    38: "にわか雨（強）",
}

def weather_icon_from_code(code: int) -> str:
    """天気コードから絵文字アイコンを返す"""
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
# Weather fetch
# ===============================

def fetch_json_with_retry(url: str, timeout: int = 30, retries: int = 3, backoff_sec: float = 1.5) -> dict:
    """リトライ機能付きJSON取得。429 のときは待機を長めにしてレート制限の回復を待つ。"""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as res:
                return json.loads(res.read().decode("utf-8"))
        except Exception as e:
            last_err = e
            # 429 Too Many Requests のときは長めに待つ（制限窓のリセットを待つ）
            wait = backoff_sec ** (attempt - 1)
            if "429" in str(e):
                wait = max(wait, 60)
            print(f"[weather] fetch failed attempt={attempt}/{retries} err={e} -> retry in {wait:.1f}s", file=sys.stderr)
            time.sleep(wait)
    raise last_err

# 0:00-7:59 は「翌日（本日）」= その日の9-21時、8:00以降は「翌日」= 翌日の9-21時
MORNING_CUTOFF_HOUR = 8

# 天気APIのレート制限対策：同一条件の結果を短時間キャッシュ（秒）
WEATHER_CACHE_TTL_SECONDS = 300

_weather_cache: dict = {}
_weather_cache_time: dict = {}


def _target_date_and_header(tz_str: str) -> tuple:
    """その地点の現在時刻から、表示する日付と冒頭文言を決める。
    Returns:
        (target_date, header_label)
        header_label は "翌日（本日）" または "翌日"
    """
    tz = ZoneInfo(tz_str)
    now = datetime.now(timezone.utc).astimezone(tz)
    if 0 <= now.hour < MORNING_CUTOFF_HOUR:
        return now.date(), "翌日（本日）"
    return now.date() + timedelta(days=1), "翌日"


def get_tomorrow_weather_9_to_21(
    lat: float,
    lon: float,
    timezone_str: str = "Asia/Tokyo",
) -> tuple[list, str, str]:
    """その地点の現在時刻に応じて、本日または翌日の 9,12,15,18,21 時の天気を取得。
    同一 (lat, lon, timezone, 対象日) は WEATHER_CACHE_TTL_SECONDS の間キャッシュしてAPI呼び出しを削減。
    Returns:
        (forecasts, date_label, header_label)
        date_label は日付文字列（表示用）、header_label は "翌日（本日）" または "翌日"
    """
    target_date, header_label = _target_date_and_header(timezone_str)
    cache_key = (round(lat, 4), round(lon, 4), timezone_str, target_date.isoformat())
    now_ts = time.monotonic()
    if cache_key in _weather_cache and (now_ts - _weather_cache_time.get(cache_key, 0)) < WEATHER_CACHE_TTL_SECONDS:
        cached = _weather_cache[cache_key]
        return cached[0], cached[1], cached[2]

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&hourly=temperature_2m,precipitation_probability,weathercode"
        f"&timezone={timezone_str.replace('/', '%2F')}"
        "&forecast_days=3"
    )
    data = fetch_json_with_retry(url, timeout=30, retries=3, backoff_sec=2.0)
    hourly = data["hourly"]
    times = hourly["time"]
    temps = hourly["temperature_2m"]
    pops = hourly.get("precipitation_probability", [])
    codes = hourly["weathercode"]

    target_hours = (9, 12, 15, 18, 21)
    forecasts = []
    for h in target_hours:
        time_str = f"{target_date.isoformat()}T{h:02d}:00"
        try:
            idx = times.index(time_str)
        except ValueError:
            idx = None
            for i, t in enumerate(times):
                if t.startswith(target_date.isoformat()) and t.endswith(f"{h:02d}:00"):
                    idx = i
                    break
        if idx is None:
            continue
        code = int(codes[idx])
        # API の time は指定 timezone の現地時刻なので、その地点の 9/12/15/18/21 時として解釈する
        dt_naive = datetime.fromisoformat(times[idx].replace("Z", "+00:00"))
        if dt_naive.tzinfo is None:
            forecast_time = dt_naive.replace(tzinfo=ZoneInfo(timezone_str))
        else:
            forecast_time = dt_naive.astimezone(ZoneInfo(timezone_str))
        forecasts.append({
            "time": forecast_time.strftime("%H:%M"),
            "datetime": forecast_time.isoformat(),
            "temp": float(temps[idx]),
            "precip_prob": int(pops[idx]) if pops and idx < len(pops) and pops[idx] is not None else None,
            "weather": WEATHERCODE_JA.get(code, f"天気コード:{code}"),
            "code": code,
            "icon": weather_icon_from_code(code),
        })
    WEEKDAY_JA = ("月", "火", "水", "木", "金", "土", "日")
    date_label = f"{target_date.year}年{target_date.month}月{target_date.day}日({WEEKDAY_JA[target_date.weekday()]})"
    _weather_cache[cache_key] = (forecasts, date_label, header_label)
    _weather_cache_time[cache_key] = now_ts
    return forecasts, date_label, header_label


def get_weather_forecast_open_meteo(
    lat: float,
    lon: float,
    timezone_str: str = "Asia/Tokyo",
    forecast_hours: int = 12,
) -> list:
    """Open-Meteo APIから天気予報を取得（今から3時間ごと、指定時間分）。
    forecast_hours=12 のとき 0h, 3h, 6h, 9h の4スロット。"""
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&hourly=temperature_2m,precipitation_probability,weathercode"
        f"&timezone={timezone_str.replace('/', '%2F')}"
        "&forecast_days=2"
    )

    data = fetch_json_with_retry(url, timeout=30, retries=3, backoff_sec=2.0)

    hourly = data["hourly"]
    times = hourly["time"]
    temps = hourly["temperature_2m"]
    pops = hourly.get("precipitation_probability", [])
    codes = hourly["weathercode"]

    now = datetime.now(timezone.utc).astimezone(ZoneInfo(timezone_str))
    forecasts = []

    start_idx = 0
    for i, time_str in enumerate(times):
        forecast_time = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        forecast_time = forecast_time.astimezone(ZoneInfo(timezone_str))
        if forecast_time >= now:
            start_idx = i
            break

    n_slots = max(1, forecast_hours // 3)
    for i in range(n_slots):
        idx = start_idx + (i * 3)
        if idx >= len(times):
            break

        forecast_time = datetime.fromisoformat(times[idx].replace("Z", "+00:00"))
        forecast_time = forecast_time.astimezone(ZoneInfo(timezone_str))

        code = int(codes[idx])
        forecasts.append({
            "time": forecast_time.strftime("%H:%M"),
            "datetime": forecast_time.isoformat(),
            "temp": float(temps[idx]),
            "precip_prob": int(pops[idx]) if pops and idx < len(pops) and pops[idx] is not None else None,
            "weather": WEATHERCODE_JA.get(code, f"天気コード:{code}"),
            "code": code,
            "icon": weather_icon_from_code(code),
        })

    return forecasts

def get_tomorrow_morning_forecast_open_meteo(lat: float, lon: float, target_hour: int = 7) -> dict:
    """明日の朝の天気予報を取得（既存のdaily_broadcast.py用）"""
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
