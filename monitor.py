import logging
import os
import re
import threading
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)

CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
CHECK_INTERVAL_SECONDS = max(15, int(os.environ.get("CHECK_INTERVAL_SECONDS", "15")))
PRODUCT_SCAN_SECONDS = max(30, int(os.environ.get("PRODUCT_SCAN_SECONDS", "60")))
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("REQUEST_TIMEOUT_SECONDS", "12"))

SEARCH_TERMS = {
    "ポケカ": ("ポケモンカードゲーム", "ポケモンカード"),
    "ワンピースカード": ("ONE PIECEカードゲーム", "ワンピースカードゲーム"),
    "ドラゴンボールカード": (
        "ドラゴンボールカードゲーム",
        "ドラゴンボールスーパーカードゲーム",
        "フュージョンワールド",
        "スーパーダイバーズ",
    ),
}
SEARCH_URL = "https://aeonretail.com/Form/Product/ProductList.aspx"
AEON_HOME_URL = "https://aeonretail.com/"
MAX_SEARCH_PAGES = 10

CARD_PATTERNS = {
    "ポケカ": re.compile(r"ポケモンカード(?:ゲーム)?", re.IGNORECASE),
    "ワンピースカード": re.compile(
        r"(?:ONE\s*PIECE|ワンピース)\s*カード(?:ゲーム)?", re.IGNORECASE
    ),
    "ドラゴンボールカード": re.compile(
        r"(?:ドラゴンボール.*(?:カード|フュージョンワールド|スーパーダイバーズ)|"
        r"(?:フュージョンワールド|スーパーダイバーズ).*(?:ドラゴンボール|カード))",
        re.IGNORECASE,
    ),
}

WAIT_MARKERS = (
    "しばらくお待ちください",
    "サイトへ接続しています",
    "順番にサイトへご案内",
    "仮想待合室",
    "queue-it",
    "waiting room",
)
SOLD_OUT_MARKERS = (
    "選択した商品は在庫切れです",
    "ただいま在庫がございません",
    "現在在庫がありません",
    "販売を終了しました",
    "販売期間外です",
    "予約受付を終了",
)
BUY_MARKERS = (
    "カートに入れる",
    "カートへ入れる",
    "予約する",
    "予約購入する",
    "お申し込み",
)

http = requests.Session()
http.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
            "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
        ),
        "Accept-Language": "ja-JP,ja;q=0.9",
    }
)

state_lock = threading.Lock()
state = {
    "started_at": None,
    "last_check_at": None,
    "last_success_at": None,
    "last_product_scan_at": None,
    "waiting": False,
    "initialized": False,
    "known_products": {},
    "last_error": None,
}


def compact_text(html):
    return " ".join(BeautifulSoup(html, "html.parser").stripped_strings)


def is_waiting_page(response, text):
    final_url = response.url.lower()
    lowered = text.lower()
    return (
        any(marker.lower() in lowered for marker in WAIT_MARKERS)
        or "queue" in final_url
        or "waiting" in final_url
    )


