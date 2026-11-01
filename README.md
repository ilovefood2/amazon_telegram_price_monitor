# Shopping Deal Monitor → Telegram

A lightweight, Dockerized shopping monitor designed to run continuously on a Raspberry Pi or any Linux host with Docker.

It currently supports two kinds of monitoring:

1. **Product price monitoring** on Amazon.ca and other shopping websites.
2. **Rakuten Canada Cash Back monitoring** for merchant pages such as Sporting Life.

When a configured threshold is reached, the monitor sends a Telegram message through your bot.

The project started as an Amazon price watcher, so the repository/container name still contains `amazon` for backward compatibility, but `products.json` is now generic and can monitor many non-Amazon sites as well.

---

## Table of contents

- [What it does](#what-it-does)
- [Configuration examples](#configuration-examples)
- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Telegram bot setup](#telegram-bot-setup)
- [Environment configuration](#environment-configuration)
- [Product monitoring](#product-monitoring)
  - [How price detection works](#how-price-detection-works)
  - [products.json schema](#productsjson-schema)
  - [Amazon example](#amazon-example)
  - [Generic automatic example](#generic-automatic-example)
  - [Generic CSS selector example](#generic-css-selector-example)
  - [Meta-tag price example](#meta-tag-price-example)
  - [Multiple price selectors](#multiple-price-selectors)
  - [JavaScript-heavy pages](#javascript-heavy-pages)
  - [Using price_regex](#using-price_regex)
  - [Custom product title selectors](#custom-product-title-selectors)
  - [Multiple currencies](#multiple-currencies)
- [Rakuten Cash Back monitoring](#rakuten-cash-back-monitoring)
  - [cashback.json schema](#cashbackjson-schema)
  - [Sporting Life example](#sporting-life-example)
  - [Cash Back alert behavior](#cash-back-alert-behavior)
- [Live configuration reload](#live-configuration-reload)
- [Alert behavior and state](#alert-behavior-and-state)
- [State file](#state-file)
- [Logs](#logs)
- [Updating the Raspberry Pi](#updating-the-raspberry-pi)
- [Adding another product](#adding-another-product)
- [Adding another Rakuten merchant](#adding-another-rakuten-merchant)
- [Finding a CSS price selector](#finding-a-css-price-selector)
- [Validation commands](#validation-commands)
- [Troubleshooting](#troubleshooting)
- [Security notes](#security-notes)
- [Known limitations](#known-limitations)
- [Useful Docker commands](#useful-docker-commands)

---

# What it does

The monitor runs continuously inside Docker and repeats the following process:

```text
Load products.json
        ↓
Load cashback.json
        ↓
Start headless Chromium
        ↓
Visit each configured product page
        ↓
Extract the product price safely
        ↓
Compare price with target_price
        ↓
Visit each configured Rakuten merchant page
        ↓
Extract current Cash Back percentage
        ↓
Compare percentage with threshold
        ↓
Send Telegram only when an alert condition is met
        ↓
Save state in data/state.json
        ↓
Sleep CHECK_INTERVAL_SECONDS
        ↓
Repeat
```

The default interval is **300 seconds / 5 minutes**.

The monitor deliberately avoids blindly scanning a page for the first dollar amount it can find. That behavior can produce false alerts because shopping pages may contain shipping prices, list prices, accessory prices, financing amounts, recommendation prices, or unrelated products.

Instead, it uses structured product data, known site-specific selectors, or an explicit selector you configure.

---

# Configuration examples

The examples below illustrate the configuration format. Check your actual
`products.json` and `cashback.json` for the active products and thresholds.

## Product price

For example, a Finer Form bench entry in `products.json`:

```json
[
  {
    "id": "finer-form-bench",
    "name": "Finer Form Multi-Functional Weight Bench",
    "parser": "amazon",
    "url": "https://www.amazon.ca/Finer-Form-Multi-Functional-Weight-Workout-dp-B08YWHN79N/dp/B08YWHN79N/ref=dp_ob_title_sports",
    "target_price": 229,
    "currency": "CAD",
    "repeat_alert_hours": 24
  }
]
```

Alert condition:

```text
current price <= C$229
```

## Rakuten Cash Back

For example, a Sporting Life entry in `cashback.json`:

```json
[
  {
    "id": "sportinglife-rakuten",
    "name": "Sporting Life",
    "url": "https://www.rakuten.ca/sportinglife",
    "threshold_percent": 10,
    "comparison": "gt",
    "repeat_alert_hours": 24
  }
]
```

Alert condition:

```text
Sporting Life Cash Back > 10%
```

A rate of exactly **10% does not trigger** because `comparison` is `gt`.

---

# How it works

The monitor uses:

- Python 3.12
- Selenium
- Chromium
- Chromium Driver
- Docker Compose
- Telegram Bot API
- JSON configuration files
- a persistent JSON state file

The Docker image installs Chromium and Chromium Driver from Debian packages. This is important on Raspberry Pi ARM64 because Selenium Manager may not support every ARM architecture combination. The code therefore explicitly uses:

```text
/usr/bin/chromium
/usr/bin/chromedriver
```

by default.

The monitor uses one Chromium session per monitoring cycle and visits all configured pages within that cycle.

---

# Requirements

Recommended host:

- Raspberry Pi 4 or newer, 64-bit OS
- Raspberry Pi OS / Debian / Ubuntu
- Docker
- Docker Compose plugin
- Internet connection
- Telegram account

Check architecture:

```bash
uname -m
```

Typical Raspberry Pi 64-bit output:

```text
aarch64
```

Check Docker:

```bash
docker --version
docker compose version
```

If your account does not have permission to use Docker directly, use `sudo` as shown throughout this README.

---

# Quick start

Clone the repository:

```bash
git clone https://github.com/ilovefood2/amazon_telegram_price_monitor.git
cd amazon_telegram_price_monitor
```

Create your private runtime environment file:

```bash
cp .env.example .env
nano .env
```

Configure Telegram:

```env
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
TELEGRAM_CHAT_ID=YOUR_CHAT_ID
```

Build:

```bash
sudo docker compose build
```

Start:

```bash
sudo docker compose up -d
```

Follow logs:

```bash
sudo docker compose logs -f
```

---

# Telegram bot setup

## 1. Create the bot

Open Telegram and search for:

```text
@BotFather
```

Send:

```text
/newbot
```

Follow BotFather's prompts.

You will receive a token that looks conceptually like:

```text
1234567890:ABCDEF...
```

Do **not** commit this token to GitHub.

Put it in your local `.env`:

```env
TELEGRAM_BOT_TOKEN=YOUR_REAL_TOKEN
```

## 2. Send your bot a message

Open the bot you just created and send something simple:

```text
hi
```

Telegram will not normally expose your chat to the bot until you interact with it.

## 3. Retrieve your chat ID

Build first if necessary:

```bash
sudo docker compose build
```

Then run:

```bash
sudo docker compose run --rm amazon-price-monitor python get_chat_id.py
```

Example output:

```json
{"chat_id": 123456789, "type": "private", "username": "example"}
```

Copy the numeric ID into `.env`:

```env
TELEGRAM_CHAT_ID=123456789
```

Then start/recreate the container:

```bash
sudo docker compose up -d --force-recreate
```

---

# Environment configuration

The supplied `.env.example` contains:

```env
CHECK_INTERVAL_SECONDS=300
PRODUCTS_FILE=/app/products.json
CASHBACK_FILE=/app/cashback.json

PAGE_LOAD_WAIT_SECONDS=4
ELEMENT_WAIT_SECONDS=12

TELEGRAM_BOT_TOKEN=PASTE_BOT_TOKEN_HERE
TELEGRAM_CHAT_ID=PASTE_CHAT_ID_HERE

REPEAT_ALERT_HOURS=24

STATE_FILE=/data/state.json
LOG_LEVEL=INFO

TZ=America/Toronto

CHROME_BINARY=/usr/bin/chromium
CHROMEDRIVER_BINARY=/usr/bin/chromedriver
```

## Variable reference

| Variable | Default | Meaning |
|---|---:|---|
| `CHECK_INTERVAL_SECONDS` | `300` | Delay between complete monitoring cycles |
| `PRODUCTS_FILE` | `/app/products.json` | Product configuration inside container |
| `CASHBACK_FILE` | `/app/cashback.json` | Rakuten configuration inside container |
| `PAGE_LOAD_WAIT_SECONDS` | `4` | Extra delay after loading a page |
| `ELEMENT_WAIT_SECONDS` | `12` | Maximum Selenium wait when `wait_selector` is configured |
| `TELEGRAM_BOT_TOKEN` | none | Telegram Bot API token |
| `TELEGRAM_CHAT_ID` | none | Destination Telegram chat |
| `REPEAT_ALERT_HOURS` | `24` | Default repeat interval if an item stays triggered |
| `STATE_FILE` | `/data/state.json` | Persistent monitor state |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `TZ` | `America/Toronto` | Local timezone shown in container logs |
| `CHROME_BINARY` | `/usr/bin/chromium` | Chromium executable |
| `CHROMEDRIVER_BINARY` | `/usr/bin/chromedriver` | Chromium Driver executable |

After changing `.env`, recreate the container:

```bash
sudo docker compose up -d --force-recreate
```

A rebuild is normally unnecessary for `.env` changes.

---

# Product monitoring

Product rules are stored in:

```text
products.json
```

You can monitor multiple products from different websites in the same file.

Example:

```json
[
  {
    "id": "amazon-bench",
    "name": "Bench",
    "url": "https://www.amazon.ca/dp/XXXXXXXXXX",
    "target_price": 229
  },
  {
    "id": "store-jacket",
    "name": "Winter Jacket",
    "url": "https://example.com/jacket",
    "target_price": 199.99,
    "price_selector": ".product-price"
  }
]
```

---

## How price detection works

Price extraction follows this order.

### Step 1 — Explicit configured selector

If the product contains:

```json
"price_selector": ".product-price"
```

or:

```json
"price_selectors": [
  ".sale-price",
  ".current-price"
]
```

those selectors are tried first.

This is the highest-confidence method because you explicitly tell the monitor which DOM element contains the price.

### Step 2 — Amazon parser

If the parser is `amazon`, the monitor tries known Amazon price selectors including:

```text
#corePrice_feature_div .a-price.apex-pricetopay-value
#corePriceDisplay_desktop_feature_div .a-price.apex-pricetopay-value
#corePriceDisplay_desktop_feature_div .a-price.priceToPay
#price_inside_buybox
#priceblock_dealprice
#priceblock_ourprice
```

Only visible main-offer containers are accepted; struck-through prices are excluded.
The parser reads whole/fraction price nodes when the accessibility price is blank.
It waits for a valid offer price and stops with an error if none is found.
Amazon pages never fall back to whole-page prices or generic product metadata.

### Step 3 — JSON-LD Product data

For generic sites, the monitor searches:

```html
<script type="application/ld+json">
```

and looks for Schema.org-style:

```json
{
  "@type": "Product",
  "offers": {
    "price": "129.99"
  }
}
```

It currently recognizes:

```text
offers.price
offers.lowPrice
```

including arrays of offers.

### Step 4 — Standard product metadata

The monitor also checks common structured metadata such as:

```html
<meta property="product:price:amount" content="129.99">
<meta property="og:price:amount" content="129.99">
<meta itemprop="price" content="129.99">
<span itemprop="price">129.99</span>
```

### No unsafe whole-page price guessing

If none of those methods work, the monitor stops with an error and asks you to configure `price_selector`.

It does **not** simply select the first dollar amount found on the page.

That is intentional.

---

# products.json schema

Each product is a JSON object.

| Field | Required | Default | Description |
|---|---|---|---|
| `id` | No | generated | Stable key for state tracking; strongly recommended |
| `name` | No | page title | Friendly product name |
| `url` | **Yes** | — | Product URL |
| `target_price` | **Yes** | — | Alert when current price is at or below this value |
| `currency` | No | `CAD` | Currency label used in logs/Telegram |
| `parser` | No | `auto` | `auto`, `amazon`, or `generic` |
| `price_selector` | No | — | One CSS selector for the exact price node |
| `price_selectors` | No | — | Ordered array of price CSS selectors |
| `price_attribute` | No | `text` | Read text or an HTML attribute such as `content` |
| `price_regex` | No | — | Regex to isolate the price from the selected value |
| `wait_selector` | No | — | Wait for this element before parsing |
| `title_selector` | No | — | Optional custom product title element |
| `title_attribute` | No | `text` | Attribute used with `title_selector` |
| `repeat_alert_hours` | No | env default | Repeat interval while price remains triggered |
| `enabled` | No | `true` | Set false to disable without deleting |

## About `id`

Use stable IDs:

```json
"id": "nike-pegasus-black"
```

The ID is used as the key in `data/state.json`.

If you change the ID, the monitor treats it as a new item with new alert history.

If `id` is omitted:

- Amazon URLs may use the ASIN.
- Other URLs use a generated hash.

Explicit IDs are easier to understand and maintain.

---

# Amazon example

```json
{
  "id": "finer-form-bench",
  "name": "Finer Form Multi-Functional Weight Bench",
  "parser": "amazon",
  "url": "https://www.amazon.ca/dp/B08YWHN79N",
  "target_price": 229,
  "currency": "CAD",
  "repeat_alert_hours": 24
}
```

You can also use:

```json
"parser": "auto"
```

For `amazon.ca`, auto mode recognizes the domain and selects the Amazon parser.

---

# Generic automatic example

Many stores expose enough structured data that no selector is needed:

```json
{
  "id": "running-shoes",
  "name": "Running Shoes",
  "parser": "generic",
  "url": "https://example.com/products/running-shoes",
  "target_price": 149.99,
  "currency": "CAD"
}
```

The monitor will try:

1. JSON-LD Product/Offer data.
2. Standard product price metadata.

If it succeeds, logs may look similar to:

```text
[running-shoes] Price candidate 139.99 from JSON-LD Product offers (...)
[running-shoes] Current price: C$139.99 (target C$149.99)
```

---

# Generic CSS selector example

If structured data is unavailable:

```json
{
  "id": "winter-jacket",
  "name": "Winter Jacket",
  "parser": "generic",
  "url": "https://example.com/products/winter-jacket",
  "target_price": 199.99,
  "currency": "CAD",
  "price_selector": ".product-price"
}
```

If the page contains:

```html
<div class="product-price">C$189.99</div>
```

the monitor extracts:

```text
189.99
```

and compares it with:

```text
199.99
```

---

# Meta-tag price example

Some stores place the price in a meta tag:

```html
<meta property="product:price:amount" content="89.99">
```

Explicit configuration:

```json
{
  "id": "meta-price-product",
  "name": "Meta Price Product",
  "url": "https://example.com/product",
  "target_price": 79.99,
  "price_selector": "meta[property='product:price:amount']",
  "price_attribute": "content"
}
```

The important part is:

```json
"price_attribute": "content"
```

because meta tags do not display their value as visible text.

---

# Multiple price selectors

Websites often change CSS class names or render separate desktop/mobile price elements.

You can provide fallbacks:

```json
{
  "id": "multi-selector-product",
  "name": "Example Product",
  "url": "https://example.com/item",
  "target_price": 99.99,
  "price_selectors": [
    ".sale-price",
    ".current-price",
    "[data-testid='price']",
    "[itemprop='price']"
  ]
}
```

Selectors are tried in order.

The first valid price wins.

This is useful when:

- sale and regular price use different elements;
- mobile and desktop markup differ;
- a site changes one selector but keeps another;
- A/B testing changes the page structure.

---

# JavaScript-heavy pages

Some pages initially load without the price and insert it later with JavaScript.

Use:

```json
"wait_selector": "[data-testid='price']"
```

Full example:

```json
{
  "id": "dynamic-price-product",
  "name": "Dynamic Product",
  "url": "https://example.com/product",
  "target_price": 129.99,
  "price_selector": "[data-testid='price']",
  "wait_selector": "[data-testid='price']"
}
```

The monitor waits up to:

```env
ELEMENT_WAIT_SECONDS=12
```

for the element to exist.

It then additionally waits:

```env
PAGE_LOAD_WAIT_SECONDS=4
```

before parsing.

If a site is especially slow, increase those values in `.env`.

---

# Using price_regex

Sometimes a price element contains multiple numbers:

```text
Was $199.99 — Now $149.99 — Save 25%
```

A simple parser might pick the wrong number.

Use `price_regex`:

```json
{
  "id": "regex-product",
  "name": "Sale Product",
  "url": "https://example.com/product",
  "target_price": 160,
  "price_selector": ".pricing-box",
  "price_regex": "Now\\s*\\$([0-9]+(?:\\.[0-9]{2})?)"
}
```

When a capture group exists, the monitor uses capture group 1.

In this example it extracts:

```text
149.99
```

not:

```text
199.99
```

or:

```text
25
```

---

# Custom product title selectors

Normally the configured `name` is used.

If `name` is empty, the monitor tries Open Graph/Twitter title metadata and then the browser title.

You can explicitly read a title element:

```json
{
  "id": "custom-title-product",
  "url": "https://example.com/item",
  "target_price": 100,
  "price_selector": ".price",
  "title_selector": "h1.product-name"
}
```

Or from an attribute:

```json
"title_selector": "meta[property='og:title']",
"title_attribute": "content"
```

---

# Multiple currencies

The monitor compares numeric values exactly as provided by the website.

It does **not** perform currency conversion.

Examples:

```json
"currency": "CAD"
```

Telegram/log formatting:

```text
C$129.99
```

For:

```json
"currency": "USD"
```

formatting is:

```text
US$129.99
```

Other codes are displayed as:

```text
EUR 129.99
GBP 129.99
```

Make sure `target_price` uses the same currency as the page.

---

# Rakuten Cash Back monitoring

Rakuten rules are intentionally kept in:

```text
cashback.json
```

instead of `products.json`.

A product monitor compares a currency amount.

A Rakuten monitor compares a percentage.

---

# cashback.json schema

| Field | Required | Default | Description |
|---|---|---|---|
| `id` | No | generated | Stable state key |
| `name` | No | `Rakuten Cash Back` | Merchant name |
| `url` | **Yes** | — | Rakuten.ca merchant page |
| `threshold_percent` | **Yes** | — | Percentage threshold |
| `comparison` | No | `gt` | `gt` or `gte` |
| `repeat_alert_hours` | No | env default | Reminder interval |
| `enabled` | No | `true` | Disable monitor without deleting |

## comparison values

```json
"comparison": "gt"
```

means:

```text
rate > threshold
```

Example:

```text
threshold = 10
10%  → no alert
11%  → alert
15%  → alert
```

```json
"comparison": "gte"
```

means:

```text
rate >= threshold
```

Example:

```text
threshold = 10
10%  → alert
11%  → alert
```

---

# Sporting Life example

Current configuration:

```json
{
  "id": "sportinglife-rakuten",
  "name": "Sporting Life",
  "url": "https://www.rakuten.ca/sportinglife",
  "threshold_percent": 10,
  "comparison": "gt",
  "repeat_alert_hours": 24
}
```

Telegram example when it reaches 12%:

```text
💰 Rakuten Cash Back Alert

Sporting Life
Cash Back: 12%
Threshold: > 10%

https://www.rakuten.ca/sportinglife
```

---

# Cash Back alert behavior

Suppose the rule is:

```text
> 10%
```

and the rate changes like this:

```text
2%   → no alert
8%   → no alert
10%  → no alert
12%  → ALERT
12%  → no immediate duplicate alert
15%  → ALERT because rate increased further
8%   → state resets to below threshold
11%  → ALERT because threshold was crossed again
```

If the rate remains above the threshold continuously, `repeat_alert_hours` controls reminder notifications.

Set:

```json
"repeat_alert_hours": 0
```

to disable repeat reminders while the condition remains true.

---

# Live configuration reload

Both configuration files are bind-mounted by Docker Compose:

```yaml
volumes:
  - ./data:/data
  - ./products.json:/app/products.json:ro
  - ./cashback.json:/app/cashback.json:ro
```

That means after the current Docker image is installed, you can edit:

```text
products.json
cashback.json
```

without rebuilding the image.

The next monitoring cycle reloads both files.

The files load independently: a product configuration error skips product checks for
that cycle, while a cashback configuration error skips cashback checks. The other
type of monitor continues. Errors are logged and the files are retried next cycle.

Example:

```bash
nano products.json
```

Save the file.

Within the next cycle, logs should show the updated monitor count.

No command is required unless the JSON is invalid.

---

# Alert behavior and state

## Product prices

For a product with:

```text
target_price = 229
```

the trigger is:

```text
current_price <= 229
```

The monitor alerts when:

1. The product first reaches or falls below the target.
2. The price decreases further while already below the target.
3. The configured reminder period expires while it remains below the target.

Example:

```text
C$279.99 → no alert
C$229.00 → ALERT
C$229.00 → no immediate duplicate
C$219.99 → ALERT because it dropped further
C$250.00 → above target; crossing state resets
C$225.00 → ALERT again
```

## Why duplicate suppression matters

Without state, a five-minute monitor would send an alert every five minutes for the entire duration of a sale.

The state system prevents that.

Crossing state advances only after a required Telegram alert succeeds, so a failed
delivery is retried next cycle while the threshold condition still holds.

---

# State file

Persistent state is stored in:

```text
./data/state.json
```

Inside the container:

```text
/data/state.json
```

The file records information such as:

- last check time;
- last seen price;
- last alert price;
- last alert time;
- whether the product is currently below target;
- last seen Rakuten rate;
- whether a Rakuten rule is currently above threshold;
- last parsing error.

State timestamps are stored in UTC even though logs may display Toronto local time.

## Reset all alert state

If you intentionally want every monitor to behave like a brand-new monitor:

```bash
sudo docker compose down
rm -f data/state.json
sudo docker compose up -d
```

This deletes alert history.

Do not do this merely because you edited `products.json`.

---

# Logs

Follow logs:

```bash
sudo docker compose logs -f
```

Show the most recent 100 lines:

```bash
sudo docker compose logs --tail=100
```

## Typical startup

```text
Shopping deal monitor started; interval=300s
Loaded 1 product(s) and 1 cashback monitor(s)
Watching product [finer-form-bench] ...
Watching Rakuten [sportinglife-rakuten] ...
```

## Typical product check

```text
[finer-form-bench] Price candidate 279.99 from Amazon selector ...
[finer-form-bench] Current price: C$279.99 (target C$229.00)
```

## Generic structured-data check

```text
[running-shoes] Price candidate 139.99 from JSON-LD Product offers (...)
[running-shoes] Current price: C$139.99 (target C$149.99)
```

## Rakuten check

```text
[sportinglife-rakuten] Rakuten cashback candidate 2.00%
[sportinglife-rakuten] Current Cash Back: 2.00% (alert > 10.00%)
```

## Telegram success

```text
Telegram alert sent.
```

---

# Updating the Raspberry Pi

Pull latest code:

```bash
cd ~/amazon_telegram_price_monitor
git pull origin main
```

If Python code, Dockerfile, requirements, or Compose configuration changed:

```bash
sudo docker compose down
sudo docker compose build --no-cache
sudo docker compose up -d
sudo docker compose logs -f
```

For normal future updates, `--no-cache` is optional:

```bash
sudo docker compose build
```

## Configuration-only changes

If only:

```text
products.json
cashback.json
```

changed locally, no rebuild is needed.

The running process reloads them each cycle.

---

# Adding another product

Edit:

```bash
nano products.json
```

Example with two products:

```json
[
  {
    "id": "finer-form-bench",
    "name": "Finer Form Multi-Functional Weight Bench",
    "parser": "amazon",
    "url": "https://www.amazon.ca/dp/B08YWHN79N",
    "target_price": 229,
    "currency": "CAD"
  },
  {
    "id": "another-product",
    "name": "Another Product",
    "url": "https://example.com/product",
    "target_price": 149.99,
    "currency": "CAD",
    "price_selector": ".product-price"
  }
]
```

Validate before waiting for the next cycle:

```bash
python3 -m json.tool products.json >/dev/null && echo "products.json OK"
```

---

# Adding another Rakuten merchant

Edit:

```bash
nano cashback.json
```

Example:

```json
[
  {
    "id": "sportinglife-rakuten",
    "name": "Sporting Life",
    "url": "https://www.rakuten.ca/sportinglife",
    "threshold_percent": 10,
    "comparison": "gt"
  },
  {
    "id": "example-store-rakuten",
    "name": "Example Store",
    "url": "https://www.rakuten.ca/example-store",
    "threshold_percent": 12,
    "comparison": "gte"
  }
]
```

Validate:

```bash
python3 -m json.tool cashback.json >/dev/null && echo "cashback.json OK"
```

---

# Finding a CSS price selector

When generic automatic extraction fails, you need the CSS selector for the real product price.

## Chrome / Chromium method

1. Open the product page in desktop Chrome.
2. Right-click directly on the displayed price.
3. Choose **Inspect**.
4. DevTools highlights the HTML element.
5. Look for a stable class, ID, `data-*` attribute, or `itemprop`.

Example HTML:

```html
<span data-testid="product-price">C$149.99</span>
```

A good selector is:

```css
[data-testid='product-price']
```

Configuration:

```json
"price_selector": "[data-testid='product-price']"
```

## Prefer stable selectors

Usually better:

```css
#product-price
[data-testid='price']
[itemprop='price']
.product-price
```

Usually worse:

```css
div:nth-child(4) > div:nth-child(2) > span:nth-child(1)
```

Long positional selectors are fragile and often break when the site layout changes.

## If DevTools offers "Copy selector"

You can try:

```text
Right-click element → Copy → Copy selector
```

but inspect the result.

Automatically generated selectors can be unnecessarily long.

Simplify them when possible.

---

# Validation commands

## Run regression tests

With the project's Python dependencies installed:

```bash
python -m unittest -v test_monitor
```

The tests use simulated pages and Telegram responses; they send no messages.

## Check JSON syntax

```bash
python3 -m json.tool products.json >/dev/null && echo OK
python3 -m json.tool cashback.json >/dev/null && echo OK
```

## Check Docker Compose configuration

```bash
sudo docker compose config
```

## Verify Chromium inside the image

```bash
sudo docker compose run --rm amazon-price-monitor sh -lc \
'echo ARCH=$(uname -m); which chromium; chromium --version; which chromedriver; chromedriver --version'
```

Expected Raspberry Pi-style output:

```text
ARCH=aarch64
/usr/bin/chromium
Chromium ...
/usr/bin/chromedriver
ChromeDriver ...
```

## Check container time

```bash
sudo docker compose exec amazon-price-monitor date
```

With:

```env
TZ=America/Toronto
```

it should show Toronto local time.

---

# Troubleshooting

## Unable to obtain driver for chrome

Example:

```text
Unsupported platform/architecture combination: linux/aarch64
Unable to obtain driver for chrome
```

The project already addresses this by explicitly using:

```text
/usr/bin/chromedriver
```

If it still happens, confirm the binaries:

```bash
sudo docker compose run --rm amazon-price-monitor sh -lc \
'which chromium; chromium --version; which chromedriver; chromedriver --version'
```

Then rebuild:

```bash
sudo docker compose down
sudo docker compose build --no-cache
sudo docker compose up -d
```

---

## Log time is four hours ahead

If you are in Toronto during daylight time and logs appear in UTC, confirm:

```env
TZ=America/Toronto
```

Then recreate:

```bash
sudo docker compose up -d --force-recreate
```

Check:

```bash
sudo docker compose exec amazon-price-monitor date
```

---

## Could not determine this product's price safely

Typical error:

```text
Could not determine this product's price safely.
Add 'price_selector' ...
```

This means:

- no configured selector produced a valid price;
- no recognized structured product metadata was found;
- the page may render prices dynamically;
- the page may require interaction;
- the page structure may have changed.

First try adding:

```json
"price_selector": ".actual-price-selector"
```

For JavaScript rendering also add:

```json
"wait_selector": ".actual-price-selector"
```

---

## Configured selector did not produce a valid price

Confirm the selector still matches the page.

The website may have changed from:

```css
.product-price
```

to something like:

```css
.sale-price
```

Use multiple fallback selectors:

```json
"price_selectors": [
  ".sale-price",
  ".product-price"
]
```

---

## Wrong price extracted

If your selector contains:

```text
Was $200 — Now $150
```

use `price_regex` so the monitor knows which number to select.

Example:

```json
"price_regex": "Now\\s*\\$([0-9]+(?:\\.[0-9]{2})?)"
```

Also check whether the page displays:

- regular price;
- member price;
- sale price;
- variant price;
- financing monthly payment;
- price range.

The monitor can only apply the rule you configure.

---

## Price is for the wrong size/color/variant

Some ecommerce pages change price based on selected product variant.

The monitor currently loads the URL as supplied and does not automatically click a size/color selector.

Possible solutions:

- use a URL that directly identifies the desired variant;
- use a page where the default variant is the one you want;
- add site-specific interaction logic in code if necessary.

Do not assume one displayed price applies to every variant.

---

## Amazon bot/challenge page

Amazon may occasionally show a challenge page.

Logs can contain:

```text
Amazon returned a bot/challenge page.
```

Potential mitigations:

- do not check excessively often;
- keep `CHECK_INTERVAL_SECONDS` reasonably high;
- avoid running multiple duplicate monitors for the same page.

Five minutes is currently a reasonable default, but no interval guarantees Amazon will never challenge automation.

---

## Rakuten rate cannot be found

If logs show:

```text
Could not find the Rakuten Cash Back percentage on the page.
```

Rakuten may have changed its page title/meta markup or page rendering.

Check the merchant page manually.

This parser currently looks for text shaped like:

```text
2% Cash Back
10% Cash Back
15% Cash Back
```

and supports:

```text
Up to 15% Cash Back
```

A markup change may require updating the parser.

---

## Telegram is not sending

Confirm both values exist:

```bash
grep '^TELEGRAM_' .env
```

Do not paste the output publicly because it can expose your token.

Confirm your bot has received at least one message from you.

Then rerun:

```bash
sudo docker compose run --rm amazon-price-monitor python get_chat_id.py
```

Check logs for HTTP or Telegram API errors.

---

## JSON syntax error

A missing comma is enough to break the entire configuration load.

Bad:

```json
{
  "name": "Product"
  "url": "https://example.com"
}
```

Good:

```json
{
  "name": "Product",
  "url": "https://example.com"
}
```

Validate:

```bash
python3 -m json.tool products.json
```

---

## Container keeps restarting

Check:

```bash
sudo docker compose ps
sudo docker compose logs --tail=200
```

Also validate:

```bash
sudo docker compose config
```

---

# Security notes

## Never commit .env

`.env` contains your Telegram bot token and chat ID.

The repository's `.gitignore` excludes:

```text
.env
```

Before pushing code, check:

```bash
git status
```

You should not see `.env` staged.

## If a Telegram token is accidentally exposed

Use BotFather to revoke/regenerate the bot token.

Then update your local `.env` and recreate the container.

Do not merely delete the token from the latest Git commit. Git history may still contain it.

## Configuration files are public if the repository is public

Do not place:

- passwords;
- cookies;
- account tokens;
- authenticated URLs containing secrets;
- session IDs;

inside `products.json` or `cashback.json` in a public repository.

---

# Known limitations

This monitor intentionally focuses on simple, reliable threshold checks.

Current limitations include:

1. **No automatic taxes**
   - Product thresholds are based on the extracted displayed price.
   - Tax is not added.

2. **No shipping calculation**
   - Shipping fees are not included unless the page itself includes them in the extracted value.

3. **No coupon calculation**
   - A checkout-only coupon may not be reflected in the displayed product price.

4. **No account-specific/member pricing**
   - The browser is not logged into your shopping accounts.
   - Member-only prices may differ.

5. **No automatic currency conversion**
   - `target_price` must use the same currency as the page.

6. **No universal variant selection**
   - Size/color/model selections are not automatically clicked.

7. **Website markup can change**
   - CSS selectors and parsers may require maintenance.

8. **Anti-bot systems**
   - Retailers can block or challenge automated browsers.

9. **No guarantee of exact instant detection**
   - Detection occurs on each scheduled cycle.
   - With the default 300-second interval, a change may be detected several minutes after it appears.

10. **Rakuten parser is currently Rakuten.ca-specific**
    - `cashback.json` rejects non-Rakuten.ca hosts.

---

# Useful Docker commands

## Start

```bash
sudo docker compose up -d
```

## Stop

```bash
sudo docker compose down
```

## Restart

```bash
sudo docker compose restart
```

## Recreate after .env changes

```bash
sudo docker compose up -d --force-recreate
```

## Rebuild after code changes

```bash
sudo docker compose build
sudo docker compose up -d
```

## Full clean rebuild

```bash
sudo docker compose down
sudo docker compose build --no-cache
sudo docker compose up -d
```

## Logs

```bash
sudo docker compose logs -f
```

## Last 200 log lines

```bash
sudo docker compose logs --tail=200
```

## Container status

```bash
sudo docker compose ps
```

## Shell inside container

```bash
sudo docker compose exec amazon-price-monitor sh
```

## Check date/time

```bash
sudo docker compose exec amazon-price-monitor date
```

---

# Recommended workflow

For normal daily use:

1. Leave Docker running continuously.
2. Edit `products.json` when you want to add/remove product price monitors.
3. Edit `cashback.json` when you want to add/remove Rakuten monitors.
4. Validate JSON before saving.
5. Watch logs after adding a new site.
6. If automatic price detection fails, add an explicit `price_selector`.
7. Only rebuild Docker when program code or Docker dependencies change.

Example:

```bash
cd ~/amazon_telegram_price_monitor

nano products.json
python3 -m json.tool products.json >/dev/null && echo OK

sudo docker compose logs -f
```

Once a generic site's selector is correct, the monitor can continue watching it alongside Amazon and Rakuten from the same Raspberry Pi.
