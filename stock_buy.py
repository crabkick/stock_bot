import glob
import json
import os
import pandas as pd
import yfinance as yf


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
    print(
        'エラー: 銘柄リストCSVが見つかりません。先にJPX取得スクリプトを実行してください。'
    )
    return

  print(f'使用するファイル: {csv_file}')
  df_all = pd.read_csv(csv_file)
  target_tickers = df_all['Ticker'].dropna().tolist()

  total_count = len(target_tickers)
  print(
      f'全銘柄スクリーニング開始（出来高フィルター適用）: 合計'
      f' {total_count} 銘柄'
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
      if avg_volume_20 < 10000:  # 20日平均出来高1万株未満は除外
        continue

      last_volume = df['Volume'].iloc[-1]
      last_close = df['Close'].iloc[-1]
      if (last_close * last_volume) < 5000000:  # 売買代金500万円未満は除外
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

  # ---------------------------------------------------------
  # 3. 🔥 既存の watchlist.json とのマージ（自動統合）処理
  # ---------------------------------------------------------
  output_json = 'watchlist.json'
  existing_watchlist = []

  # リポジトリ上に既存の watchlist.json があれば読み込む
  if os.path.exists(output_json):
    try:
      with open(output_json, 'r', encoding='utf-8') as f:
        existing_watchlist = json.load(f)
      print(
          f'\n既存の {output_json} から {len(existing_watchlist)} 銘柄を読み込みました。'
      )
    except Exception as e:
      print(f'既存ファイル読み込みエラー (新規作成します): {e}')

  # 既存リスト + 今回抽出した新規リスト を結合（順序を維持したまま重複を除去）
  merged_watchlist = list(
      dict.fromkeys(existing_watchlist + new_buy_candidates)
  )

  # マージ結果を保存
  with open(output_json, 'w', encoding='utf-8') as f:
    json.dump(merged_watchlist, f, ensure_ascii=False, indent=2)

  added_count = len(merged_watchlist) - len(existing_watchlist)
  print('\n=== スクリーニング & マージ完了 ===')
  print(f'・今回新規検出: {len(new_buy_candidates)} 銘柄')
  print(f'・新規追加分: {added_count} 銘柄（重複除外済み）')
  print(
      f'・最終監視対象: {len(merged_watchlist)} 銘柄 ➔ {output_json}'
      ' に保存しました。'
  )
  print(f'・最新リスト: {merged_watchlist}')


if __name__ == '__main__':
  run_manual_screener()
