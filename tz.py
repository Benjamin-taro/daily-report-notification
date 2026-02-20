from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pytz

# 主要都市のタイムゾーンマッピング
CITY_TIMEZONES = {
    "横浜": "Asia/Tokyo",
    "松山": "Asia/Tokyo",
    "鹿児島": "Asia/Tokyo",
    "秋田": "Asia/Tokyo",
    "Tokyo": "Asia/Tokyo",
    "Glasgow": "Europe/London",
    "London": "Europe/London",
    "New York": "America/New_York",
    "Los Angeles": "America/Los_Angeles",
    "Paris": "Europe/Paris",
    "Berlin": "Europe/Berlin",
    "Sydney": "Australia/Sydney",
    "Shanghai": "Asia/Shanghai",
    "Seoul": "Asia/Seoul",
    "Bangkok": "Asia/Bangkok",
    "Singapore": "Asia/Singapore",
    "Dubai": "Asia/Dubai",
    "Moscow": "Europe/Moscow",
    "Mumbai": "Asia/Kolkata",
}

def get_timezone_for_city(city_name: str) -> str:
    """都市名からタイムゾーンを取得"""
    # 完全一致を優先
    if city_name in CITY_TIMEZONES:
        return CITY_TIMEZONES[city_name]
    
    # 部分一致を試す（大文字小文字を無視）
    city_lower = city_name.lower()
    for key, tz in CITY_TIMEZONES.items():
        if key.lower() == city_lower or city_lower in key.lower() or key.lower() in city_lower:
            return tz
    
    # デフォルトは日本時間
    return "Asia/Tokyo"

def calculate_timezone_difference(from_tz: str, to_tz: str) -> tuple[int, str]:
    """
    2つのタイムゾーン間の時差を計算
    
    Returns:
        (時差（時間）, 説明文字列)
    """
    try:
        from_zone = ZoneInfo(from_tz)
        to_zone = ZoneInfo(to_tz)
    except Exception:
        # ZoneInfoで取得できない場合はpytzを試す
        try:
            from_zone = pytz.timezone(from_tz)
            to_zone = pytz.timezone(to_tz)
        except Exception:
            return (0, "タイムゾーンが取得できませんでした")
    
    now_utc = datetime.now(timezone.utc)
    from_time = now_utc.astimezone(from_zone)
    to_time = now_utc.astimezone(to_zone)
    
    # 時差を計算（秒単位）
    offset_diff = (to_time.utcoffset() - from_time.utcoffset()).total_seconds()
    hours_diff = int(offset_diff / 3600)
    
    if hours_diff == 0:
        diff_str = "時差なし"
    elif hours_diff > 0:
        diff_str = f"+{hours_diff}時間"
    else:
        diff_str = f"{hours_diff}時間"
    
    return (hours_diff, diff_str)

def get_current_time_in_timezone(tz_str: str) -> str:
    """指定されたタイムゾーンの現在時刻を取得（ISO風）"""
    try:
        tz = ZoneInfo(tz_str)
    except Exception:
        try:
            tz = pytz.timezone(tz_str)
        except Exception:
            return "時刻を取得できませんでした"

    now = datetime.now(timezone.utc).astimezone(tz)
    return now.strftime("%Y-%m-%d %H:%M:%S %Z")


# 曜日（日本語）
WEEKDAY_JA = ["月", "火", "水", "木", "金", "土", "日"]


def format_datetime_ja(tz_str: str) -> str:
    """指定タイムゾーンの現在時刻を「何年何月何日 (曜) 何時」形式で返す。"""
    try:
        tz = ZoneInfo(tz_str)
    except Exception:
        try:
            tz = pytz.timezone(tz_str)
        except Exception:
            return "—"
    now = datetime.now(timezone.utc).astimezone(tz)
    w = now.weekday()  # 0=月曜
    return f"{now.year}年{now.month}月{now.day}日 ({WEEKDAY_JA[w]}) {now.hour:02d}:{now.minute:02d}"