def line_broadcast(message):
    response = requests.post(
        "https://api.line.me/v2/bot/message/broadcast",
        headers={
            "Authorization": f"Bearer {CHANNEL_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        json={"messages": [{"type": "text", "text": message[:5000]}]},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    logger.info("LINE notification sent")


def product_title(anchor):
    text = " ".join(anchor.stripped_strings)
    if text:
        return text
    image = anchor.find("img")
    return (image.get("alt") or "").strip() if image else ""


def extract_products(html, category):
    soup = BeautifulSoup(html, "html.parser")
    pattern = CARD_PATTERNS[category]
    products = []
    seen = set()
    for anchor in soup.select('a[href*="/product/"]'):
        href = anchor.get("href")
        title = product_title(anchor)
        if not href or not title or not pattern.search(title):
            continue
        url = urljoin(AEON_HOME_URL, href).split("?")[0]
        if url not in seen:
            seen.add(url)
            products.append((title, url))
    return products


def result_count(html):
    match = re.search(r"対象アイテム[：:]\s*([0-9,]+)件", compact_text(html))
    return int(match.group(1).replace(",", "")) if match else 0


def search_all_products(category, term):
    products = {}
    for page_number in range(1, MAX_SEARCH_PAGES + 1):
        params = {"gspsk": term, "gspss": "sell_from:desc", "psc": "0"}
        if page_number > 1:
            params["gspsp"] = str(page_number)
        response = http.get(
            SEARCH_URL,
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
        response.raise_for_status()
        text = compact_text(response.text)
        if is_waiting_page(response, text):
            return {}, True
        page_products = extract_products(response.text, category)
        before = len(products)
        for title, url in page_products:
            products[url] = title
        total = result_count(response.text)
        if total and page_number * 20 >= total:
            break
        if page_number > 1 and len(products) == before:
            break
        if not total and len(page_products) < 20:
            break
    return [(title, url) for url, title in products.items()], False


def fetch(url):
    response = http.get(url, timeout=REQUEST_TIMEOUT_SECONDS, allow_redirects=True)
    response.raise_for_status()
    return response, compact_text(response.text)


def check_product(url):
    response, text = fetch(url)
    if is_waiting_page(response, text):
        return None, True
    sold_out = any(marker in text for marker in SOLD_OUT_MARKERS)
    purchasable = any(marker in text for marker in BUY_MARKERS)
    return purchasable and not sold_out, False


def notify_waiting(url=AEON_HOME_URL):
    line_broadcast(
        "🚨 イオンスタイルオンラインで待機が発生しました\n"
        "販売開始の可能性があります。すぐに確認してください。\n"
        f"{url}"
    )
    with state_lock:
        state["waiting"] = True


def run_cycle():
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with state_lock:
        state["last_check_at"] = now

    try:
        response, text = fetch(AEON_HOME_URL)
        waiting_detected = is_waiting_page(response, text)
    except requests.RequestException as exc:
        logger.warning("Queue check failed: %s", exc)
        waiting_detected = False

    with state_lock:
        was_waiting = state["waiting"]
    if waiting_detected:
        if not was_waiting:
            notify_waiting()
        with state_lock:
            state["last_success_at"] = now
            state["last_error"] = None
        return
    with state_lock:
        state["waiting"] = False
        last_scan = state["last_product_scan_at"]
    if last_scan and time.time() - last_scan < PRODUCT_SCAN_SECONDS:
        with state_lock:
            state["last_success_at"] = now
        return

    found_products = {}
    for category, terms in SEARCH_TERMS.items():
        for term in terms:
            try:
                products, search_waiting = search_all_products(category, term)
                if search_waiting:
                    notify_waiting()
                    return
                for title, url in products:
                    found_products[(category, url)] = title
            except requests.RequestException as exc:
                logger.warning("Search failed for %s/%s: %s", category, term, exc)

    with state_lock:
        initialized = state["initialized"]
    for (category, url), title in found_products.items():
        try:
            available, product_waiting = check_product(url)
            if product_waiting:
                notify_waiting(url)
                return
            with state_lock:
                previous = state["known_products"].get(url)
                state["known_products"][url] = bool(available)
            if initialized and available and previous is not True:
                line_broadcast(f"🔥【販売開始】{category}\n{title[:300]}\n{url}")
        except requests.RequestException as exc:
            logger.warning("Product check failed for %s: %s", url, exc)

    with state_lock:
        state["initialized"] = True
        state["last_product_scan_at"] = time.time()
        state["last_success_at"] = now
        state["last_error"] = None


def loop():
    with state_lock:
        state["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    logger.info(
        "AEON monitor started; queue=%ss products=%ss",
        CHECK_INTERVAL_SECONDS,
        PRODUCT_SCAN_SECONDS,
    )
    while True:
        started = time.monotonic()
        try:
            run_cycle()
        except Exception as exc:
            logger.exception("Monitor cycle failed")
            with state_lock:
                state["last_error"] = str(exc)[:500]
        time.sleep(max(1, CHECK_INTERVAL_SECONDS - (time.monotonic() - started)))


if CHANNEL_ACCESS_TOKEN and os.environ.get("MONITOR_ENABLED", "true").lower() == "true":
    threading.Thread(target=loop, name="aeon-monitor", daemon=True).start()
