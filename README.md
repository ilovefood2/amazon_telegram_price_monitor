# Shopping Deal Monitor → Telegram

Dockerized Raspberry Pi / ARM64 monitor for:

- Amazon.ca product prices
- Rakuten.ca Cash Back rates

Telegram alerts are sent only when a configured threshold is triggered.

## Current monitors

### Amazon

`products.json` contains Amazon product price rules.

### Rakuten

`cashback.json` currently watches Sporting Life:

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

`comparison: "gt"` means **strictly greater than 10%**. A 10% offer does not trigger; 10.5%, 12%, 15%, etc. do.

## Live configuration

Both configuration files are bind-mounted:

- `products.json`
- `cashback.json`

You can edit either file while the monitor is running. The changes are loaded on the next check cycle without another rebuild or restart.

## Rakuten alert behavior

For each cashback monitor:

- Crossing from at/below the threshold to above it sends an alert.
- If Cash Back increases again while already above the threshold, another alert is sent.
- If Cash Back drops back to/below the threshold, the crossing state resets.
- `repeat_alert_hours` controls reminder alerts while the deal remains triggered.
- Set `repeat_alert_hours` to `0` to disable repeat reminders.

Example:

```text
💰 Rakuten Cash Back Alert

Sporting Life
Cash Back: 12%
Threshold: > 10%

https://www.rakuten.ca/sportinglife
```

## Amazon product example

```json
[
  {
    "id": "finer-form-bench",
    "name": "Finer Form Multi-Functional Weight Bench",
    "url": "https://www.amazon.ca/dp/B08YWHN79N",
    "target_price": 229,
    "repeat_alert_hours": 24
  }
]
```

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

After pulling this code update, rebuild once because `monitor.py` and Docker mounts changed:

```bash
cd ~/amazon_telegram_price_monitor
git pull origin main

sudo docker compose down
sudo docker compose build --no-cache
sudo docker compose up -d
sudo docker compose logs -f
```

After that, changing only `products.json` or `cashback.json` does not require another rebuild.

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
