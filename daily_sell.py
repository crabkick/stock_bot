import json
import os
import pandas as pd
import requests
import yfinance as yf

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1569541009053065348/atvAS9slaGCq2yED1AUkpJ3lpFVK1Um1NW6CvrOkGCUQSyZif75cMOItpLchx2PoPsn"


def monitor_watchlist():
  if not os.path.exists('watchlist.json'):
    print('watchlist.json が存在しません。処理を終了します。')
    return

  with open('watchlist.json', 'r', encoding='utf-8') as f:
    watchlist = json.load(f)

  if not watchlist:
    print('現在、監視対象の銘柄はありません。')
    return

  print(f'監視中銘柄数: {len(watchlist)} 件')

  sell_notifications = []
  remaining_watchlist = watchlist.copy()

  for ticker in watchlist:
    try:
      df = yf.download(ticker, period='6mo', progress=False)
      if df.empty or len(df) < 30:
        continue

      if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

      # 指標計算
      df['SMA20'] = df['Close'].rolling(20).mean()
      df['STD20'] = df['Close'].rolling(20).std()
      df['Upper_Band'] = df['SMA20'] + (df['STD20'] * 2)

      exp1 = df['Close'].ewm(span=12, adjust=False).mean()
      exp2 = df['Close'].ewm(span=26, adjust=False).mean()
      df['MACD'] = exp1 - exp2
      df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
      df['Hist'] = df['MACD'] - df['Signal']

      last_close = df['Close'].iloc[-1]
      upper_band = df['Upper_Band'].iloc[-1]
      prev_hist = df['Hist'].iloc[-2]
      last_hist = df['Hist'].iloc[-1]

      # 売り条件: 上限到達 & MACDヒストグラム下降転換
      if (last_close >= upper_band) and (last_hist < prev_hist):
        msg = f'🔴 **【売り・手仕舞いサイン】** {ticker} (終値: {last_close:.1f}円)'
        print(msg)
        sell_notifications.append(msg)
        # 手仕舞い条件を満たした銘柄はリストから外す
        remaining_watchlist.remove(ticker)

    except Exception as e:
      print(f'Error monitoring {ticker}: {e}')

  # Discordへ通知送信
  if sell_notifications and DISCORD_WEBHOOK_URL:
    notification = '📊 **本日の利確・手仕舞い判定レポート**\n' + '\n'.join(
        sell_notifications
    )
    requests.post(DISCORD_WEBHOOK_URL, json={'content': notification})

  # 更新されたリストを保存（売りが出た銘柄は除外される）
  with open('watchlist.json', 'w', encoding='utf-8') as f:
    json.dump(remaining_watchlist, f, ensure_ascii=False, indent=2)

  print('監視処理が正常に完了しました。')


if __name__ == '__main__':
  monitor_watchlist()
