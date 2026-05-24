import os
from dataclasses import dataclass

from dotenv import load_dotenv


# Hardcoded Telegram user IDs that can use the admin panel.
# Replace/add IDs here when a new admin must be allowed.
HARDCODED_ADMIN_IDS = {1363148895}


@dataclass(frozen=True)
class Service:
    key: str
    title: str
    price: str
    description: str
    subtitle: str | None = None
    vip_only: bool = False


@dataclass(frozen=True)
class PaymentDetails:
    recipient_name: str
    iban: str
    card: str
    monobank: str
    privat: str
    wise: str
    revolut: str
    sepa_iban: str
    usdt_trc20: str
    usdc_trc20: str
    btc: str
    eth: str


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: set[int]
    admin_review_chat_id: int | None
    private_chat_id: int | None
    services: list[Service]
    database_path: str
    manager_username: str
    manager_link: str
    support_link: str
    payment_details: PaymentDetails


DEFAULT_SERVICES = [
    Service(
        key="consultation",
        title="Консультація",
        price="50 EUR",
        description=(
            "Персональна консультація по банам, просуванню, збільшенню продажів "
            "та роботі з європейськими маркетплейсами."
        ),
    ),
    Service(
        key="legit_check",
        title="Legit Check",
        price="3 EUR / item",
        description=(
            "Перевірка товару модератором. Після підтвердження оплати бот попросить "
            "завантажити фото товару."
        ),
    ),
    Service(
        key="chat_group",
        title="Chat Group",
        price="13 EUR / місяць",
        description=(
            "Доступ до закритого чату VCommunity на 30 днів. Після підтвердження "
            "оплати бот видасть invite link."
        ),
    ),
    Service(
        key="vip_service",
        title="VIP Europe Service",
        subtitle="Готовий аккаунт Vinted",
        price="15 EUR передплата",
        description=(
            "Послуга для старту продажів на Vinted у Європі. Ви залишаєте передплату "
            "15 EUR, заповнюєте анкету, після чого заявка потрапляє в VIP Queue "
            "на manager review. Якщо заявку підтверджено, доплата за готовий акаунт "
            "становить 115 EUR."
        ),
    ),
    Service(
        key="vinted_buyout",
        title="Vinted Buyout",
        price="15% від ціни товару",
        description=(
            "Викуп товарів з Vinted. Доступно тільки користувачам зі статусом VIP."
        ),
        vip_only=True,
    ),
]


def _parse_admin_ids(raw: str) -> set[int]:
    result: set[int] = set()
    for item in raw.split(","):
        item = item.strip()
        if item:
            result.add(int(item))
    return result


def _parse_optional_int(raw: str | None) -> int | None:
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    return int(raw)


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _load_payment_details() -> PaymentDetails:
    return PaymentDetails(
        recipient_name=_env("PAYMENT_RECIPIENT_NAME", "VCommunity"),
        iban=_env("PAYMENT_IBAN", "UA00 0000 0000 0000 0000 0000 000"),
        card=_env("PAYMENT_CARD", "0000 0000 0000 0000"),
        monobank=_env("PAYMENT_MONOBANK", "Monobank: 0000 0000 0000 0000"),
        privat=_env("PAYMENT_PRIVAT", "PrivatBank: 0000 0000 0000 0000"),
        wise=_env("PAYMENT_WISE", "Wise: example@vcommunity.com"),
        revolut=_env("PAYMENT_REVOLUT", "Revolut: @vcommunity"),
        sepa_iban=_env("PAYMENT_SEPA_IBAN", "SEPA IBAN: XXXX XXXX XXXX"),
        usdt_trc20=_env("PAYMENT_USDT_TRC20", "USDT TRC20: TXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"),
        usdc_trc20=_env("PAYMENT_USDC_TRC20", "USDC TRC20: TXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"),
        btc=_env("PAYMENT_BTC", "BTC: bc1xxxxxxxxxxxxxxxxxxxxxxxxxxxx"),
        eth=_env("PAYMENT_ETH", "ETH: 0x0000000000000000000000000000000000000000"),
    )


def load_config() -> Config:
    load_dotenv()

    bot_token = _env("BOT_TOKEN")
    if not bot_token:
        raise ValueError("BOT_TOKEN is required")

    admin_ids = set(HARDCODED_ADMIN_IDS)
    admin_ids.update(_parse_admin_ids(_env("ADMIN_IDS")))
    if not admin_ids:
        raise ValueError("At least one admin ID is required")

    manager_username = _env("MANAGER_USERNAME", "m_ss66").lstrip("@")
    manager_link = _env("MANAGER_LINK", f"https://t.me/{manager_username}")

    return Config(
        bot_token=bot_token,
        admin_ids=admin_ids,
        admin_review_chat_id=_parse_optional_int(os.getenv("ADMIN_REVIEW_CHAT_ID")),
        private_chat_id=_parse_optional_int(os.getenv("PRIVATE_CHAT_ID")),
        services=DEFAULT_SERVICES,
        database_path=_env("DATABASE_PATH", "bot.db"),
        manager_username=manager_username,
        manager_link=manager_link,
        support_link=_env("SUPPORT_LINK", manager_link),
        payment_details=_load_payment_details(),
    )
