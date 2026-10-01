# Shopping Deal Monitor → Telegram

Dockerized Raspberry Pi / ARM64 monitor for:

- product prices on Amazon.ca and other shopping websites
- Rakuten.ca Cash Back rates

Telegram alerts are sent only when a configured threshold is triggered.

## Generic product monitoring

`products.json` is now site-independent.

The monitor uses this order:

1. An explicit CSS selector from `price_selector` / `price_selectors`, if configured.
2. Amazon-specific selectors when `parser` is `amazon`.
3. Standard Product/Offer JSON-LD.
4. Standard product price metadata such as `product:price:amount` and `itemprop=price`.

It intentionally does **not** scan the entire page for the first dollar amount. If a site does not expose safe structured price data, add a CSS selector for the exact price element.

### Amazon example

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

`parser: "auto"` is the default. It automatically recognizes Amazon.ca URLs as Amazon and treats other domains as generic.

### Generic site — automatic structured-data detection

Many Shopify and modern commerce sites expose JSON-LD or product metadata, so this can be enough:

```json
{
  "id": "my-shoes",
  "name": "Running Shoes",
  "parser": "generic",
  "url": "https://example.com/products/running-shoes",
  "target_price": 149.99,
  "currency": "CAD"
}
```

### Generic site — explicit CSS price selector

If automatic detection cannot safely find the price:

```json
{
  "id": "my-jacket",
  "name": "Winter Jacket",
  "parser": "generic",
  "url": "https://example.com/products/winter-jacket",
  "target_price": 199.99,
  "currency": "CAD",
  "price_selector": ".product-price"
}
```

The default `price_attribute` is `text`.

If the price is stored in a meta tag or HTML attribute:

```json
{
  "id": "meta-price-item",
  "name": "Example Item",
  "parser": "generic",
  "url": "https://example.com/product/123",
  "target_price": 99.99,
  "price_selector": "meta[property='product:price:amount']",
  "price_attribute": "content"
}
```

You can supply several candidate selectors:

```json
{
  "id": "multi-selector-item",
  "name": "Example Item",
  "url": "https://example.com/product/456",
  "target_price": 79.99,
  "price_selectors": [
    ".sale-price",
    ".current-price",
    "[itemprop='price']"
  ]
}
```

### JavaScript-heavy pages

If the page renders its price after initial page load, use `wait_selector`:

```json
{
  "id": "dynamic-item",
  "name": "Dynamic Product",
  "url": "https://example.com/dynamic-product",
  "target_price": 129.99,
  "price_selector": "[data-testid='price']",
  "wait_selector": "[data-testid='price']"
}
```

The maximum wait is controlled by `ELEMENT_WAIT_SECONDS` in `.env`.

### Price regex

If the selected element contains several values, `price_regex` can isolate the real price. Capture group 1 is used when present.

```json
{
  "id": "regex-item",
  "name": "Example Item",
  "url": "https://example.com/item",
  "target_price": 100,
  "price_selector": ".pricing-box",
  "price_regex": "Now\\s*\\$([0-9]+(?:\\.[0-9]{2})?)"
}
```

## Product configuration fields

- `id` — optional stable state key; recommended.
- `name` — optional display name.
- `url` — required product URL.
- `target_price` — required alert price.
- `currency` — defaults to `CAD`; `USD` is also formatted specially.
- `parser` — `auto` (default), `amazon`, or `generic`.
- `price_selector` — optional CSS selector for the price node.
- `price_selectors` — optional ordered list of CSS selectors.
- `price_attribute` — defaults to `text`; can be `content`, `value`, etc.
- `price_regex` — optional regex to extract the price from the selected value.
- `wait_selector` — optional CSS selector to wait for before parsing.
- `title_selector` — optional CSS selector for the product title.
- `title_attribute` — defaults to `text`.
- `repeat_alert_hours` — repeat interval while still at/below target; `0` disables reminders.
- `enabled` — set to `false` to temporarily disable the item.

## Live product configuration

`products.json` is bind-mounted into the container. You can add, remove, or edit products while the monitor is running. Changes are loaded on the next check cycle without a Docker rebuild or restart.

## Rakuten Cash Back monitoring

`cashback.json` is separate because it monitors a percentage rather than a product price.

Current Sporting Life example:

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

`comparison: "gt"` means strictly greater than 10%.

## Telegram setup

Create a bot with **@BotFather**, then:

```bash
cp .env.example .env
nano .env
```

Set:

```env
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

To retrieve the chat ID after messaging the bot:

```bash
sudo docker compose build
sudo docker compose run --rm amazon-price-monitor python get_chat_id.py
```

## Update the Raspberry Pi

This code change requires one rebuild:

```bash
cd ~/amazon_telegram_price_monitor
git pull origin main

sudo docker compose down
sudo docker compose build --no-cache
sudo docker compose up -d
sudo docker compose logs -f
```

After that, edits to `products.json` or `cashback.json` are live and do not require another rebuild.

## Time zone

The example environment uses:

```env
TZ=America/Toronto
```

Logs use Toronto local time. State timestamps remain UTC.

## Check frequency

Default:

```env
CHECK_INTERVAL_SECONDS=300
```

That checks all configured monitors every five minutes. Very frequent checks may increase the chance a retailer serves a bot/challenge page.
