import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from app.config import Config, PaymentDetails, Service, load_config
from app.db import (
    STATUS_AWAITING_PROOF,
    STATUS_CONFIRMED,
    STATUS_DONE,
    STATUS_IN_QUEUE,
    STATUS_PENDING_REVIEW,
    STATUS_PROCESSING,
    STATUS_REJECTED,
    Database,
    status_label,
)
from app.keyboards import (
    admin_review_keyboard,
    legit_done_keyboard,
    locked_vip_keyboard,
    manager_keyboard,
    optional_comment_keyboard,
    payment_keyboard,
    phone_keyboard,
    retry_payment_keyboard,
    service_keyboard,
    services_keyboard,
)


class PaymentFlow(StatesGroup):
    waiting_for_proof = State()
    waiting_for_name = State()
    waiting_for_username = State()
    waiting_for_phone = State()
    waiting_for_comment = State()


class VintedFlow(StatesGroup):
    waiting_for_link = State()
    waiting_for_price = State()
    waiting_for_comment = State()


class ConsultationFlow(StatesGroup):
    waiting_for_questionnaire = State()


class LegitCheckFlow(StatesGroup):
    waiting_for_item_files = State()


class VIPFlow(StatesGroup):
    waiting_for_questionnaire = State()


class BroadcastFlow(StatesGroup):
    waiting_for_message = State()


router = Router()
config: Config
db: Database
dispatcher: Dispatcher


def find_service(service_key: str) -> Service | None:
    return next((service for service in config.services if service.key == service_key), None)


def is_admin(user_id: int | None) -> bool:
    return bool(user_id and user_id in config.admin_ids)


async def ensure_user(message: Message) -> None:
    if not message.from_user:
        return
    db.upsert_user(
        telegram_user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )


async def ensure_callback_user(callback: CallbackQuery) -> None:
    user = callback.from_user
    db.upsert_user(
        telegram_user_id=user.id,
        username=user.username,
        full_name=user.full_name,
    )


def admin_chat_ids() -> list[int]:
    if config.admin_review_chat_id:
        return [config.admin_review_chat_id]
    return sorted(config.admin_ids)


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await ensure_user(message)
    await state.clear()
    await send_menu(message)


@router.message(Command("whoami"))
async def whoami(message: Message) -> None:
    await message.answer(f"Ваш Telegram user ID: {message.from_user.id}")


