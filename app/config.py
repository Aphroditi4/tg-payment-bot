import os
from dataclasses import dataclass

from dotenv import load_dotenv


# Hardcoded Telegram user IDs that can use the admin panel.
# Replace/add IDs here when a new admin must be allowed.
HARDCODED_ADMIN_IDS = {1363148895, 363161985, 5768681665}


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
    recipients: str
    lev_name: str
    lev_iban: str
    lev_monobank: str
    stelmakh_name: str
    stelmakh_iban: str
    stelmakh_card: str
    revolut_iban: str
    revolut_tag: str
    wise_tag: str
    wise_iban: str
    usdt_trc20: str
    usdc_erc20: str
    binance_id: str


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


PAYMENT_PLACEHOLDERS = {
    "VCommunity",
    "UA00 0000 0000 0000 0000 0000 000",
    "0000 0000 0000 0000",
    "Monobank: 0000 0000 0000 0000",
    "PrivatBank: 0000 0000 0000 0000",
    "Wise: example@vcommunity.com",
    "Revolut: @vcommunity",
    "SEPA IBAN: XXXX XXXX XXXX",
    "USDT TRC20: TXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
    "USDC TRC20: TXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
    "BTC: bc1xxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "ETH: 0x0000000000000000000000000000000000000000",
}


def _payment_env(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    if not value or value in PAYMENT_PLACEHOLDERS:
        return default
    return value


def _load_payment_details() -> PaymentDetails:
    return PaymentDetails(
        recipients=_payment_env("PAYMENT_RECIPIENTS", "Lev Korunov / Stelmakh Maksym"),
        lev_name=_payment_env("PAYMENT_LEV_NAME", "Lev Korunov"),
        lev_iban=_payment_env("PAYMENT_LEV_IBAN", "UA113220010000026200318219054"),
        lev_monobank=_payment_env("PAYMENT_LEV_MONOBANK", "4441111025358593"),
        stelmakh_name=_payment_env("PAYMENT_STELMAKH_NAME", "Stelmakh Maksym"),
        stelmakh_iban=_payment_env("PAYMENT_STELMAKH_IBAN", "UA313052990000026205696398065"),
        stelmakh_card=_payment_env("PAYMENT_STELMAKH_CARD", "5457082256824330"),
        revolut_iban=_payment_env("PAYMENT_REVOLUT_IBAN", "LT143250010412806160"),
        revolut_tag=_payment_env("PAYMENT_REVOLUT_TAG", "@maksymstelmakh"),
        wise_tag=_payment_env("PAYMENT_WISE_TAG", "@stelmahmaksims"),
        wise_iban=_payment_env("PAYMENT_WISE_IBAN", "BE84967315589159"),
        usdt_trc20=_payment_env("PAYMENT_USDT_TRC20", "TB3VtywkDdBtcAuJnSA8FVxk6suA78iiKb"),
        usdc_erc20=_payment_env("PAYMENT_USDC_ERC20", "0x3af7ecbd55ed45c8b6704cd65f63f80c633f65cd"),
        binance_id=_payment_env("PAYMENT_BINANCE_ID", "424934326"),
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
