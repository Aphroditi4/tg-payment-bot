from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from app.config import Service


def services_keyboard(services: list[Service]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=service.title, callback_data=f"service:{service.key}")]
            for service in services
        ]
    )


def service_keyboard(service: Service) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Оплатити {service.price}", callback_data=f"pay:{service.key}")],
            [InlineKeyboardButton(text="Назад", callback_data="menu")],
        ]
    )


def locked_vip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подати заявку на VIP", callback_data="service:vip_service")],
            [InlineKeyboardButton(text="Назад", callback_data="menu")],
        ]
    )


def payment_keyboard(order_id: int, service_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Я оплатив", callback_data=f"payment_paid:{order_id}")],
            [InlineKeyboardButton(text="Скасувати", callback_data=f"payment_cancel:{order_id}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"service:{service_key}")],
        ]
    )


def admin_review_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Confirm Payment", callback_data=f"admin:confirm:{order_id}"),
                InlineKeyboardButton(text="Reject Payment", callback_data=f"admin:reject:{order_id}"),
            ],
            [
                InlineKeyboardButton(text="Ask User Again", callback_data=f"admin:ask_again:{order_id}"),
                InlineKeyboardButton(text="Move to Queue", callback_data=f"admin:queue:{order_id}"),
            ],
            [
                InlineKeyboardButton(text="Processing", callback_data=f"admin:processing:{order_id}"),
                InlineKeyboardButton(text="Done", callback_data=f"admin:done:{order_id}"),
            ],
        ]
    )


def retry_payment_keyboard(order_id: int, support_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Завантажити повторно", callback_data=f"retry_payment:{order_id}")],
            [InlineKeyboardButton(text="Підтримка", url=support_link)],
        ]
    )


def manager_keyboard(manager_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Написати менеджеру", url=manager_link)],
            [InlineKeyboardButton(text="Повернутися до послуг", callback_data="menu")],
        ]
    )


def phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Надіслати номер телефону", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def optional_comment_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Пропустити")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def legit_done_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Готово")]],
        resize_keyboard=True,
        one_time_keyboard=False,
    )
