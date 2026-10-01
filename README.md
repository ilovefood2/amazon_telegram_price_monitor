# Amazon.ca → Telegram Multi-Product Price Monitor

Dockerized price monitor for Raspberry Pi / ARM64. It checks multiple Amazon.ca product URLs and sends a Telegram alert when any item reaches its own target price.

Default check interval: **5 minutes**.

## Configure products

All monitored items live in `products.json`:

```json
[
  {
    "id": "finer-form-bench",
    "name": "Finer Form Multi-Functional Weight Bench",
    "url": "https://www.amazon.ca/dp/B08YWHN79N",
    "target_price": 229,
    "repeat_alert_hours": 24
  },
  {
    "id": "another-item",
    "name": "Another Amazon item",
    "url": "https://www.amazon.ca/dp/XXXXXXXXXX",
    "target_price": 149.99,
    "repeat_alert_hours": 24
  }
]
```

Fields:

- `url` — required product URL.
- `target_price` — required alert threshold in CAD.
- `id` — optional but recommended stable identifier. If omitted, the Amazon ASIN (or a URL hash) is used.
- `name` — optional display name. The product title from Amazon is used when available.
- `repeat_alert_hours` — optional; defaults to `.env` `REPEAT_ALERT_HOURS`. Set to `0` to disable repeat reminders while the item remains under target.
- `enabled` — optional; set to `false` to temporarily skip an item.

`products.json` is mounted into the container. **You can edit it while the monitor is running; changes are loaded automatically on the next check cycle. No rebuild or restart is needed.**

## Telegram setup

1. Open Telegram and chat with **@BotFather**.
2. Send `/newbot` and follow the prompts.
3. Copy the bot token.
4. Create your local environment file:

```bash
cp .env.example .env
nano .env
```

Put the token in:

```env
TELEGRAM_BOT_TOKEN=your_token_here
```

Send any message such as `hi` to your new bot, then build and retrieve the chat ID:

```bash
sudo docker compose build
sudo docker compose run --rm amazon-price-monitor python get_chat_id.py
```

Put the returned ID into `.env`:

```env
TELEGRAM_CHAT_ID=123456789
```

## Start / update

```bash
sudo docker compose up -d
sudo docker compose logs -f
```

For this release, rebuild once because the Docker image now includes timezone data:

```bash
sudo docker compose down
sudo docker compose build --no-cache
sudo docker compose up -d
```

After that, adding/removing products only requires editing `products.json`.

## Add another product

Edit:

```bash
nano products.json
```

Add another object to the JSON array, save it, and leave the container running. On the next cycle the logs will show the new number of enabled products.

Validate the JSON before saving if desired:

```bash
python3 -m json.tool products.json >/dev/null && echo OK
```

## Notification behavior

Each product has independent state:

- Alerts immediately when it crosses from above target to at/below target.
- Alerts again if the price drops further.
- Can repeat after `repeat_alert_hours` while still under target.
- Crossing back above the target resets the crossing behavior, so a later drop below triggers a fresh alert.
- State is stored in `./data/state.json`.

Example Telegram alert:

```text
🔥 Amazon Price Alert

Finer Form Multi-Functional Weight Bench
Price: C$229.00
Target: C$229.00 or less

https://www.amazon.ca/dp/B08YWHN79N
```

## Time zone

`.env.example` sets:

```env
TZ=America/Toronto
```

Container logs therefore use Toronto local time. State timestamps remain UTC for reliable comparisons.

## Check frequency

Edit `.env`:

```env
CHECK_INTERVAL_SECONDS=300
```

Examples:

- `60` = every minute
- `300` = every 5 minutes
- `900` = every 15 minutes

Very frequent Amazon page checks increase the chance of Amazon returning a bot/challenge page. Five minutes is a reasonable default.
