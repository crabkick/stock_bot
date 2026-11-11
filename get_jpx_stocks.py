from datetime import datetime
import glob
import io
import os
import urllib.parse
from bs4 import BeautifulSoup
import pandas as pd
import requests

PAGE_URL = 'https://www.jpx.co.jp/markets/statistics-equities/misc/01.html'
BASE_URL = 'https://www.jpx.co.jp'


def remove_old_csv_files():
  """フォルダー内にある既存の japan_stocks_list_*.csv を削除する"""
  old_files = glob.glob('japan_stocks_list_*.csv')
  for f in old_files:
    try:
      os.remove(f)
      print(f'🗑️ 古いリストファイルを削除しました: {f}')
    except Exception as e:
      print(f'⚠️ ファイル削除エラー ({f}): {e}')


def get_japan_all_stocks():
  print('JPXから最新の銘柄一覧ファイルを検索中...')

  # 🔥 新しいファイルを作る前に古いCSVを削除
  remove_old_csv_files()

  headers = {
      'User-Agent': (
          'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
          ' (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
      )
  }

  res = requests.get(PAGE_URL, headers=headers)
  res.raise_for_status()
  soup = BeautifulSoup(res.text, 'html.parser')

  file_url = None
  for a in soup.find_all('a', href=True):
    href = a['href']
    if ('data_j' in href or 'data' in href) and (
        href.endswith('.xls') or href.endswith('.xlsx')
    ):
      file_url = urllib.parse.urljoin(BASE_URL, href)
      break

  if not file_url:
    for a in soup.find_all('a', href=True):
      if a['href'].endswith('.xls') or a['href'].endswith('.xlsx'):
        file_url = urllib.parse.urljoin(BASE_URL, a['href'])
        break

  if not file_url:
    raise Exception('銘柄一覧ファイルのダウンロードリンクが見つかりませんでした。')

  print(f'最新ファイルをダウンロード中: {file_url}')

  excel_res = requests.get(file_url, headers=headers)
  excel_res.raise_for_status()

  try:
    df = pd.read_excel(io.BytesIO(excel_res.content))
  except Exception:
    dfs = pd.read_html(io.BytesIO(excel_res.content))
    df = dfs[0]

  df.columns = [str(c) for c in df.columns]
  df_stocks = df[['コード', '銘柄名', '市場・商品区分', '33業種区分']].copy()

  df_stocks['コード'] = (
      df_stocks['コード'].astype(str).str.replace(r'\.0$', '', regex=True)
  )
  df_stocks = df_stocks[df_stocks['コード'].str.len() == 4].copy()

  df_stocks['Ticker'] = df_stocks['コード'] + '.T'

  today_str = datetime.now().strftime('%Y%m%d')
  output_filename = f'japan_stocks_list_{today_str}.csv'

  df_stocks.to_csv(output_filename, index=False, encoding='utf-8-sig')

  print(
      f'✨ 完了！全 {len(df_stocks)} 銘柄の最新リストを "{output_filename}" に保存しました。'
  )
  return output_filename


if __name__ == '__main__':
  get_japan_all_stocks()
