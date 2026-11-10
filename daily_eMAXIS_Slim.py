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

# =========================================================
# 基準価額取得関数（日本版Yahoo!ファイナンスより）
# =========================================================
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

        # パターン1: StyledNumber__value クラスからの抽出
        price_element = soup.find(
            "span", class_=re.compile(r"StyledNumber__value.*")
        )

        # パターン2: 予備セレクター（クラス名変更対策）
        if not price_element:
            price_element = soup.select_one("span._1D6qf42_")

        # パターン3: メタタグからの抽出（さらにフォールバック）
        if not price_element:
            meta_price = soup.find("meta", property="text:price")
            if meta_price and meta_price.get("content"):
                return float(meta_price["content"].replace(",", ""))

        if price_element:
            price_str = price_element.text.replace(",", "")
            return float(price_str)
        else:
            print("エラー: 基準価額を表示するHTML要素が見つかりませんでした。")
            return None

    except Exception as e:
        print(f"データ取得エラー: {e}")
        return None


# =========================================================
# 通知ロジック
# =========================================================
def check_and_notify_discord():
    # Webhook URLの存在チェック（設定漏れ防止）
    if not DISCORD_WEBHOOK_URL:
        print("エラー: DISCORD_WEBHOOK_URL が環境変数に設定されていません。")
        return

    # 最新の基準価額を取得（1万口あたり）
    nav_10k = get_orukan_nav()

    if nav_10k is None:
        print("基準価額の取得に失敗したため、通知をキャンセルします。")
        return

    # 1口あたりの基準価額
    latest_nav = nav_10k / 10000.0

    # 1. 現在の評価額
    current_total_value = latest_nav * HOLDING_UNITS

    # 2. 損益額
    diff_amount = current_total_value - PRINCIPAL

    # 差額の表現を生成
    if diff_amount >= 0:
        diff_text = f"**+{diff_amount:,.0f} 円** (プラス 🟢)"
    else:
        diff_text = f"**{diff_amount:,.0f} 円** (マイナス 🔴)"

    # 送信メッセージの作成
    content_message = f"""
📈 **【オルカン 資産差額レポート】**

・投資元本: **{PRINCIPAL:,.0f} 円**
・現在評価額: **{current_total_value:,.0f} 円** (1万口あたり: {nav_10k:,.0f}円)
---------------------------------
👉 元本との差額: {diff_text}
"""

    # Discordへ送信
    try:
        payload = {"content": content_message}
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)

        if response.status_code in [200, 204]:
            print("Discordへ正常に送信しました。")
        else:
            print(f"送信失敗: HTTP {response.status_code}, {response.text}")
    except Exception as e:
        print(f"Discord送信エラー: {e}")


if __name__ == "__main__":
    check_and_notify_discord()
