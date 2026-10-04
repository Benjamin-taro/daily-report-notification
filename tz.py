from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

# 曜日（日本語）
WEEKDAY_JA = ["月", "火", "水", "木", "金", "土", "日"]


def format_date_ja(d: date) -> str:
    """日付を「何年何月何日(曜)」形式で返す。"""
    return f"{d.year}年{d.month}月{d.day}日({WEEKDAY_JA[d.weekday()]})"


def format_timezone_difference(from_tz: str, to_tz: str) -> str:
    """2つのタイムゾーン間の現在の時差を「+8時間」「-3時間30分」のような文字列で返す。"""
    try:
        from_zone = ZoneInfo(from_tz)
        to_zone = ZoneInfo(to_tz)
    except Exception:
        return "タイムゾーンが取得できませんでした"

    now_utc = datetime.now(timezone.utc)
    diff = now_utc.astimezone(to_zone).utcoffset() - now_utc.astimezone(from_zone).utcoffset()
    minutes = int(diff.total_seconds() // 60)

    if minutes == 0:
        return "時差なし"
    sign = "+" if minutes > 0 else "-"
    hours, rest = divmod(abs(minutes), 60)
    if rest:
        return f"{sign}{hours}時間{rest}分"
    return f"{sign}{hours}時間"


def format_datetime_ja(tz_str: str) -> str:
    """指定タイムゾーンの現在時刻を「何年何月何日 (曜) 何時」形式で返す。"""
    try:
        tz = ZoneInfo(tz_str)
    except Exception:
        return "—"
    now = datetime.now(timezone.utc).astimezone(tz)
    w = now.weekday()  # 0=月曜
    return f"{now.year}年{now.month}月{now.day}日 ({WEEKDAY_JA[w]}) {now.hour:02d}:{now.minute:02d}"
