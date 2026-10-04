# daily-report-notification

毎晩 21 時ごろ（日本時間）に、日報の投稿を促す LINE 通知を配信する。通知には Glasgow・秋田・さいたまの翌日の天気と、Claude が天気から書く一言が付く。

あわせて、LINE のトークで時差計算と天気検索に答える Webhook アプリも含む。

## 構成

| ファイル | 役割 |
| --- | --- |
| `daily_broadcast.py` | 毎晩の配信。天気とリマインド文を組み立てて送る |
| `comment.py` | Claude Code を非対話モードで呼び、一言コメントを生成する |
| `weather.py` | Open-Meteo から予報を取得する |
| `line_client.py` | LINE Messaging API のクライアント |
| `webhook_app.py` | 時差計算・天気検索の Webhook（FastAPI） |
| `geocode.py` / `tz.py` / `state_store.py` | Webhook 用の地名検索、時刻の整形、会話状態の保持 |

## 毎晩の配信

GitHub Actions の `LINE Broadcast` ワークフローが `daily_broadcast.py` を実行する。起動は cron-job.org から 20:55 に `workflow_dispatch` で行い、GitHub の `schedule`（21:05 と 21:35）は保険として残している。

同じ日に 2 回配信されることはない。配信リクエストには日付（日本時間）から決まる `X-Line-Retry-Key` を付けていて、2 回目以降は LINE 側が 409 で弾く。その日のうちに本番配信をやり直したい場合も弾かれるので、確認にはテストモードを使う。

天気は各都市の現地の日付で「明日」の予報を出す。3 都市ぶんを 1 リクエストで取得し、失敗した場合は天気なしでリマインドだけを送る。

### 必要なシークレット

| 名前 | 必須 | 用途 |
| --- | --- | --- |
| `LINE_CHANNEL_ACCESS_TOKEN` | 必須 | LINE への配信 |
| `CLAUDE_CODE_OAUTH_TOKEN` | 任意 | 一言コメントの生成。`claude setup-token` で発行する（Claude のサブスクの枠で動く）。未設定・期限切れ・生成失敗なら、一言なしで配信する |

### ローカルでの確認

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # Webhook アプリ用。配信だけなら標準ライブラリで動く

# 送信せずにメッセージの JSON だけ確認する
python daily_broadcast.py --dry-run

# 自分だけに送る
LINE_CHANNEL_ACCESS_TOKEN=... LINE_TEST_MODE=true TEST_LINE_USER_ID=... python daily_broadcast.py
```

都市を変えるときは `daily_broadcast.py` の `CITIES` を、一言の口調を変えるときは `comment.py` の `SYSTEM_PROMPT` を編集する。

## Webhook アプリ

「メニュー」と送ると、時差計算と天気検索を選べる。地名は Open-Meteo の Geocoding API で解決し、天気は検索した地点の現地時間で 9・12・15・18・21 時の予報を返す。

```bash
cp .env.example .env   # LINE_CHANNEL_ACCESS_TOKEN と LINE_CHANNEL_SECRET を設定
python webhook_app.py  # http://localhost:8000/webhook
```

会話の状態はメモリ上に持つので、プロセスを再起動すると消える。
