import json
import os
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
import yfinance as yf


def plot_watchlist_charts():
  # 1. watchlist.json の存在チェックと読み込み
  json_file = 'watchlist.json'
  if not os.path.exists(json_file):
    print(
        f'エラー: {json_file} が見つかりません。先にスクリーナーを実行してください。'
    )
    return

  with open(json_file, 'r', encoding='utf-8') as f:
    watchlist = json.load(f)

  if not watchlist:
    print(f'ℹ️ {json_file} に監視対象（買い候補）銘柄が含まれていません。')
    return

  print(f'📊 {len(watchlist)} 銘柄のチャート画像を生成します...\n')

  # 保存先フォルダーの作成
  os.makedirs('charts', exist_ok=True)

  # 2. 銘柄ごとにデータを取得してチャート描画・保存
  for idx, ticker in enumerate(watchlist, 1):
    print(f'[{idx}/{len(watchlist)}] {ticker} のデータを取得中...')

    try:
      # 直近6ヶ月の日足データを取得
      df = yf.download(ticker, period='6mo', progress=False)

      if df.empty or len(df) < 30:
        print(f'  ⚠️ {ticker} のデータが不十分なためスキップします。')
        continue

      # MultiIndexカラムの平坦化処理
      if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

      # ---------------------------------------------------------
      # 指標計算 (ボリンジャーバンド + MACD)
      # ---------------------------------------------------------
      df['SMA20'] = df['Close'].rolling(20).mean()
      df['STD20'] = df['Close'].rolling(20).std()
      df['Upper_Band'] = df['SMA20'] + (df['STD20'] * 2)
      df['Lower_Band'] = df['SMA20'] - (df['STD20'] * 2)

      # MACD (12, 26, 9)
      exp1 = df['Close'].ewm(span=12, adjust=False).mean()
      exp2 = df['Close'].ewm(span=26, adjust=False).mean()
      df['MACD'] = exp1 - exp2
      df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
      df['Hist'] = df['MACD'] - df['Signal']

      # ---------------------------------------------------------
      # mplfinance 用のサブプロット設定
      # ---------------------------------------------------------
      colors = ['red' if v >= 0 else 'green' for v in df['Hist']]

      add_plots = [
          mpf.makeaddplot(df['SMA20'], color='orange', width=1.0),
          mpf.makeaddplot(
              df['Upper_Band'], color='gray', linestyle='--', width=0.8
          ),
          mpf.makeaddplot(
              df['Lower_Band'], color='purple', linestyle='--', width=1.2
          ),
          mpf.makeaddplot(df['MACD'], panel=2, color='blue', width=1.0),
          mpf.makeaddplot(df['Signal'], panel=2, color='orange', width=1.0),
          mpf.makeaddplot(
              df['Hist'], type='bar', panel=2, color=colors, alpha=0.5
          ),
      ]

      mc = mpf.make_marketcolors(
          up='red', down='green', edge='inherit', wick='inherit', volume='inherit'
      )
      style = mpf.make_mpf_style(marketcolors=mc, gridstyle=':')

      last_close = df['Close'].iloc[-1]
      lower_band = df['Lower_Band'].iloc[-1]

      # 保存先ファイル名
      save_path = f"charts/{ticker.replace('.T', '')}_chart.png"

      # 描画 & ファイルへ保存 (savefig)
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
          savefig=save_path,  # 🔥 画面表示ではなくファイル保存にする
      )

      print(f'  ✅ 画像保存完了: {save_path}')

    except Exception as e:
      print(f'  ❌ {ticker} の描画中にエラーが発生しました: {e}')
      continue

  print('\n全銘柄のチャート画像生成が完了しました。')


if __name__ == '__main__':
  plot_watchlist_charts()
