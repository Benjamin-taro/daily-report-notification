"""
日報リマインドに添える「明日は何の日」を作る。
材料は日本語版ウィキペディアの日付ページ（記念日・年中行事／できごと）から取り、
Claude Code（非対話モード）にその中から1つ選んで紹介文を書かせる。
GitHub Actions では CLAUDE_CODE_OAUTH_TOKEN（`claude setup-token` で発行）で認証し、サブスクの枠で動く。
材料が取れない、claude コマンドがない、生成に失敗した、のいずれでも None を返し、配信はこの欄なしで続ける。
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import date
from typing import Optional

MODEL = "sonnet"
TIMEOUT_SECONDS = 90

WIKIPEDIA_API_URL = "https://ja.wikipedia.org/w/api.php"
# ウィキペディアは User-Agent のないリクエストを拒否する
USER_AGENT = "daily-report-notification/1.0 (https://github.com/Benjamin-taro/daily-report-notification)"
# 材料にする節と、Claude に渡す最大文字数
SECTIONS = {"記念日・年中行事": 3000, "できごと": 4000}

SYSTEM_PROMPT = """\
親しい友人3人に毎晩届くLINE通知の「明日は何の日」欄を書いてください。

渡される材料（日本語版ウィキペディアのその日のページ）から、いちばん「へえ」と思える、\
誰かに話したくなるものをひとつだけ選びます。記念日でも、過去のできごとでも構いません。\
戦争・事故・災害・事件のような重い話題は選びません。語呂合わせの記念日は、こじつけ具合が面白いものなら歓迎です。

次の2つを、改行で分けて書きます。

全体を、やわらかい「です・ます」調で書きます。

1行目は事実です。「明日（○月○日）は〜の日です。」のように何の日かを言い切る文で始め、由来をひとこと添えます（70文字以内）。\
材料に書かれていない事実、年、数字を足してはいけません。

2行目はあなたからのひとことです（50文字以内）。その日にちなんで思いついたことを、隣でふとつぶやくように添えます。\
中身は、明日やってみたら楽しそうなこと、こうなったらいいなという願い、その日らしい光景の想像、\
自分ならこうしそうだという打ち明け話など、その日の題材にいちばん合うものを選んでください。少しふざけても構いません。

大事なのは距離感です。読む人は一日を終えて疲れているので、やるかどうかは完全に読む人の自由で、\
聞き流しても何も困らない、という軽さにします。指示された・急かされた・答えを求められたと感じさせる言い方\
（命令、呼びかけ、問いかけ）は避けます。

語尾は決まった型にせず、その文の内容から自然に出てくる形にしてください。毎晩届く欄なので、\
いつも同じ言い回しで終わると飽きられます。

誰でも思いつく無難な内容（「大切にしよう」「感謝しよう」など）ではなく、その日ならではの具体的な一言にします。\
「今年で○年目」のような年数の計算や、新しい数字・事実はここにも書きません。

出力は本文の2行だけにしてください。見出し、前置き、挨拶、絵文字は付けません。"""


def fetch_day_material(target_date: date) -> Optional[str]:
    """日本語版ウィキペディアの日付ページから、記念日とできごとの節を取り出す。"""
    params = {
        "action": "query",
        "prop": "extracts",
        "explaintext": 1,
        "titles": f"{target_date.month}月{target_date.day}日",
        "redirects": 1,
        "format": "json",
        "formatversion": 2,
    }
    req = urllib.request.Request(
        f"{WIKIPEDIA_API_URL}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=15) as res:
        data = json.loads(res.read().decode("utf-8"))
    text = data["query"]["pages"][0].get("extract") or ""

    # "== 見出し ==" で区切って {見出し: 本文} にする
    parts = re.split(r"\n== (.+?) ==\n", "\n" + text)
    sections = dict(zip(parts[1::2], parts[2::2]))

    blocks = []
    for name, limit in SECTIONS.items():
        body = sections.get(name, "").strip()
        if body:
            blocks.append(f"## {name}\n{body[:limit]}")
    return "\n\n".join(blocks) or None


def generate_tomorrow_note(target_date: date) -> Optional[str]:
    """target_date（明日）が何の日かを紹介する短い文を生成する。"""
    claude = shutil.which("claude")
    if not claude:
        return None

    try:
        material = fetch_day_material(target_date)
        if not material:
            raise RuntimeError("no material on Wikipedia")
        prompt = f"明日は{target_date.month}月{target_date.day}日です。\n\n{material}"

        # 文章を1つ書くだけなので、ツール・スキル・プロジェクト設定は使わせない
        with tempfile.TemporaryDirectory() as workdir:
            result = subprocess.run(
                [
                    claude, "-p", prompt,
                    "--system-prompt", SYSTEM_PROMPT,
                    "--model", MODEL,
                    "--tools", "",
                    "--disable-slash-commands",
                    "--no-session-persistence",
                ],
                cwd=workdir,
                # 標準入力がつながっていると、claude がその中身までプロンプトとして読んでしまう
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
            )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()[:300]
            raise RuntimeError(f"claude exit={result.returncode} {detail}")
        return result.stdout.strip() or None
    except Exception as e:
        # この欄は添え物なので、失敗しても配信は止めない
        print(f"[comment] failed err={e}", file=sys.stderr)
        return None
