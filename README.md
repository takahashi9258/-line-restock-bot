# イオンスタイルオンライン Discord入荷通知Bot

4つのオンラインショップを60秒ごとに監視し、Discordへ通知します。

## 監視対象

- イオンスタイルオンライン（サイト待機列を含む）
- あみあみ
- Joshin web
- トイザらスオンライン

各ショップで次のカード商品を監視します。

- ポケモンカード全商品
- ONE PIECEカード全商品
- ドラゴンボールカード全商品

初回起動時は現在の状態を記録するだけで、既存商品を大量通知しません。その後、販売可能へ変化した商品を通知します。

## Discord通知内容

- 商品カテゴリー
- 商品名
- 価格（ページから取得できた場合）
- 商品ページURL
- 検知時刻

## Render設定

- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn main:app --workers 1 --threads 2 --timeout 120`
- Health Check Path: `/`
- Instance Type: Starter（常時稼働、月7ドル）

### Environment Variables

- `DISCORD_WEBHOOK_URL`: Discordで作成した秘密のWebhook URL
- `CHECK_INTERVAL_SECONDS`: `60`
- `PRODUCT_SCAN_SECONDS`: `60`
- `MONITOR_ENABLED`: `true`

Webhook URLはGitHubへ書き込まず、Renderの環境変数だけに保存してください。
