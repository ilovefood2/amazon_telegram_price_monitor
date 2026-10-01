import hashlib
import json
import logging
import os
import re
import shutil
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "300"))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
DEFAULT_REPEAT_ALERT_HOURS = int(os.getenv("REPEAT_ALERT_HOURS", "24"))
STATE_FILE = os.getenv("STATE_FILE", "/data/state.json")
PRODUCTS_FILE = os.getenv("PRODUCTS_FILE", "/app/products.json")
CASHBACK_FILE = os.getenv("CASHBACK_FILE", "/app/cashback.json")
PAGE_LOAD_WAIT_SECONDS = int(os.getenv("PAGE_LOAD_WAIT_SECONDS", "4"))

CHROME_BINARY = (
    os.getenv("CHROME_BINARY")
    or shutil.which("chromium")
    or shutil.which("chromium-browser")
    or "/usr/bin/chromium"
)
CHROMEDRIVER_BINARY = (
    os.getenv("CHROMEDRIVER_BINARY")
    or shutil.which("chromedriver")
    or "/usr/bin/chromedriver"
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("price-monitor")


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
            if isinstance(state, dict):
                return state
    except FileNotFoundError:
        pass
    except Exception as exc:
        log.warning("Could not load state file %s: %s", STATE_FILE, exc)
    return {"products": {}, "cashback": {}}


def save_state(state):
    directory = os.path.dirname(STATE_FILE) or "."
    os.makedirs(directory, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp, STATE_FILE)


def product_key(url, explicit_id=None):
    if explicit_id:
        return str(explicit_id).strip()

    asin_match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?]|$)", url, re.I)
    if asin_match:
        return asin_match.group(1).upper()

    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def load_products():
    with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, dict):
        raw = raw.get("products")
    if not isinstance(raw, list):
        raise ValueError(
            "products.json must contain a JSON array "
            "(or an object with a 'products' array)."
        )

    products = []
    seen_keys = set()

    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Product #{index} must be a JSON object.")
        if item.get("enabled", True) is False:
            continue

        url = str(item.get("url", "")).strip()
        if not url:
            raise ValueError(f"Product #{index} is missing 'url'.")

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"Product #{index} has an invalid URL: {url}")

        try:
            target_price = float(item["target_price"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(
                f"Product #{index} has an invalid or missing 'target_price'."
            )

        if target_price <= 0:
            raise ValueError(f"Product #{index} target_price must be greater than 0.")

        try:
            repeat_alert_hours = int(
                item.get("repeat_alert_hours", DEFAULT_REPEAT_ALERT_HOURS)
            )
        except (TypeError, ValueError):
            raise ValueError(f"Product #{index} has an invalid 'repeat_alert_hours'.")

        if repeat_alert_hours < 0:
            raise ValueError(f"Product #{index} repeat_alert_hours cannot be negative.")

        key = product_key(url, item.get("id"))
        if not key:
            raise ValueError(f"Product #{index} has an empty id.")
        if key in seen_keys:
            raise ValueError(f"Duplicate product id/key '{key}' in products.json.")

        seen_keys.add(key)
        products.append(
            {
                "key": key,
                "name": str(item.get("name", "")).strip(),
                "url": url,
                "target_price": target_price,
                "repeat_alert_hours": repeat_alert_hours,
            }
        )

    return products


def cashback_key(url, explicit_id=None):
    if explicit_id:
        return str(explicit_id).strip()
    return "cashback-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def load_cashback_monitors():
    if not os.path.exists(CASHBACK_FILE):
        return []

    with open(CASHBACK_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, dict):
        raw = raw.get("cashback")
    if not isinstance(raw, list):
        raise ValueError(
            "cashback.json must contain a JSON array "
            "(or an object with a 'cashback' array)."
        )

    monitors = []
    seen_keys = set()

    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Cashback monitor #{index} must be a JSON object.")
        if item.get("enabled", True) is False:
            continue

        url = str(item.get("url", "")).strip()
        if not url:
            raise ValueError(f"Cashback monitor #{index} is missing 'url'.")

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"Cashback monitor #{index} has an invalid URL: {url}")

        host = parsed.netloc.lower().split(":")[0]
        if host != "rakuten.ca" and not host.endswith(".rakuten.ca"):
            raise ValueError(
                f"Cashback monitor #{index} must use a rakuten.ca URL."
            )

        try:
            threshold_percent = float(item["threshold_percent"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(
                f"Cashback monitor #{index} has an invalid or missing "
                "'threshold_percent'."
            )

        if threshold_percent < 0:
            raise ValueError(
                f"Cashback monitor #{index} threshold_percent cannot be negative."
            )

        comparison = str(item.get("comparison", "gt")).strip().lower()
        if comparison not in {"gt", "gte"}:
            raise ValueError(
                f"Cashback monitor #{index} comparison must be 'gt' or 'gte'."
            )

        try:
            repeat_alert_hours = int(
                item.get("repeat_alert_hours", DEFAULT_REPEAT_ALERT_HOURS)
            )
        except (TypeError, ValueError):
            raise ValueError(
                f"Cashback monitor #{index} has an invalid 'repeat_alert_hours'."
            )

        if repeat_alert_hours < 0:
            raise ValueError(
                f"Cashback monitor #{index} repeat_alert_hours cannot be negative."
            )

        key = cashback_key(url, item.get("id"))
        if not key:
            raise ValueError(f"Cashback monitor #{index} has an empty id.")
        if key in seen_keys:
            raise ValueError(f"Duplicate cashback monitor id/key '{key}'.")

        seen_keys.add(key)
        monitors.append(
            {
                "key": key,
                "name": str(item.get("name", "Rakuten Cash Back")).strip()
                or "Rakuten Cash Back",
                "url": url,
                "threshold_percent": threshold_percent,
                "comparison": comparison,
                "repeat_alert_hours": repeat_alert_hours,
            }
        )

    return monitors


def build_driver():
    if not os.path.exists(CHROME_BINARY):
        raise RuntimeError(f"Chromium binary not found: {CHROME_BINARY}")
    if not os.path.exists(CHROMEDRIVER_BINARY):
        raise RuntimeError(f"ChromeDriver binary not found: {CHROMEDRIVER_BINARY}")

    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1400,1800")
    options.add_argument("--lang=en-CA")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"
    )

    service = Service(executable_path=CHROMEDRIVER_BINARY)
    return webdriver.Chrome(service=service, options=options)


def parse_money(text):
    if not text:
        return None

    text = text.replace(",", "").replace("\xa0", " ")
    match = re.search(r"(?:C\$|\$)\s*([0-9]+(?:\.[0-9]{1,2})?)", text)
    if match:
        return float(match.group(1))

    match = re.search(r"\b([0-9]+(?:\.[0-9]{1,2})?)\b", text)
    if match:
        return float(match.group(1))

    return None


def get_product_price(driver, product):
    driver.get(product["url"])
    time.sleep(PAGE_LOAD_WAIT_SECONDS)

    title = product["name"] or "Amazon product"
    try:
        title_text = driver.find_element(By.ID, "productTitle").text.strip()
        if title_text:
            title = title_text
    except Exception:
        pass

    selectors = [
        "#corePrice_feature_div .a-price .a-offscreen",
        "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
        "#price_inside_buybox",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        ".apexPriceToPay .a-offscreen",
        "span.a-price span.a-offscreen",
    ]

    for selector in selectors:
        try:
            for element in driver.find_elements(By.CSS_SELECTOR, selector):
                raw = (
                    element.get_attribute("textContent")
                    or element.text
                    or ""
                ).strip()
                price = parse_money(raw)
                if price is not None and 0.01 <= price <= 100000:
                    log.info(
                        "[%s] Price candidate %.2f from %s (%s)",
                        product["key"],
                        price,
                        selector,
                        raw,
                    )
                    return title, price
        except Exception:
            continue

    body = driver.find_element(By.TAG_NAME, "body").text
    for raw in re.findall(
        r"(?:C\$|\$)\s*[0-9]{1,6}(?:\.[0-9]{2})?",
        body,
    ):
        price = parse_money(raw)
        if price is not None and 0.01 <= price <= 100000:
            log.info(
                "[%s] Fallback price candidate %.2f (%s)",
                product["key"],
                price,
                raw,
            )
            return title, price

    source = driver.page_source.lower()
    if (
        "enter the characters you see below" in source
        or "sorry, we just need to make sure" in source
    ):
        raise RuntimeError("Amazon returned a bot/challenge page.")

    raise RuntimeError("Could not find a product price on the page.")


def parse_cashback_percent(text):
    if not text:
        return None

    match = re.search(
        r"(?i)(?:up to\s*)?([0-9]+(?:\.[0-9]+)?)\s*%\s*Cash Back\b",
        text,
    )
    if match:
        return float(match.group(1))

    return None


def get_rakuten_cashback_rate(driver, monitor):
    driver.get(monitor["url"])
    time.sleep(PAGE_LOAD_WAIT_SECONDS)

    candidates = [("page title", driver.title or "")]

    for selector in [
        "meta[property='og:title']",
        "meta[name='twitter:title']",
    ]:
        try:
            for element in driver.find_elements(By.CSS_SELECTOR, selector):
                content = (element.get_attribute("content") or "").strip()
                if content:
                    candidates.append((selector, content))
        except Exception:
            pass

    for source_name, text in candidates:
        rate = parse_cashback_percent(text)
        if rate is not None:
            log.info(
                "[%s] Rakuten cashback candidate %.2f%% from %s (%s)",
                monitor["key"],
                rate,
                source_name,
                text,
            )
            return rate

    try:
        body = driver.find_element(By.TAG_NAME, "body").text
        merchant = monitor["name"].strip()
        if merchant:
            lower_body = body.lower()
            pos = lower_body.find(merchant.lower())
            if pos >= 0:
                snippet = body[max(0, pos - 250): pos + 800]
                rate = parse_cashback_percent(snippet)
                if rate is not None:
                    log.info(
                        "[%s] Rakuten cashback candidate %.2f%% "
                        "from merchant snippet",
                        monitor["key"],
                        rate,
                    )
                    return rate
    except Exception:
        pass

    raise RuntimeError(
        "Could not find the Rakuten Cash Back percentage on the page."
    )


def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing.")

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    response = requests.post(
        url,
        timeout=20,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "disable_web_page_preview": False,
        },
    )
    response.raise_for_status()
    data = response.json()

    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")


def should_alert(item_state, price, target_price, repeat_alert_hours):
    if price > target_price:
        return False

    if not item_state.get("below_target", False):
        return True

    last_price = item_state.get("last_alert_price")
    if last_price is None or price < float(last_price):
        return True

    if repeat_alert_hours == 0:
        return False

    last_alert_at = item_state.get("last_alert_at")
    if last_alert_at:
        try:
            last_dt = datetime.fromisoformat(last_alert_at)
            return (
                datetime.now(timezone.utc) - last_dt
                >= timedelta(hours=repeat_alert_hours)
            )
        except Exception:
            return True

    return True


def cashback_triggered(rate, threshold_percent, comparison):
    if comparison == "gte":
        return rate >= threshold_percent
    return rate > threshold_percent


def should_alert_cashback(
    item_state,
    rate,
    threshold_percent,
    comparison,
    repeat_alert_hours,
):
    if not cashback_triggered(rate, threshold_percent, comparison):
        return False

    if not item_state.get("above_threshold", False):
        return True

    last_rate = item_state.get("last_alert_rate")
    if last_rate is None or rate > float(last_rate):
        return True

    if repeat_alert_hours == 0:
        return False

    last_alert_at = item_state.get("last_alert_at")
    if last_alert_at:
        try:
            last_dt = datetime.fromisoformat(last_alert_at)
            return (
                datetime.now(timezone.utc) - last_dt
                >= timedelta(hours=repeat_alert_hours)
            )
        except Exception:
            return True

    return True


def run():
    log.info(
        "Shopping deal monitor started; interval=%ss; products=%s; cashback=%s",
        CHECK_INTERVAL_SECONDS,
        PRODUCTS_FILE,
        CASHBACK_FILE,
    )

    state = load_state()
    if not isinstance(state.get("products"), dict):
        state["products"] = {}
    if not isinstance(state.get("cashback"), dict):
        state["cashback"] = {}

    last_config_signature = None

    while True:
        driver = None

        try:
            products = load_products()
            cashback_monitors = load_cashback_monitors()

            signature = json.dumps(
                {
                    "products": products,
                    "cashback": cashback_monitors,
                },
                sort_keys=True,
                ensure_ascii=False,
            )

            if signature != last_config_signature:
                log.info(
                    "Loaded %d Amazon product(s) and %d cashback monitor(s)",
                    len(products),
                    len(cashback_monitors),
                )

                for product in products:
                    log.info(
                        "Watching Amazon [%s] %s | target C$%.2f | %s",
                        product["key"],
                        product["name"] or "(title from page)",
                        product["target_price"],
                        product["url"],
                    )

                for cashback in cashback_monitors:
                    operator = (
                        ">=" if cashback["comparison"] == "gte" else ">"
                    )
                    log.info(
                        "Watching Rakuten [%s] %s | alert %s %.2f%% | %s",
                        cashback["key"],
                        cashback["name"],
                        operator,
                        cashback["threshold_percent"],
                        cashback["url"],
                    )

                last_config_signature = signature

            if not products and not cashback_monitors:
                log.warning("No enabled monitors are configured.")
            else:
                driver = build_driver()

            for product in products:
                item_state = state["products"].setdefault(
                    product["key"],
                    {},
                )

                try:
                    title, price = get_product_price(driver, product)
                    now = datetime.now(timezone.utc).isoformat()

                    log.info(
                        "[%s] Current price: C$%.2f (target C$%.2f)",
                        product["key"],
                        price,
                        product["target_price"],
                    )

                    alert = should_alert(
                        item_state,
                        price,
                        product["target_price"],
                        product["repeat_alert_hours"],
                    )

                    item_state.update(
                        {
                            "last_check_at": now,
                            "last_seen_price": price,
                            "last_title": title,
                            "url": product["url"],
                            "target_price": product["target_price"],
                            "below_target": (
                                price <= product["target_price"]
                            ),
                        }
                    )

                    if alert:
                        message = (
                            "🔥 Amazon Price Alert\n\n"
                            f"{title}\n"
                            f"Price: C${price:.2f}\n"
                            f"Target: C${product['target_price']:.2f} "
                            "or less\n\n"
                            f"{product['url']}"
                        )
                        send_telegram(message)
                        item_state["last_alert_at"] = now
                        item_state["last_alert_price"] = price
                        log.info(
                            "[%s] Telegram alert sent.",
                            product["key"],
                        )

                    save_state(state)

                except Exception as exc:
                    item_state["last_error_at"] = (
                        datetime.now(timezone.utc).isoformat()
                    )
                    item_state["last_error"] = str(exc)
                    save_state(state)
                    log.exception(
                        "[%s] Amazon check failed: %s",
                        product["key"],
                        exc,
                    )

            for cashback in cashback_monitors:
                item_state = state["cashback"].setdefault(
                    cashback["key"],
                    {},
                )

                try:
                    rate = get_rakuten_cashback_rate(driver, cashback)
                    now = datetime.now(timezone.utc).isoformat()

                    triggered = cashback_triggered(
                        rate,
                        cashback["threshold_percent"],
                        cashback["comparison"],
                    )
                    operator = (
                        ">=" if cashback["comparison"] == "gte" else ">"
                    )

                    log.info(
                        "[%s] Current Cash Back: %.2f%% "
                        "(alert %s %.2f%%)",
                        cashback["key"],
                        rate,
                        operator,
                        cashback["threshold_percent"],
                    )

                    alert = should_alert_cashback(
                        item_state,
                        rate,
                        cashback["threshold_percent"],
                        cashback["comparison"],
                        cashback["repeat_alert_hours"],
                    )

                    item_state.update(
                        {
                            "last_check_at": now,
                            "last_seen_rate": rate,
                            "name": cashback["name"],
                            "url": cashback["url"],
                            "threshold_percent": (
                                cashback["threshold_percent"]
                            ),
                            "comparison": cashback["comparison"],
                            "above_threshold": triggered,
                        }
                    )

                    if alert:
                        message = (
                            "💰 Rakuten Cash Back Alert\n\n"
                            f"{cashback['name']}\n"
                            f"Cash Back: {rate:g}%\n"
                            f"Threshold: {operator} "
                            f"{cashback['threshold_percent']:g}%\n\n"
                            f"{cashback['url']}"
                        )
                        send_telegram(message)
                        item_state["last_alert_at"] = now
                        item_state["last_alert_rate"] = rate
                        log.info(
                            "[%s] Telegram alert sent.",
                            cashback["key"],
                        )

                    save_state(state)

                except Exception as exc:
                    item_state["last_error_at"] = (
                        datetime.now(timezone.utc).isoformat()
                    )
                    item_state["last_error"] = str(exc)
                    save_state(state)
                    log.exception(
                        "[%s] Rakuten check failed: %s",
                        cashback["key"],
                        exc,
                    )

        except Exception as exc:
            log.exception("Monitor cycle failed: %s", exc)

        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    run()
