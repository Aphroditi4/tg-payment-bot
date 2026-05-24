# VCommunity Telegram CRM Bot

Aiogram MVP for manual payments by requisites, payment-proof upload, Telegram admin review, CRM queue flows, VIP gating, private chat subscriptions, and admin commands.

## Implemented Flow

```text
/start
-> service selection
-> service description
-> payment requisites + Order ID
-> user clicks "Я оплатив"
-> user uploads screenshot / PDF / receipt photo
-> bot collects name, Telegram username, phone, optional comment
-> admin receives CRM card with attached proof
-> admin confirms / rejects / asks again / moves to queue
-> service-specific flow starts after payment confirmation
```

## Services

- Consultation - 50 EUR: after confirm, user fills a questionnaire and the request goes to CRM.
- Legit Check - 3 EUR / item: after confirm, user uploads item photos and the request goes to moderator queue.
- Chat Group - 13 EUR / month: after confirm, bot creates a private invite link and tracks a 30-day subscription.
- Готовий акаунт Vinted - 15 EUR prepayment / 115 EUR after manager review: after confirm, user fills a VIP questionnaire and goes to VIP Queue.
- Vinted Buyout - VIP only: user must be VIP, submits item link/price/comment, pays, then order moves to Processing after confirm.

## Admin Access

Admin panel is inside Telegram. Access is checked by Telegram user ID.

The current hardcoded admin ID is in:

```python
app/config.py
HARDCODED_ADMIN_IDS = {1363148895}
```

You can also add comma-separated IDs in `.env`:

```env
ADMIN_IDS=1363148895,123456789
```

Admin commands:

```text
/admin
/orders
/pending
/confirmed
/rejected
/vip
/queue
/broadcast <text>
```

Admin actions under a payment card:

```text
Confirm Payment
Reject Payment
Ask User Again
Move to Queue
Processing
Done
```

## Setup

```powershell
cd D:\ForWork\tg-payment-bot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Fill `.env`:

- `BOT_TOKEN` - token from BotFather.
- `ADMIN_IDS` - Telegram user IDs allowed to use admin commands and buttons.
- `ADMIN_REVIEW_CHAT_ID` - optional admin group/channel for CRM cards. If empty, bot sends cards directly to admins.
- `PRIVATE_CHAT_ID` - optional private chat/group for Chat Group invite links. Bot must be admin there.
- payment requisites: `PAYMENT_IBAN`, `PAYMENT_CARD`, `PAYMENT_USDT_TRC20`, etc.

## Run

```powershell
python -m app.main
```

or:

```powershell
.\run.ps1
```

## Database

Current MVP uses SQLite for local simplicity. Tables:

- `users`
- `orders`
- `payment_proofs`
- `admin_reviews`
- `vip_queue`
- `subscriptions`
- `consultations`
- `legit_check`
- `buyout_orders`

The schema is intentionally close to the PostgreSQL target, so Railway/PostgreSQL migration can be done later without changing bot flows.
