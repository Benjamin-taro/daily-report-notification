"""
Claude Code（非対話モード）で、日報リマインドに添える一言を生成する。
GitHub Actions では CLAUDE_CODE_OAUTH_TOKEN（`claude setup-token` で発行）で認証し、サブスクの枠で動く。
claude コマンドがない、または生成に失敗したときは None を返し、配信は一言なしで続ける。
"""
import json
import shutil
import subprocess
import sys
import tempfile
from typing import Optional

MODEL = "sonnet"
TIMEOUT_SECONDS = 90

SYSTEM_PROMPT = """\
日報の投稿を促すLINE通知に添える一言を書いてください。

読むのは Glasgow・秋田・さいたまに住む親しい3人です。通知は日本時間の21時ごろに届くので、\
日本の2人は一日の終わりに、Glasgow の1人は現地の昼ごろに読みます。

渡される明日の日付と各都市の天気予報から話題をひとつ選び、友人に話しかける口調で、\
60文字以内の1文にまとめてください。都市どうしの違いや、曜日・季節に触れるのも歓迎です。
予報の数字は一言のすぐ上に載っているので、3都市の天気を並べ直すのではなく、\
いちばん目を引く点ひとつに絞って、感想や声かけにしてください。

出力はその1文だけにしてください。挨拶、日報への言及、「おやすみ」のような時間帯を決めつける言葉は入れません\
（挨拶と日報の案内は通知の別の部分にあります）。絵文字は使っても1つまでです。"""


def generate_comment(date_label: str, forecasts: list[dict]) -> Optional[str]:
    """明日の日付と各都市の予報から、通知に添える一言を生成する。"""
    claude = shutil.which("claude")
    if not claude:
        return None

    payload = {
        "明日": date_label,
        "予報": [
            {
                "都市": f["name"],
                "天気": f["weather"],
                "最高気温": round(f["temp_max"]),
                "最低気温": round(f["temp_min"]),
                "降水確率": f["precip_prob"],
            }
            for f in forecasts
        ],
    }

    try:
        # 文章を1つ書くだけなので、ツール・スキル・プロジェクト設定は使わせない
        with tempfile.TemporaryDirectory() as workdir:
            result = subprocess.run(
                [
                    claude, "-p", json.dumps(payload, ensure_ascii=False),
                    "--system-prompt", SYSTEM_PROMPT,
                    "--model", MODEL,
                    "--tools", "",
                    "--disable-slash-commands",
                    "--no-session-persistence",
                ],
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
            )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()[:300]
            raise RuntimeError(f"claude exit={result.returncode} {detail}")
        return result.stdout.strip() or None
    except Exception as e:
        # 一言は添え物なので、失敗しても配信は止めない
        print(f"[comment] failed err={e}", file=sys.stderr)
        return None
