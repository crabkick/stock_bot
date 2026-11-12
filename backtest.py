import glob
import pandas as pd
import yfinance as yf


def get_target_tickers(limit=50):
  """最新のCSVから出来高のありそうな銘柄を抽出（テスト時間短縮のため上限設定）"""
  files = glob.glob('japan_stocks_list_*.csv')
  if files:
    df = pd.read_csv(sorted(files)[-1])
    # プライム市場に絞って先頭から指定件数を取得（全件やる場合は limit=None にする）
    prime_df = df[df['市場・商品区分'].str.contains('プライム', na=False)]
    tickers = prime_df['Ticker'].dropna().tolist()
    return tickers[:limit] if limit else tickers
  else:
    # CSVがない場合のサンプル銘柄リスト（トヨタ、ソニー、三菱UFJ、ソフトバンクG、任天堂など）
    return [
        '7203.T',
        '6758.T',
        '8306.T',
        '9984.T',
        '7974.T',
        '8035.T',
        '6861.T',
        '6098.T',
        '9432.T',
        '4063.T',
    ]


def run_backtest(
    tickers,
    period='2y',
    take_profit_mode='SMA20',  # 'SMA20' (中央線利確) または 'Upper' (+2σ利確)
    stop_loss_pct=-0.05,  # 損切りライン (-5%)
    trade_amount=1000000,  # 1トレードあたりの投資資金 (100万円)
):
  print(f'=== バックテスト開始 (対象: {len(tickers)} 銘柄 / 期間: {period}) ===')
  print(
      f'ルール: 買い(週1・金曜判定→月曜始値) / 売り(毎日判定→翌始値) /'
      f' 利確={take_profit_mode} / 損切り={stop_loss_pct*100:.1f}%\n'
  )

  all_trades = []

  for idx, ticker in enumerate(tickers, 1):
    try:
      df = yf.download(ticker, period=period, progress=False)
      if df.empty or len(df) < 60:
        continue

      if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

      # 指標計算
      df['SMA20'] = df['Close'].rolling(20).mean()
      df['STD20'] = df['Close'].rolling(20).std()
      df['Upper_Band'] = df['SMA20'] + (df['STD20'] * 2)
      df['Lower_Band'] = df['SMA20'] - (df['STD20'] * 2)
      df['Avg_Vol20'] = df['Volume'].rolling(20).mean()

      exp1 = df['Close'].ewm(span=12, adjust=False).mean()
      exp2 = df['Close'].ewm(span=26, adjust=False).mean()
      df['MACD'] = exp1 - exp2
      df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
      df['Hist'] = df['MACD'] - df['Signal']

      # 曜日番号 (0=月, 4=金)
      df['Weekday'] = df.index.weekday

      in_position = False
      buy_price = 0.0
      buy_date = None
      pending_buy = False
      pending_sell = False
      sell_reason = ''

      for i in range(30, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i - 1]
        current_date = df.index[i].strftime('%Y-%m-%d')

        # 1. 前営業日にシグナルが出ていた場合の「本日の始値」での約定処理
        if pending_buy and not in_position:
          buy_price = row['Open']
          buy_date = current_date
          in_position = True
          pending_buy = False

        elif pending_sell and in_position:
          sell_price = row['Open']
          return_pct = (sell_price - buy_price) / buy_price
          profit_yen = trade_amount * return_pct

          all_trades.append({
              'Ticker': ticker,
              'Buy_Date': buy_date,
              'Sell_Date': current_date,
              'Buy_Price': round(buy_price, 1),
              'Sell_Price': round(sell_price, 1),
              'Return_Pct': return_pct * 100,
              'Profit_Yen': round(profit_yen),
              'Reason': sell_reason,
          })

          in_position = False
          pending_sell = False
          buy_price = 0.0

        # 2. 大引け後の判定処理
        if not in_position and not pending_buy:
          # 【買い判定】毎週金曜日 (Weekday == 4) のみチェック
          if row['Weekday'] == 4:
            # 流動性フィルター
            if (
                row['Avg_Vol20'] >= 10000
                and (row['Close'] * row['Volume']) >= 5000000
            ):
              # ボリバン-2σ以下 ＆ MACDヒストグラム反転
              if (row['Close'] <= row['Lower_Band']) and (
                  row['Hist'] > prev_row['Hist']
              ):
                pending_buy = True

        elif in_position and not pending_sell:
          # 【売り判定】毎日チェック
          current_return = (row['Close'] - buy_price) / buy_price
          target_line = (
              row['SMA20'] if take_profit_mode == 'SMA20' else row['Upper_Band']
          )

          # 損切り判定
          if current_return <= stop_loss_pct:
            pending_sell = True
            sell_reason = '損切り'
          # 利確判定
          elif row['Close'] >= target_line:
            pending_sell = True
            sell_reason = f'利確({take_profit_mode})'

    except Exception:
      continue

  # ---------------------------------------------------------
  # 3. 集計レポートの出力
  # ---------------------------------------------------------
  if not all_trades:
    print('⚠️ 期間中に条件に合致するトレードが発生しませんでした。')
    return

  res_df = pd.DataFrame(all_trades)
  total_trades = len(res_df)
  win_trades = len(res_df[res_df['Profit_Yen'] > 0])
  lose_trades = len(res_df[res_df['Profit_Yen'] <= 0])
  win_rate = (win_trades / total_trades) * 100

  total_profit = res_df['Profit_Yen'].sum()
  avg_return = res_df['Return_Pct'].mean()
  max_win = res_df['Return_Pct'].max()
  max_loss = res_df['Return_Pct'].min()

  print('==================================================')
  print('📊 バックテスト結果サマリー')
  print('==================================================')
  print(f'・総トレード回数 : {total_trades} 回 (勝ち: {win_trades} / 負け: {lose_trades})')
  print(f'・勝率           : {win_rate:.1f} %')
  print(f'・平均損益率     : {avg_return:+.2f} % / 1トレード')
  print(f'・最大利益率     : {max_win:+.2f} %')
  print(f'・最大損失率     : {max_loss:+.2f} %')
  print(
      f'・累計損益額     : {total_profit:+,} 円 (1回 {trade_amount:,}円 投資換算)'
  )
  print('==================================================\n')

  print('--- 直近のトレード履歴（最大15件） ---')
  print(res_df.tail(15).to_string(index=False))


if __name__ == '__main__':
  # まず50銘柄で高速テスト（全銘柄やる場合は limit=None に変更）
  targets = get_target_tickers(limit=50)
  run_backtest(
      targets,
      period='2y',
      take_profit_mode='SMA20',  # 'SMA20' か 'Upper' を切り替えて比較可能
      stop_loss_pct=-0.05,
  )
