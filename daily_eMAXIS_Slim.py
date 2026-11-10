import os
import re
import bs4
import requests

# =========================================================
# 設定項目
# =========================================================
PRINCIPAL = 44444  # 投資元本（全体）
HOLDING_UNITS = 11671  # 保有口数
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")


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
    print("DISCORD_WEBHOOK_URL が設定されていません。")


def get_orukan_nav():
  """eMAXIS Slim 全世界株式（オール・カントリー）の最新基準価額を取得する"""
  url = "https://finance.yahoo.co.jp/quote/0331418A"

  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
          " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
      )
  }

  try:
    res = requests.get(url, headers=headers, timeout=10)
    res.raise_for_status()
    soup = bs4.BeautifulSoup(res.text, "html.parser")

    # 抽出パターン1: 数字表記クラス（柔軟な正規表現パターン）
    price_element = soup.find(
        "span", class_=re.compile(r".*StyledNumber__value.*|.*value.*")
    )

    # 抽出パターン2: metaタグ（og:price や canonical 関連データ）
    if not price_element:
      meta_tag = soup.find("meta", property="text:price") or soup.find(
          "meta", attrs={"name": "price"}
      )
      if meta_tag and meta_tag.get("content"):
        return float(meta_tag["content"].replace(",", ""))

    # 抽出パターン3: ページ内の全テキストから「基準価額」近辺の数値を検索
    if not price_element:
      # 「基準価額」を含む要素を探す
      nav_label = soup.find(text=re.compile(r"基準価額"))
      if nav_label:
        parent = nav_label.find_parent()
        if parent:
          numbers = re.findall(r"[\d,]+", parent.text)
          for num in numbers:
            clean_num = num.replace(",", "")
            if clean_num.isdigit() and len(clean_num) >= 4:
              return float(clean_num)

    if price_element:
      price_str = price_element.text.replace(",", "")
      # 数字以外の文字が含まれる場合を取り除く処理
      match = re.search(r"[\d\.]+", price_str)
      if match:
        return float(match.group())

    print("エラー: 基準価額を表示するHTML要素が見つかりませんでした。")
    return None

  except Exception as e:
    print(f"データ取得エラー: {e}")
    return None


def check_and_notify_discord():
  # 1. Secret設定の存在チェック
  if not DISCORD_WEBHOOK_URL:
    print("エラー: DISCORD_WEBHOOK_URL が設定されていません。")
    return

  # 2. 最新の基準価額を取得
  nav_10k = get_orukan_nav()

  # 失敗した場合はエラーメッセージをDiscordに送って知らせる
  if nav_10k is None:
    error_msg = "⚠️ **【オルカンレポート エラー】**\nYahoo!ファイナンスからの基準価額取得に失敗しました。"
    print(error_msg)
    send_discord(error_msg)
    return

  # 1口あたりの基準価額
  latest_nav = nav_10k / 10000.0

  # 現在の評価額 & 損益計算
  current_total_value = latest_nav * HOLDING_UNITS
  diff_amount = current_total_value - PRINCIPAL

  if diff_amount >= 0:
    diff_text = f"**+{diff_amount:,.0f} 円** (プラス 🟢)"
  else:
    diff_text = f"**{diff_amount:,.0f} 円** (マイナス 🔴)"

  content_message = f"""
📈 **【オルカン 資産差額レポート】**

・投資元本: **{PRINCIPAL:,.0f} 円**
・現在評価額: **{current_total_value:,.0f} 円** (1万口あたり: {nav_10k:,.0f}円)
---------------------------------
👉 元本との差額: {diff_text}
"""

  send_discord(content_message)


if __name__ == "__main__":
  check_and_notify_discord()
