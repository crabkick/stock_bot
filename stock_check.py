import json
import os
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
import requests
import yfinance as yf

# GitHub Secrets から環境変数として取得
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')


def send_image_to_discord(filepath, content=''):
  """Discord Webhook経由で画像ファイルを送信する"""
  if not DISCORD_WEBHOOK_URL:
    print('⚠️ DISCORD_WEBHOOK_URL が設定されていません。')
    return

  with open(filepath, 'rb') as f:
    files = {'file': f}
    payload = {'content': content}
    response = requests.post(
        DISCORD_WEBHOOK_URL, data=payload, files=files
    )

  if response.status_code in (200, 204):
    print(f'  ✉️ Discord送信成功: {filepath}')
  else:
    print(f'  ⚠️ Discord送信失敗 ({response.status_code}): {response.text}')


def plot_watchlist_charts():
  json_file = 'watchlist.json'
  if not os.path.exists(json_file):
    print(f'エラー: {json_file} が見つかりません。')
    return

  with open(json_file, 'r', encoding='utf-8') as f:
    watchlist = json.load(f)

  if not watchlist:
    print(f'ℹ️ {json_file} に監視対象銘柄が含まれていません。')
    return

  print(f'📊 {len(watchlist)} 銘柄のチャート画像を生成・送信します...\n')
  os.makedirs('charts', exist_ok=True)

  for idx, ticker in enumerate(watchlist, 1):
    print(f'[{idx}/{len(watchlist)}] {ticker} のデータを取得中...')

    try:
      df = yf.download(ticker, period='2mo', progress=False)

      if df.empty or len(df) < 30:
        print(f'  ⚠️ {ticker} のデータが不十分なためスキップします。')
        continue

      if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

      # ---------------------------------------------------------
      # 指標計算
      # ---------------------------------------------------------
      df['SMA20'] = df['Close'].rolling(20).mean()
      df['STD20'] = df['Close'].rolling(20).std()
      df['Upper_Band'] = df['SMA20'] + (df['STD20'] * 2)
      df['Lower_Band'] = df['SMA20'] - (df['STD20'] * 2)

      exp1 = df['Close'].ewm(span=12, adjust=False).mean()
      exp2 = df['Close'].ewm(span=26, adjust=False).mean()
      df['MACD'] = exp1 - exp2
      df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
      df['Hist'] = df['MACD'] - df['Signal']

      colors = ['red' if v >= 0 else 'green' for v in df['Hist']]

      add_plots = [
          mpf.make_addplot(df['SMA20'], color='orange', width=1.0),
          mpf.make_addplot(
              df['Upper_Band'], color='gray', linestyle='--', width=0.8
          ),
          mpf.make_addplot(
              df['Lower_Band'], color='purple', linestyle='--', width=1.2
          ),
          mpf.make_addplot(df['MACD'], panel=2, color='blue', width=1.0),
          mpf.make_addplot(df['Signal'], panel=2, color='orange', width=1.0),
          mpf.make_addplot(
              df['Hist'], type='bar', panel=2, color=colors, alpha=0.5
          ),
      ]

      mc = mpf.make_marketcolors(
          up='red', down='green', edge='inherit', wick='inherit', volume='inherit'
      )
      style = mpf.make_mpf_style(marketcolors=mc, gridstyle=':')

      last_close = df['Close'].iloc[-1]
      save_path = f"charts/{ticker.replace('.T', '')}_chart.png"

      mpf.plot(
          df,
          type='candle',
          volume=True,
          addplot=add_plots,
          style=style,
          title=f'\nStock: {ticker} (Close: {last_close:.1f} JPY)',
          figratio=(12, 7),
          figscale=1.1,
          panel_ratios=(3, 1, 1.5),
          savefig=save_path,
      )

      # 生成した画像をDiscordへ直ちに送信
      send_image_to_discord(
          save_path,
          content=f'📈 **{ticker}** チャート画像 (終値: {last_close:.1f}円)',
      )

    except Exception as e:
      print(f'  ❌ {ticker} の処理中にエラーが発生しました: {e}')
      continue

  print('\n全銘柄の処理が完了しました。')


if __name__ == '__main__':
  plot_watchlist_charts()
