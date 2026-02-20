"""
Open-Meteo Geocoding API で地名・郵便番号を緯度経度・タイムゾーンに変換する。
Webhookの時差計算・天気で任意の場所名入力に対応するために使用する。
"""
import urllib.parse
from typing import Optional, List, Dict, Any

from weather import fetch_json_with_retry

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"


def search_place(query: str, count: int = 5, language: str = "ja") -> List[Dict[str, Any]]:
    """
    地名または郵便番号で検索し、候補リストを返す。
    
    Args:
        query: 検索文字列（2文字以上。3文字以上でファジー検索）
        count: 返す件数（最大100）
        language: 結果の言語（ja / en など）
    
    Returns:
        [{"name", "latitude", "longitude", "timezone", "country", "admin1", ...}, ...]
        見つからない場合は空リスト。
    """
    query = (query or "").strip()
    if len(query) < 2:
        return []

    params = {
        "name": query,
        "count": min(max(1, count), 100),
        "language": language,
    }
    qs = urllib.parse.urlencode(params)
    url = f"{GEOCODE_URL}?{qs}"

    try:
        data = fetch_json_with_retry(url, timeout=10, retries=2)
    except Exception:
        return []

    results = data.get("results") or []
    out = []
    for r in results:
        out.append({
            "name": r.get("name", ""),
            "latitude": float(r.get("latitude", 0)),
            "longitude": float(r.get("longitude", 0)),
            "timezone": r.get("timezone", "UTC"),
            "country": r.get("country", ""),
            "country_code": r.get("country_code", ""),
            "admin1": r.get("admin1", ""),
        })
    return out


def resolve_place(query: str, language: str = "ja") -> Optional[Dict[str, Any]]:
    """
    地名を1件解決する。候補の先頭を返す。
    日報ブロードキャスト用の固定都市リストは使わず、Webhook用に任意入力から取得する。
    
    Returns:
        {"name", "lat", "lon", "timezone", "display_name"} または None
    """
    candidates = search_place(query, count=1, language=language)
    if not candidates:
        return None

    c = candidates[0]
    # 表示名: 国や地域があれば付ける
    parts = [c["name"]]
    if c.get("admin1") and c["admin1"] != c["name"]:
        parts.append(c["admin1"])
    if c.get("country"):
        parts.append(c["country"])
    display_name = ", ".join(parts)

    return {
        "name": c["name"],
        "lat": c["latitude"],
        "lon": c["longitude"],
        "timezone": c["timezone"],
        "display_name": display_name,
    }
