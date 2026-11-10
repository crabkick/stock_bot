import re
import bs4
import requests

# =========================================================
# 設定項目
# =========================================================
PRINCIPAL = 44444  # 投資元本（全体）
HOLDING_UNITS = 11671  # 保有口数（実際の保有口数）
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1569541009053065348/atvAS9slaGCq2yED1AUkpJ3lpFVK1Um1NW6CvrOkGCUQSyZif75cMOItpLchx2PoPsnT"


# =========================================================
# 基準価額取得関数（日本版Yahoo!ファイナンスより）
# =========================================================
def get_orukan_nav():
  """eMAXIS Slim 全世界株式（オール・カントリー）の最新基準価額を取得する"""
  # Yahoo!ファイナンス日本版の投信ページURL
  url = "https://finance.yahoo.co.jp/quote/0331418A"

  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
          " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
      )
  }

  try:
    res = requests.get(url, headers=headers, timeout=10)
    soup = bs4.BeautifulSoup(res.text, "html.parser")

    # 基準価額が表示されている要素を抽出
    # ※ YahooファイナンスのHTML構造から最新価格を抽出
    price_element = soup.find(
        "span", class_=re.compile(r"StyledNumber__value.*")
    )

    if not price_element:
      # 代替：メタタグや別クラスからの抽出を試行
      price_element = soup.select_one("span._1D6qf42_")

    if price_element:
      # カンマを除去して数値（float）に変換
      price_str = price_element.text.replace(",", "")
      return float(price_str)
    else:
      print("基準価額の要素が見つかりませんでした。")
      return None

  except Exception as e:
    print(f"データ取得エラー: {e}")
    return None


# =========================================================
# 通知ロジック
# =========================================================
def check_and_notify_discord():
  # 最新の1口あたり基準価額を取得（※日本の投信画面の値は1万口あたり表示のため10,000で割る）
  nav_10k = get_orukan_nav()

  if nav_10k is None:
    print("基準価額の取得に失敗したため、通知をキャンセルします。")
    return

  # 1口あたりの基準価額
  latest_nav = nav_10k / 10000.0

  # 1. 現在の評価額（全体）
  current_total_value = latest_nav * HOLDING_UNITS

  # 2. 元本との差額（全体の損益額）
  diff_amount = current_total_value - PRINCIPAL

  # 差額の表現を生成
  if diff_amount >= 0:
    diff_text = f"**+{diff_amount:,.0f} 円** (プラス)"
  else:
    diff_text = f"**{diff_amount:,.0f} 円** (マイナス)"

  # 送信メッセージの作成
  content_message = f"""
📈 **【オルカン 資産差額レポート】**

・投資元本: **{PRINCIPAL:,.0f} 円**
・現在評価額: **{current_total_value:,.0f} 円** (1万口あたり: {nav_10k:,.0f}円)
---------------------------------
👉 元本との差額: {diff_text}
"""

  # Discordへ送信
  payload = {"content": content_message}
  response = requests.post(DISCORD_WEBHOOK_URL, json=payload)

  if response.status_code in [200, 204]:
    print("Discordへ正常に送信しました。")
  else:
    print(f"送信失敗: {response.status_code}, {response.text}")


# 実行
check_and_notify_discord()