@router.message(Command("admin"))
async def admin_panel(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Немає доступу.")
        return

    await message.answer(
        "Admin panel VCommunity\n\n"
        "/orders - останні заявки\n"
        "/pending - платежі на перевірці\n"
        "/confirmed - підтверджені платежі\n"
        "/rejected - відхилені платежі\n"
        "/vip - VIP користувачі\n"
        "/queue - черга\n"
        "/broadcast <текст> - розсилка"
    )


async def send_menu(message: Message) -> None:
    await message.answer(
        build_welcome_text(),
        reply_markup=services_keyboard(config.services),
    )


def build_welcome_text() -> str:
    return (
        "Вітаємо! Це VCommunity Bot.\n\n"
        "Оберіть послугу:\n\n"
        "1. Consultation - 50 EUR\n"
        "2. Legit Check - 3 EUR / item\n"
        "3. Chat Group - 13 EUR / month\n"
        "4. Готовий акаунт Vinted - 15 EUR передплата / 115 EUR після review\n"
        "5. Vinted Buyout - тільки для VIP"
    )


@router.callback_query(F.data == "menu")
async def menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await ensure_callback_user(callback)
    await state.clear()
    await callback.message.edit_text(
        build_welcome_text(),
        reply_markup=services_keyboard(config.services),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("service:"))
async def select_service(callback: CallbackQuery, state: FSMContext) -> None:
    await ensure_callback_user(callback)
    service_key = callback.data.split(":", maxsplit=1)[1] if callback.data else ""
    service = find_service(service_key)
    if service is None:
        await callback.answer("Послугу не знайдено", show_alert=True)
        return

    if service.vip_only and not db.is_user_vip(callback.from_user.id):
        await state.clear()
        await callback.message.edit_text(
            f"{service.title}\n\n"
            "Ця послуга доступна тільки VIP-користувачам.\n\n"
            "Спочатку оформіть послугу «Готовий акаунт Vinted» або зверніться до підтримки.",
            reply_markup=locked_vip_keyboard(),
        )
        await callback.answer()
        return

    if service.key == "vinted_buyout":
        await state.set_state(VintedFlow.waiting_for_link)
        await state.update_data(service_key=service.key)
        await callback.message.edit_text(
            f"{service.title}\n\n"
            f"Ціна: {service.price}\n\n"
            "Надішліть посилання на товар Vinted."
        )
        await callback.answer()
        return

    await state.clear()
    await callback.message.edit_text(
        f"{service.title}\n\n"
        f"Ціна: {service.price}\n\n"
        f"{service.description}\n\n"
        "Після натискання кнопки бот покаже реквізити та Order ID для призначення платежу.",
        reply_markup=service_keyboard(service),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay:"))
async def show_payment(callback: CallbackQuery, state: FSMContext) -> None:
    await ensure_callback_user(callback)
    service_key = callback.data.split(":", maxsplit=1)[1] if callback.data else ""
    service = find_service(service_key)
    if service is None:
        await callback.answer("Послугу не знайдено", show_alert=True)
        return

    order_id = db.create_order(
        user_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
        service_key=service.key,
        service_title=service.title,
        service_price=service.price,
    )
    await state.clear()
    await callback.message.edit_text(
        build_payment_text(order_id, service),
        reply_markup=payment_keyboard(order_id, service.key),
    )
    await callback.answer()


@router.message(VintedFlow.waiting_for_link)
async def vinted_link(message: Message, state: FSMContext) -> None:
    await ensure_user(message)
    if not message.text:
        await message.answer("Надішліть посилання текстом.")
        return
    await state.update_data(item_link=message.text.strip())
    await state.set_state(VintedFlow.waiting_for_price)
    await message.answer("Вкажіть ціну товару, наприклад: 80 EUR.")


@router.message(VintedFlow.waiting_for_price)
async def vinted_price(message: Message, state: FSMContext) -> None:
    await ensure_user(message)
    if not message.text:
        await message.answer("Вкажіть ціну текстом.")
        return
    await state.update_data(item_price=message.text.strip())
    await state.set_state(VintedFlow.waiting_for_comment)
    await message.answer(
        "Додайте коментар до викупу або натисніть «Пропустити».",
        reply_markup=optional_comment_keyboard(),
    )


@router.message(VintedFlow.waiting_for_comment)
async def vinted_comment(message: Message, state: FSMContext) -> None:
    await ensure_user(message)
    data = await state.get_data()
    service = find_service("vinted_buyout")
    if service is None or not message.from_user:
        await state.clear()
        return

    comment = "" if (message.text or "").casefold() == "пропустити" else (message.text or "").strip()
    amount_text = f"15% від {data['item_price']}"
    order_id = db.create_order(
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        service_key=service.key,
        service_title=service.title,
        service_price=service.price,
        amount_text=amount_text,
    )
    db.create_buyout_order(
        order_id=order_id,
        user_id=message.from_user.id,
        item_link=data["item_link"],
        item_price=data["item_price"],
        comment=comment,
    )
    await state.clear()
    await message.answer(
        build_payment_text(order_id, service, amount_text=amount_text),
        reply_markup=payment_keyboard(order_id, service.key),
    )


def build_payment_text(order_id: int, service: Service, amount_text: str | None = None) -> str:
    details = config.payment_details
    purpose = db.build_payment_purpose(order_id)
    return (
        "💳 Оплата послуг VCommunity\n\n"
        "Реквізити для оплати:\n"
        f"Отримувач: {details.recipient_name}\n"
        f"Сума: {amount_text or service.price}\n"
        f"Order ID / призначення платежу: {purpose}\n\n"
        f"{format_payment_methods(details)}\n\n"
        "Після оплати натисніть «Я оплатив» і завантажте скріншот, PDF/чек або фото квитанції."
    )


def format_payment_methods(details: PaymentDetails) -> str:
    return (
        "Card / IBAN:\n"
        f"- IBAN: {details.iban}\n"
        f"- Card: {details.card}\n"
        f"- Monobank: {details.monobank}\n"
        f"- Privat: {details.privat}\n"
        f"- Wise: {details.wise}\n"
        f"- Revolut: {details.revolut}\n"
        f"- SEPA / IBAN: {details.sepa_iban}\n\n"
        "Crypto:\n"
        f"- USDT TRC20: {details.usdt_trc20}\n"
        f"- USDC TRC20: {details.usdc_trc20}\n"
        f"- BTC: {details.btc}\n"
        f"- ETH: {details.eth}"
    )


@router.callback_query(F.data.startswith("payment_paid:"))
async def payment_paid(callback: CallbackQuery, state: FSMContext) -> None:
    order_id = int(callback.data.split(":", maxsplit=1)[1])
    order = db.get_order(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Заявку не знайдено", show_alert=True)
        return

    await state.set_state(PaymentFlow.waiting_for_proof)
    await state.update_data(order_id=order_id)
    await callback.message.answer(
        "Будь ласка, завантажте скріншот оплати, PDF/чек або фото квитанції."
    )
    await callback.answer()


@router.callback_query(F.data.startswith("retry_payment:"))
async def retry_payment(callback: CallbackQuery, state: FSMContext) -> None:
    order_id = int(callback.data.split(":", maxsplit=1)[1])
    order = db.get_order(order_id)
    if not order or order["user_id"] != callback.from_user.id:
        await callback.answer("Заявку не знайдено", show_alert=True)
        return

    db.update_order_status(order_id, STATUS_AWAITING_PROOF)
    await state.set_state(PaymentFlow.waiting_for_proof)
    await state.update_data(order_id=order_id)
    await callback.message.answer("Завантажте новий скріншот/PDF/фото квитанції.")
    await callback.answer()


@router.callback_query(F.data.startswith("payment_cancel:"))
async def payment_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    order_id = int(callback.data.split(":", maxsplit=1)[1])
    order = db.get_order(order_id)
    if order and order["user_id"] == callback.from_user.id:
        db.update_order_status(order_id, "cancelled")
    await state.clear()
    await callback.message.edit_text("Оплату скасовано.", reply_markup=services_keyboard(config.services))
    await callback.answer()


@router.message(PaymentFlow.waiting_for_proof)
async def receive_payment_proof(message: Message, state: FSMContext) -> None:
    await ensure_user(message)
    data = await state.get_data()
    order_id = int(data["order_id"])
    order = db.get_order(order_id)
    if not order or not message.from_user or order["user_id"] != message.from_user.id:
        await state.clear()
        await message.answer("Заявку не знайдено. Почніть заново через /start.")
        return

    upload = extract_upload(message)
    if upload is None:
        await message.answer("Потрібен скріншот, PDF/чек або фото квитанції.")
        return

    db.create_payment_proof(order_id=order_id, user_id=message.from_user.id, **upload)
    db.update_order_status(order_id, STATUS_PENDING_REVIEW)
    await state.set_state(PaymentFlow.waiting_for_name)
    await message.answer("Вкажіть ім'я платника.")


@router.message(PaymentFlow.waiting_for_name)
async def receive_payment_name(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Вкажіть ім'я текстом.")
        return
    data = await state.get_data()
    db.update_order_contact(int(data["order_id"]), customer_name=message.text.strip())
    await state.set_state(PaymentFlow.waiting_for_username)
    default_username = f"@{message.from_user.username}" if message.from_user and message.from_user.username else ""
    await message.answer(
        "Вкажіть Telegram username."
        + (f"\nМожна надіслати поточний: {default_username}" if default_username else "")
    )


@router.message(PaymentFlow.waiting_for_username)
async def receive_payment_username(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Вкажіть Telegram username текстом.")
        return
    data = await state.get_data()
    username = message.text.strip()
    db.update_order_contact(int(data["order_id"]), customer_username=username)
    await state.set_state(PaymentFlow.waiting_for_phone)
    await message.answer("Надішліть телефон кнопкою нижче або введіть номер текстом.", reply_markup=phone_keyboard())


@router.message(PaymentFlow.waiting_for_phone, F.contact)
async def receive_payment_phone_contact(message: Message, state: FSMContext) -> None:
    await save_payment_phone_and_ask_comment(message, state, message.contact.phone_number)


@router.message(PaymentFlow.waiting_for_phone)
async def receive_payment_phone_text(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Надішліть телефон кнопкою або введіть номер текстом.")
        return
    await save_payment_phone_and_ask_comment(message, state, message.text.strip())


async def save_payment_phone_and_ask_comment(message: Message, state: FSMContext, phone_number: str) -> None:
    data = await state.get_data()
    db.update_order_contact(int(data["order_id"]), phone_number=phone_number)
    await state.set_state(PaymentFlow.waiting_for_comment)
    await message.answer(
        "Додайте коментар до оплати або натисніть «Пропустити».",
        reply_markup=optional_comment_keyboard(),
    )


@router.message(PaymentFlow.waiting_for_comment)
async def receive_payment_comment(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    order_id = int(data["order_id"])
    comment = "" if (message.text or "").casefold() == "пропустити" else (message.text or "").strip()
    db.update_order_contact(order_id, customer_comment=comment)
    await state.clear()

    await send_admin_payment_request(bot, order_id)
    await message.answer(
        "Заявку відправлено на перевірку адміну.\n"
        "Статус: Pending Payment Review.",
        reply_markup=ReplyKeyboardRemove(),
    )


def extract_upload(message: Message) -> dict[str, Any] | None:
    if message.photo:
        photo = message.photo[-1]
        return {
            "file_id": photo.file_id,
            "file_unique_id": photo.file_unique_id,
            "file_type": "photo",
            "mime_type": None,
            "file_name": None,
        }

    if message.document:
        document = message.document
        mime_type = document.mime_type or ""
        if mime_type == "application/pdf" or mime_type.startswith("image/"):
            return {
                "file_id": document.file_id,
                "file_unique_id": document.file_unique_id,
                "file_type": "document",
                "mime_type": mime_type,
                "file_name": document.file_name,
            }
    return None


async def send_admin_payment_request(bot: Bot, order_id: int) -> None:
    order = db.get_order(order_id)
    proof = db.get_latest_payment_proof(order_id)
    if not order or not proof:
        return

    caption = build_admin_payment_card(order, proof)
    for chat_id in admin_chat_ids():
        try:
            if proof["file_type"] == "photo":
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=proof["file_id"],
                    caption=caption,
                    reply_markup=admin_review_keyboard(order_id),
                )
            else:
                await bot.send_document(
                    chat_id=chat_id,
                    document=proof["file_id"],
                    caption=caption,
                    reply_markup=admin_review_keyboard(order_id),
                )
        except Exception:
            logging.exception("Failed to send payment request %s to admin chat %s", order_id, chat_id)


def build_admin_payment_card(order: dict[str, Any], proof: dict[str, Any]) -> str:
    username = order.get("customer_username") or order.get("username") or "без username"
    if username and not str(username).startswith("@"):
        username = f"@{username}"
    return (
        "NEW PAYMENT REQUEST\n\n"
        f"Service: {order['service_title']}\n"
        f"User ID: {order['user_id']}\n"
        f"Username: {username}\n"
        f"Name: {order.get('customer_name') or order.get('full_name') or '-'}\n"
        f"Телефон: {order.get('phone_number') or '-'}\n"
        f"Сума: {order.get('amount_text') or order.get('service_price')}\n"
        f"Дата: {order.get('created_at')}\n"
        f"Order ID: {order['payment_purpose'] or order['id']}\n"
        f"Screenshot Attached: {'yes' if proof else 'no'}\n"
        f"Status: {status_label(order['status'])}\n"
        f"Коментар: {order.get('customer_comment') or '-'}"
    )


@router.callback_query(F.data.startswith("admin:"))
async def admin_action(callback: CallbackQuery, bot: Bot) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Немає доступу", show_alert=True)
        return

    _, action, raw_order_id = callback.data.split(":", maxsplit=2)
    order_id = int(raw_order_id)
    order = db.get_order(order_id)
    if not order:
        await callback.answer("Заявку не знайдено", show_alert=True)
        return

    if action == "confirm":
        db.update_order_status(order_id, STATUS_CONFIRMED)
        db.add_admin_review(order_id=order_id, admin_id=callback.from_user.id, action="confirm")
        await mark_admin_message(callback, "Payment Confirmed")
        await continue_after_payment_confirmed(bot, order_id)
        await callback.answer("Платіж підтверджено")
        return

    if action == "reject":
        db.update_order_status(order_id, STATUS_REJECTED)
        db.add_admin_review(order_id=order_id, admin_id=callback.from_user.id, action="reject")
        await mark_admin_message(callback, "Rejected")
        await bot.send_message(
            chat_id=order["user_id"],
            text=(
                "Ваш платіж не підтверджено.\n\n"
                "Перевірте:\n"
                "- суму\n"
                "- реквізити\n"
                "- правильність скріншота"
            ),
            reply_markup=retry_payment_keyboard(order_id, config.support_link),
        )
        await callback.answer("Платіж відхилено")
        return

    if action == "ask_again":
        db.update_order_status(order_id, STATUS_AWAITING_PROOF)
        db.add_admin_review(order_id=order_id, admin_id=callback.from_user.id, action="ask_again")
        await mark_admin_message(callback, "Asked user again")
        await bot.send_message(
            chat_id=order["user_id"],
            text="Адмін просить завантажити підтвердження оплати ще раз.",
            reply_markup=retry_payment_keyboard(order_id, config.support_link),
        )
        await callback.answer("Користувачу надіслано повторний запит")
        return

    if action == "queue":
        db.update_order_status(order_id, STATUS_IN_QUEUE)
        db.add_admin_review(order_id=order_id, admin_id=callback.from_user.id, action="queue")
        await mark_admin_message(callback, "Moved to Queue")
        await bot.send_message(chat_id=order["user_id"], text="Вашу заявку перенесено в чергу.")
        await callback.answer("Заявку перенесено в чергу")
        return

    if action == "processing":
        db.update_order_status(order_id, STATUS_PROCESSING)
        db.add_admin_review(order_id=order_id, admin_id=callback.from_user.id, action="processing")
        await mark_admin_message(callback, "Processing")
        await bot.send_message(chat_id=order["user_id"], text="Статус заявки: Processing.")
        await callback.answer("Статус оновлено")
        return

    if action == "done":
        db.update_order_status(order_id, STATUS_DONE)
        db.add_admin_review(order_id=order_id, admin_id=callback.from_user.id, action="done")
        await mark_admin_message(callback, "Done")
        await bot.send_message(chat_id=order["user_id"], text="Статус заявки: Done.")
        await callback.answer("Заявку завершено")
        return

    await callback.answer("Невідома дія", show_alert=True)


async def mark_admin_message(callback: CallbackQuery, note: str) -> None:
    message = callback.message
    if not message:
        return
    try:
        current = message.caption or message.text or ""
        updated = f"{current}\n\nAdmin action: {note}"
        if message.caption is not None:
            await message.edit_caption(caption=updated[:1024], reply_markup=None)
        elif message.text is not None:
            await message.edit_text(updated, reply_markup=None)
        else:
            await message.edit_reply_markup(reply_markup=None)
    except Exception:
        logging.exception("Failed to edit admin message")


async def continue_after_payment_confirmed(bot: Bot, order_id: int) -> None:
    order = db.get_order(order_id)
    if not order:
        return

    user_id = int(order["user_id"])
    user_state = dispatcher.fsm.get_context(bot=bot, chat_id=user_id, user_id=user_id)
    await user_state.clear()

    service_key = order["service_key"]
    if service_key == "consultation":
        await user_state.set_state(ConsultationFlow.waiting_for_questionnaire)
        await user_state.update_data(order_id=order_id)
        await bot.send_message(
            chat_id=user_id,
            text=(
                "Платіж підтверджено.\n\n"
                "Заповніть анкету для консультації: коротко опишіть нішу, проблему, "
                "ціль та що вже пробували."
            ),
        )
        return

    if service_key == "legit_check":
        await user_state.set_state(LegitCheckFlow.waiting_for_item_files)
        await user_state.update_data(order_id=order_id)
        await bot.send_message(
            chat_id=user_id,
            text="Платіж підтверджено. Завантажте фото товару для Legit Check.",
            reply_markup=legit_done_keyboard(),
        )
        return

    if service_key == "chat_group":
        await grant_chat_access(bot, order)
        return

    if service_key == "vip_service":
        await user_state.set_state(VIPFlow.waiting_for_questionnaire)
        await user_state.update_data(order_id=order_id)
        await bot.send_message(
            chat_id=user_id,
            text=(
                "Платіж підтверджено.\n\n"
                "Заповніть VIP-анкету: досвід, маркетплейси, країна, бюджет, "
                "що саме потрібно від сервісу."
            ),
        )
        return

    if service_key == "vinted_buyout":
        db.update_order_status(order_id, STATUS_PROCESSING)
        db.update_buyout_status(order_id, STATUS_PROCESSING)
        await bot.send_message(
            chat_id=user_id,
            text="Платіж підтверджено. Ваш Vinted Buyout перейшов у Processing.",
        )
        await notify_admins_text(bot, f"Vinted Buyout #{order_id} confirmed and moved to Processing.")


async def grant_chat_access(bot: Bot, order: dict[str, Any]) -> None:
    user_id = int(order["user_id"])
    order_id = int(order["id"])
    if not config.private_chat_id:
        db.update_order_status(order_id, STATUS_IN_QUEUE)
        await bot.send_message(
            chat_id=user_id,
            text=(
                "Платіж підтверджено. Закритий чат ще не налаштований у конфігу, "
                "адмін додасть вас вручну."
            ),
            reply_markup=manager_keyboard(config.manager_link),
        )
        await notify_admins_text(
            bot,
            f"Chat Group order #{order_id}: PRIVATE_CHAT_ID не налаштований. Додайте користувача вручну.",
        )
        return

    try:
        invite = await bot.create_chat_invite_link(
            chat_id=config.private_chat_id,
            name=f"VCommunity order {order_id}",
            expire_date=datetime.now(timezone.utc) + timedelta(days=1),
            member_limit=1,
        )
        db.create_subscription(
            user_id=user_id,
            order_id=order_id,
            chat_id=config.private_chat_id,
            invite_link=invite.invite_link,
            days=30,
        )
        db.update_order_status(order_id, STATUS_DONE)
        await bot.send_message(
            chat_id=user_id,
            text=(
                "Платіж підтверджено.\n\n"
                "Ваш invite link до закритого чату на 30 днів:\n"
                f"{invite.invite_link}"
            ),
        )
    except Exception:
        logging.exception("Failed to create private chat invite")
        db.update_order_status(order_id, STATUS_IN_QUEUE)
        await bot.send_message(
            chat_id=user_id,
            text="Платіж підтверджено. Не вдалося автоматично створити invite link, адмін додасть вас вручну.",
        )
        await notify_admins_text(bot, f"Не вдалося створити invite link для order #{order_id}.")


@router.message(ConsultationFlow.waiting_for_questionnaire)
async def consultation_questionnaire(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.text:
        await message.answer("Надішліть анкету текстом.")
        return
    data = await state.get_data()
    order_id = int(data["order_id"])
    db.create_consultation(order_id=order_id, user_id=message.from_user.id, questionnaire=message.text.strip())
    db.update_order_status(order_id, STATUS_IN_QUEUE)
    await state.clear()
    await message.answer("Анкету прийнято. Заявка передана в CRM.")
    await notify_admins_text(
        bot,
        f"CONSULTATION CRM\nOrder #{order_id}\nUser ID: {message.from_user.id}\n\n{message.text.strip()}",
    )


@router.message(VIPFlow.waiting_for_questionnaire)
async def vip_questionnaire(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.text:
        await message.answer("Надішліть VIP-анкету текстом.")
        return
    data = await state.get_data()
    order_id = int(data["order_id"])
    db.create_vip_queue(order_id=order_id, user_id=message.from_user.id, questionnaire=message.text.strip())
    db.mark_user_vip(message.from_user.id)
    db.update_order_status(order_id, STATUS_IN_QUEUE)
    await state.clear()
    await message.answer("VIP-анкету прийнято. Ви додані в VIP Queue.")
    await notify_admins_text(
        bot,
        f"VIP QUEUE\nOrder #{order_id}\nUser ID: {message.from_user.id}\n\n{message.text.strip()}",
    )


@router.message(LegitCheckFlow.waiting_for_item_files, F.text.casefold() == "готово")
async def legit_done(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    order_id = int(data["order_id"])
    files = db.get_legit_check_files(order_id)
    if not files:
        await message.answer("Спочатку завантажте хоча б одне фото товару.")
        return

    db.update_order_status(order_id, STATUS_IN_QUEUE)
    await state.clear()
    await message.answer("Фото прийнято. Заявка передана модератору.")
    await notify_legit_check_queue(bot, order_id, files)


@router.message(LegitCheckFlow.waiting_for_item_files)
async def legit_file(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    order_id = int(data["order_id"])
    upload = extract_upload(message)
    if upload is None:
        await message.answer("Завантажте фото товару або натисніть «Готово».")
        return

    db.add_legit_check_file(
        order_id=order_id,
        user_id=message.from_user.id,
        file_id=upload["file_id"],
        file_unique_id=upload["file_unique_id"],
        file_type=upload["file_type"],
        caption=message.caption,
    )
    await message.answer("Файл додано. Надішліть ще фото або натисніть «Готово».", reply_markup=legit_done_keyboard())


async def notify_legit_check_queue(bot: Bot, order_id: int, files: list[dict[str, Any]]) -> None:
    order = db.get_order(order_id)
    if not order:
        return
    text = (
        "LEGIT CHECK MODERATOR QUEUE\n\n"
        f"Order ID: {order['payment_purpose'] or order_id}\n"
        f"User ID: {order['user_id']}\n"
        f"Username: {order.get('customer_username') or order.get('username') or '-'}\n"
        f"Files: {len(files)}\n"
        f"Status: {status_label(order['status'])}"
    )
    for chat_id in admin_chat_ids():
        try:
            await bot.send_message(chat_id=chat_id, text=text, reply_markup=admin_review_keyboard(order_id))
            for item in files:
                if item["file_type"] == "photo":
                    await bot.send_photo(chat_id=chat_id, photo=item["file_id"], caption=item.get("caption"))
                else:
                    await bot.send_document(chat_id=chat_id, document=item["file_id"], caption=item.get("caption"))
        except Exception:
            logging.exception("Failed to notify legit queue for order %s", order_id)


async def notify_admins_text(bot: Bot, text: str) -> None:
    for chat_id in admin_chat_ids():
        try:
            await bot.send_message(chat_id=chat_id, text=text)
        except Exception:
            logging.exception("Failed to notify admin chat %s", chat_id)


@router.message(Command("orders"))
async def orders_command(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Немає доступу.")
        return
    await message.answer(format_orders_list("Останні заявки", db.list_orders(limit=10)))


@router.message(Command("pending"))
async def pending_command(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Немає доступу.")
        return
    await message.answer(format_orders_list("Платежі на перевірці", db.list_orders(status=STATUS_PENDING_REVIEW, limit=20)))


@router.message(Command("confirmed"))
async def confirmed_command(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Немає доступу.")
        return
    await message.answer(format_orders_list("Підтверджені платежі", db.list_orders(status=STATUS_CONFIRMED, limit=20)))


@router.message(Command("rejected"))
async def rejected_command(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Немає доступу.")
        return
    await message.answer(format_orders_list("Відхилені платежі", db.list_orders(status=STATUS_REJECTED, limit=20)))


@router.message(Command("queue"))
async def queue_command(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Немає доступу.")
        return
    await message.answer(format_orders_list("Черга", db.list_queue_orders(limit=20)))


@router.message(Command("vip"))
async def vip_command(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Немає доступу.")
        return
    users = db.list_vip_users(limit=30)
    if not users:
        await message.answer("VIP користувачів поки немає.")
        return
    lines = ["VIP користувачі:"]
    for user in users:
        username = f"@{user['username']}" if user.get("username") else "без username"
        lines.append(f"{user['telegram_user_id']} | {username} | {user.get('full_name') or '-'}")
    await message.answer("\n".join(lines))


@router.message(Command("broadcast"))
async def broadcast_command(message: Message, command: CommandObject, state: FSMContext, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Немає доступу.")
        return

    text = (command.args or "").strip()
    if text:
        sent, failed = await broadcast_text(bot, text)
        await message.answer(f"Розсилка завершена. Надіслано: {sent}, помилок: {failed}.")
        return

    await state.set_state(BroadcastFlow.waiting_for_message)
    await message.answer("Надішліть текст для розсилки.")


@router.message(BroadcastFlow.waiting_for_message)
async def broadcast_message(message: Message, state: FSMContext, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    if not message.text:
        await message.answer("Потрібен текст для розсилки.")
        return
    await state.clear()
    sent, failed = await broadcast_text(bot, message.text)
    await message.answer(f"Розсилка завершена. Надіслано: {sent}, помилок: {failed}.")


async def broadcast_text(bot: Bot, text: str) -> tuple[int, int]:
    sent = 0
    failed = 0
    for user_id in db.list_user_ids():
        try:
            await bot.send_message(chat_id=user_id, text=text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
            logging.exception("Broadcast failed for user %s", user_id)
    return sent, failed


def format_orders_list(title: str, orders: list[dict[str, Any]]) -> str:
    if not orders:
        return f"{title}: порожньо."
    lines = [f"{title}:"]
    for order in orders:
        username = order.get("customer_username") or order.get("username") or "-"
        if username != "-" and not str(username).startswith("@"):
            username = f"@{username}"
        lines.append(
            f"#{order['id']} | {status_label(order['status'])} | {order['service_title']} | "
            f"{order.get('amount_text') or order.get('service_price')} | {username} | user {order['user_id']}"
        )
    return "\n".join(lines)


async def subscription_watcher(bot: Bot) -> None:
    await asyncio.sleep(10)
    while True:
        try:
            subscriptions = db.get_subscriptions_for_reminder(within_days=3)
            for subscription in subscriptions:
                await bot.send_message(
                    chat_id=subscription["user_id"],
                    text=(
                        "Нагадування: підписка на Chat Group скоро завершується.\n"
                        "Для продовження оберіть Chat Group і оплатіть наступні 30 днів."
                    ),
                    reply_markup=services_keyboard(config.services),
                )
                db.mark_subscription_reminded(subscription["id"])
                await asyncio.sleep(0.1)
        except Exception:
            logging.exception("Subscription watcher failed")
        await asyncio.sleep(60 * 60)


async def main() -> None:
    global config, db, dispatcher

    logging.basicConfig(level=logging.INFO)
    config = load_config()
    db = Database(config.database_path)
    db.init()

    bot = Bot(token=config.bot_token)
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(router)

    asyncio.create_task(subscription_watcher(bot))
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
