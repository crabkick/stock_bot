import glob
import json
import os
import pandas as pd
import requests
import yfinance as yf

DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')


def send_discord_notification(message):
  """Discord Webhook経由でテキスト通知を送信する"""
  if not DISCORD_WEBHOOK_URL:
    print('⚠️ DISCORD_WEBHOOK_URL が設定されていないため通知をスキップします。')
    return

  payload = {'content': message}
  try:
    res = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    if res.status_code in (200, 204):
      print('✉️ Discordへ通知を送信しました。')
    else:
      print(f'⚠️ Discord通知エラー ({res.status_code}): {res.text}')
  except Exception as e:
    print(f'⚠️ Discord通信例外: {e}')


def get_latest_csv():
  """フォルダー内の最新の japan_stocks_list_*.csv を自動検索する"""
  files = glob.glob('japan_stocks_list_*.csv')
  if not files:
    return None
  return sorted(files)[-1]


def run_manual_screener():
  # 1. CSVファイルの読み込み
  csv_file = get_latest_csv()
  if not csv_file:
    err_msg = '❌ **【週次スクリーナーエラー】**\n銘柄リストCSVが見つかりませんでした。'
    print(err_msg)
    send_discord_notification(err_msg)
    return

  print(f'使用するファイル: {csv_file}')
  df_all = pd.read_csv(csv_file)
  target_tickers = df_all['Ticker'].dropna().tolist()

  total_count = len(target_tickers)
  print(
      f'全銘柄スクリーニング開始（出来高フィルター適用）: 合計 {total_count} 銘柄'
  )

  new_buy_candidates = []

  # 2. 全銘柄のループ処理判定
  for idx, ticker in enumerate(target_tickers, 1):
    if idx % 100 == 0 or idx == total_count:
      print(
          f'進捗: {idx}/{total_count} 銘柄完了 ('
          f'現在の買い候補: {len(new_buy_candidates)}件)...'
      )

    try:
      df = yf.download(ticker, period='6mo', progress=False)
      if df.empty or len(df) < 30:
        continue

      if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

      # 出来高・売買代金フィルター（低流動性株の除外）
      avg_volume_20 = df['Volume'].rolling(20).mean().iloc[-1]
      if avg_volume_20 < 10000:
        continue

      last_volume = df['Volume'].iloc[-1]
      last_close = df['Close'].iloc[-1]
      if (last_close * last_volume) < 5000000:
        continue

      # ボリンジャーバンド計算 (20日, 2σ)
      df['SMA20'] = df['Close'].rolling(20).mean()
      df['STD20'] = df['Close'].rolling(20).std()
      df['Lower_Band'] = df['SMA20'] - (df['STD20'] * 2)

      # MACD計算 (12, 26, 9)
      exp1 = df['Close'].ewm(span=12, adjust=False).mean()
      exp2 = df['Close'].ewm(span=26, adjust=False).mean()
      df['MACD'] = exp1 - exp2
      df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
      df['Hist'] = df['MACD'] - df['Signal']

      lower_band = df['Lower_Band'].iloc[-1]
      prev_hist = df['Hist'].iloc[-2]
      last_hist = df['Hist'].iloc[-1]

      # 買い判定条件
      if (last_close <= lower_band) and (last_hist > prev_hist):
        print(
            f'🟢 買いシグナル検出: {ticker} (終値: {last_close:.1f}円,'
            f' 20日平均出来高: {int(avg_volume_20):,}株)'
        )
        new_buy_candidates.append(ticker)

    except Exception:
      continue

  # 3. 既存の watchlist.json とのマージ（自動統合）処理
  output_json = 'watchlist.json'
  existing_watchlist = []

  if os.path.exists(output_json):
    try:
      with open(output_json, 'r', encoding='utf-8') as f:
        existing_watchlist = json.load(f)
      print(
          f'\n既存の {output_json} から {len(existing_watchlist)} 銘柄を読み込みました。'
      )
    except Exception as e:
      print(f'既存ファイル読み込みエラー (新規作成します): {e}')

  # 新規追加分のみを抽出（通知用）
  actually_added = [
      t for t in new_buy_candidates if t not in existing_watchlist
  ]

  # 結合（重複除去）
  merged_watchlist = list(
      dict.fromkeys(existing_watchlist + new_buy_candidates)
  )

  with open(output_json, 'w', encoding='utf-8') as f:
    json.dump(merged_watchlist, f, ensure_ascii=False, indent=2)

  added_count = len(actually_added)
  print('\n=== スクリーニング & マージ完了 ===')
  print(f'・今回新規検出: {len(new_buy_candidates)} 銘柄')
  print(f'・新規追加分: {added_count} 銘柄（重複除外済み）')
  print(f'・最終監視対象: {len(merged_watchlist)} 銘柄')

  # 4. Discord への完了通知（0件でも必ず送信）
  if added_count > 0:
    added_str = ', '.join(actually_added)
    discord_msg = (
        f'🟢 **【週次買いスクリーニング完了】**\n'
        f'・新規追加: **{added_count} 銘柄** (`{added_str}`)\n'
        f'・現在の総監視銘柄数: **{len(merged_watchlist)} 銘柄**\n'
        f'・監視リスト: `{merged_watchlist}`'
    )
  else:
    discord_msg = (
        f'⚪ **【週次買いスクリーニング完了】**\n'
        f'・新規追加: **0 銘柄**（条件合致なし・または既存リストと重複）\n'
        f'・現在の総監視銘柄数: **{len(merged_watchlist)} 銘柄**\n'
        f'・監視リスト: `{merged_watchlist}`'
    )

  send_discord_notification(discord_msg)


if __name__ == '__main__':
  run_manual_screener()
