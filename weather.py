import json
import sys
import time
from datetime import date, datetime, timezone, timedelta, tzinfo
import urllib.request
import urllib.error

from tz import format_date_ja

# ===============================
# Weather mapping
# ===============================
# WMO weather interpretation codes（Open-Meteo が返すもの）
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
    56: "着氷性の霧雨（弱）",
    57: "着氷性の霧雨（強）",
    61: "雨（弱）",
    63: "雨（中）",
    65: "雨（強）",
    66: "着氷性の雨（弱）",
    67: "着氷性の雨（強）",
    71: "雪（弱）",
    73: "雪（中）",
    75: "雪（強）",
    77: "霧雪",
    80: "にわか雨（弱）",
    81: "にわか雨（中）",
    82: "にわか雨（強）",
    85: "にわか雪（弱）",
    86: "にわか雪（強）",
    95: "雷雨",
    96: "雷雨（ひょうを伴う）",
    99: "雷雨（強いひょうを伴う）",
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
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def fetch_json_with_retry(
    url: str,
    timeout: int = 30,
    retries: int = 3,
    backoff_sec: float = 1.5,
    rate_limit_wait_sec: float = 60,
) -> dict:
    """リトライ機能付きJSON取得。429 のときは rate_limit_wait_sec 以上待ってレート制限の回復を待つ。"""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as res:
                return json.loads(res.read().decode("utf-8"))
        except Exception as e:
            last_err = e
            if attempt == retries:
                break
            wait = backoff_sec ** (attempt - 1)
            if isinstance(e, urllib.error.HTTPError) and e.code == 429:
                wait = max(wait, rate_limit_wait_sec)
            print(f"[weather] fetch failed attempt={attempt}/{retries} err={e} -> retry in {wait:.1f}s", file=sys.stderr)
            time.sleep(wait)
    raise last_err


def _fetch_forecast(points: list[tuple[float, float]], query: str, **retry_opts) -> list[dict]:
    """複数地点の予報を1リクエストで取得し、points と同じ順のリストで返す。
    timezone=auto なので、時刻・日付はそれぞれの地点の現地時間で返ってくる。
    """
    lats = ",".join(str(lat) for lat, _ in points)
    lons = ",".join(str(lon) for _, lon in points)
    url = f"{FORECAST_URL}?latitude={lats}&longitude={lons}&{query}&timezone=auto"
    data = fetch_json_with_retry(url, **retry_opts)
    # 1地点のときだけ dict、複数地点のときは list で返ってくる
    return data if isinstance(data, list) else [data]


def get_daily_forecasts(points: list[tuple[float, float]], target_date: date) -> list:
    """各地点の target_date（現地の日付）の天気・最高/最低気温・降水確率を取得する。
    Returns:
        points と同じ順のリスト。その日のデータがない地点は None。
    """
    locations = _fetch_forecast(
        points,
        "daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        "&forecast_days=3",
        timeout=30, retries=3, backoff_sec=2.0,
    )

    forecasts = []
    for loc in locations:
        daily = loc["daily"]
        try:
            idx = daily["time"].index(target_date.isoformat())
        except ValueError:
            forecasts.append(None)
            continue
        code = daily["weather_code"][idx]
        temp_max = daily["temperature_2m_max"][idx]
        temp_min = daily["temperature_2m_min"][idx]
        if code is None or temp_max is None or temp_min is None:
            forecasts.append(None)
            continue
        code = int(code)
        pop = daily["precipitation_probability_max"][idx]
        forecasts.append({
            "code": code,
            "weather": WEATHERCODE_JA.get(code, f"天気コード:{code}"),
            "icon": weather_icon_from_code(code),
            "temp_max": float(temp_max),
            "temp_min": float(temp_min),
            "precip_prob": int(pop) if pop is not None else None,
        })
    return forecasts


# 0:00-7:59 は「翌日（本日）」= その日の9-21時、8:00以降は「翌日」= 翌日の9-21時
MORNING_CUTOFF_HOUR = 8

# 天気APIのレート制限対策：同一地点の結果を短時間キャッシュ（秒）
WEATHER_CACHE_TTL_SECONDS = 300

_weather_cache: dict = {}
_weather_cache_time: dict = {}


def _target_date_and_header(tz: tzinfo) -> tuple:
    """その地点の現在時刻から、表示する日付と冒頭文言を決める。
    Returns:
        (target_date, header_label)
        header_label は "翌日（本日）" または "翌日"
    """
    now = datetime.now(timezone.utc).astimezone(tz)
    if 0 <= now.hour < MORNING_CUTOFF_HOUR:
        return now.date(), "翌日（本日）"
    return now.date() + timedelta(days=1), "翌日"


def get_tomorrow_weather_9_to_21(lat: float, lon: float) -> tuple[list, str, str]:
    """その地点の現在時刻に応じて、本日または翌日の 9,12,15,18,21 時（現地時間）の天気を取得。
    同一 (lat, lon) のAPI応答は WEATHER_CACHE_TTL_SECONDS の間キャッシュしてAPI呼び出しを削減。
    Webhook の返信用なので、リトライは短く切り上げる（reply token が失効する前に返すため）。
    Returns:
        (forecasts, date_label, header_label)
        date_label は日付文字列（表示用）、header_label は "翌日（本日）" または "翌日"
    """
    cache_key = (round(lat, 4), round(lon, 4))
    now_ts = time.monotonic()
    if cache_key in _weather_cache and (now_ts - _weather_cache_time.get(cache_key, 0)) < WEATHER_CACHE_TTL_SECONDS:
        data = _weather_cache[cache_key]
    else:
        data = _fetch_forecast(
            [(lat, lon)],
            "hourly=temperature_2m,precipitation_probability,weather_code&forecast_days=3",
            timeout=10, retries=2, rate_limit_wait_sec=2,
        )[0]
        _weather_cache[cache_key] = data
        _weather_cache_time[cache_key] = now_ts

    local_tz = timezone(timedelta(seconds=data["utc_offset_seconds"]))
    target_date, header_label = _target_date_and_header(local_tz)

    hourly = data["hourly"]
    times = hourly["time"]
    temps = hourly["temperature_2m"]
    pops = hourly.get("precipitation_probability", [])
    codes = hourly["weather_code"]

    forecasts = []
    for h in (9, 12, 15, 18, 21):
        try:
            idx = times.index(f"{target_date.isoformat()}T{h:02d}:00")
        except ValueError:
            continue
        if codes[idx] is None or temps[idx] is None:
            continue
        code = int(codes[idx])
        forecasts.append({
            "time": f"{h:02d}:00",
            "temp": float(temps[idx]),
            "precip_prob": int(pops[idx]) if pops and idx < len(pops) and pops[idx] is not None else None,
            "weather": WEATHERCODE_JA.get(code, f"天気コード:{code}"),
            "code": code,
            "icon": weather_icon_from_code(code),
        })
    return forecasts, format_date_ja(target_date), header_label
