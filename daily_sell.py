import json
import os
import pandas as pd
import requests
import yfinance as yf

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# 損切りラインの設定（例: -5.0% で損切り判定）
STOP_LOSS_THRESHOLD = -0.05  # -5% (買値管理をしていない場合はボリバン下限ブレイク等で判定)


def send_discord(msg):
  """Discord送信用の共通関数"""
  if DISCORD_WEBHOOK_URL:
    try:
      res = requests.post(
          DISCORD_WEBHOOK_URL, json={"content": msg}, timeout=10
      )
      res.raise_for_status()
    except Exception as e:
      print(f"Discord通知エラー: {e}")
  else:
    print(
        "DISCORD_WEBHOOK_URL が設定されていないため、通知をスキップしました。"
    )


def monitor_watchlist():
  if not os.path.exists("watchlist.json"):
    msg = "⚠️ `watchlist.json` が見つかりませんでした。手動スクリーニングを先に実行してください。"
    print(msg)
    send_discord(msg)
    return

  with open("watchlist.json", "r", encoding="utf-8") as f:
    watchlist = json.load(f)

  if not watchlist:
    msg = "ℹ️ 現在、監視対象の銘柄はありません。"
    print(msg)
    send_discord(msg)
    return

  print(f"監視中銘柄数: {len(watchlist)} 件")

  sell_notifications = []
  stop_loss_notifications = []
  remaining_watchlist = watchlist.copy()

  for ticker in watchlist:
    try:
      df = yf.download(ticker, period="6mo", progress=False)
      if df.empty or len(df) < 30:
        continue

      if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

      # 指標計算 (ボリンジャーバンド + MACD)
      df["SMA20"] = df["Close"].rolling(20).mean()
      df["STD20"] = df["Close"].rolling(20).std()
      df["Upper_Band"] = df["SMA20"] + (df["STD20"] * 2)
      df["Lower_Band"] = df["SMA20"] - (df["STD20"] * 2)

      exp1 = df["Close"].ewm(span=12, adjust=False).mean()
      exp2 = df["Close"].ewm(span=26, adjust=False).mean()
      df["MACD"] = exp1 - exp2
      df["Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
      df["Hist"] = df["MACD"] - df["Signal"]

      last_close = df["Close"].iloc[-1]
      upper_band = df["Upper_Band"].iloc[-1]
      lower_band = df["Lower_Band"].iloc[-1]
      prev_hist = df["Hist"].iloc[-2]
      last_hist = df["Hist"].iloc[-1]

      # 1. 🟢 利確・手仕舞い条件: 上限到達 & MACDヒストグラム下降転換
      if (last_close >= upper_band) and (last_hist < prev_hist):
        msg = f"🔴 **【利確・手仕舞いサイン】** `{ticker}` (終値: {last_close:.1f}円)"
        print(msg)
        sell_notifications.append(msg)
        remaining_watchlist.remove(ticker)

      # 2. ⚠️ 損切り条件: ボリバン下限を大幅更新(-3%以上下振れ) ＋ MACDデッドクロス/拡大
      # (※直近で底抜けして下降トレンドが加速した場合のロスカット判定)
      elif (last_close < lower_band * 0.97) and (last_hist < prev_hist):
        msg = f"💀 **【損切り・ロスカットサイン】** `{ticker}` (終値: {last_close:.1f}円 / 下限割れ)"
        print(msg)
        stop_loss_notifications.append(msg)
        remaining_watchlist.remove(ticker)

    except Exception as e:
      print(f"Error monitoring {ticker}: {e}")

  # 4. 通知文の作成（利確・損切り・平常時）
  watchlist_str = ", ".join([f"`{t}`" for t in watchlist])
  all_action_notifs = sell_notifications + stop_loss_notifications

  if all_action_notifs:
    notification = (
        "📊 **【本日の売買判定レポート】**\n"
        + "\n".join(all_action_notifs)
        + f"\n\n残りの監視対象: {len(remaining_watchlist)} 銘柄"
    )
  else:
    notification = (
        "✅ **【日次株価チェック完了】**\n"
        "本日、利確・損切り条件を満たした銘柄はありませんでした。\n"
        f"・監視中銘柄数: {len(watchlist)}件 ({watchlist_str})"
    )

  # Discordへ通知送信
  send_discord(notification)

  # 更新されたリストを保存（利確・損切りされた銘柄を除外）
  with open("watchlist.json", "w", encoding="utf-8") as f:
    json.dump(remaining_watchlist, f, ensure_ascii=False, indent=2)

  print("監視処理および通知完了。")


if __name__ == "__main__":
  monitor_watchlist()
