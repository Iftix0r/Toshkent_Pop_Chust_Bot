import asyncio
import itertools
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ButtonStyle, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    User,
)

import storage
from config import ADMIN_IDS, ADMIN_PHONE, ADMIN_USERNAME, BOT_TOKEN, DRIVERS_GROUP_ID

router = Router()
order_id_counter = itertools.count(1)
# order_id -> {"customer_id", "customer_name", "username", "phone", "location", "text", "message_id"}
orders: dict[int, dict] = {}
# customer_id -> order_id of their currently open (not yet accepted) order
active_order_id: dict[int, int] = {}

order_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(
                text="📞 Telefon yuborish",
                request_contact=True,
                style=ButtonStyle.SUCCESS,
            )
        ],
        [
            KeyboardButton(
                text="📍 Joylashuv yuborish",
                request_location=True,
                style=ButtonStyle.PRIMARY,
            )
        ],
    ],
    resize_keyboard=True,
)


def user_contact(user_id: int, username: str | None) -> str:
    if username:
        return f"@{username}"
    return f'<a href="tg://user?id={user_id}">profil</a>'


def get_or_create_order(user: User) -> dict:
    order_id = active_order_id.get(user.id)
    if order_id is not None:
        return orders[order_id]

    order_id = next(order_id_counter)
    order = {
        "customer_id": user.id,
        "customer_name": user.full_name,
        "username": user.username,
        "message_id": None,
    }
    orders[order_id] = order
    active_order_id[user.id] = order_id
    return order


def build_order_text(order: dict) -> str:
    lines = [
        "🚖 <b>Yangi buyurtma!</b>",
        "",
        f"👤 Mijoz: {order['customer_name']} "
        f"({user_contact(order['customer_id'], order['username'])})",
    ]
    if order.get("phone"):
        lines.append(f"📞 Telefon: {order['phone']}")
    if order.get("location"):
        latitude, longitude = order["location"]
        lines.append(
            "📍 Joylashuv: "
            f'<a href="https://maps.google.com/?q={latitude},{longitude}">xaritada ko\'rish</a>'
        )
    if order.get("text"):
        lines.append(f"📄 Ma'lumot: {order['text']}")
    return "\n".join(lines)


def build_order_keyboard(order_id: int, order: dict) -> InlineKeyboardMarkup:
    username = order["username"]
    customer_url = (
        f"https://t.me/{username}" if username else f"tg://user?id={order['customer_id']}"
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"👤 {order['customer_name']}",
                    url=customer_url,
                    style=ButtonStyle.PRIMARY,
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Qabul qilish",
                    callback_data=f"accept:{order_id}",
                    style=ButtonStyle.SUCCESS,
                )
            ],
        ]
    )


async def sync_order_message(bot: Bot, order_id: int) -> None:
    order = orders[order_id]
    text = build_order_text(order)
    keyboard = build_order_keyboard(order_id, order)

    if order["message_id"] is not None:
        await bot.edit_message_text(
            chat_id=DRIVERS_GROUP_ID,
            message_id=order["message_id"],
            text=text,
            reply_markup=keyboard,
        )
        return

    sent = await bot.send_message(DRIVERS_GROUP_ID, text, reply_markup=keyboard)
    order["message_id"] = sent.message_id


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user = message.from_user
    is_new = storage.register_user(user.id, user.full_name, user.username)

    if is_new:
        await message.bot.send_message(
            DRIVERS_GROUP_ID,
            "🆕 <b>Yangi foydalanuvchi!</b>\n\n"
            f"👤 Ism: {user.full_name}\n"
            f"📞 Aloqa: {user_contact(user.id, user.username)}\n"
            f"🆔 ID: <code>{user.id}</code>",
        )

    await message.answer(
        "👋 <b>Assalomu alaykum!</b>\n\n"
        "📝 <b>Zakazingizni yozing</b> (qayerga borasiz, "
        "telefon raqam va boshqa ma'lumotlar):",
        reply_markup=order_keyboard,
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer(f"📊 Foydalanuvchilar soni: <b>{storage.users_count()}</b>")


@router.message(F.contact)
async def handle_contact(message: Message) -> None:
    order = get_or_create_order(message.from_user)
    order["phone"] = message.contact.phone_number
    order_id = active_order_id[message.from_user.id]

    await sync_order_message(message.bot, order_id)
    await message.answer(
        "📞 Telefon raqamingiz qabul qilindi va haydovchilarga yuborildi.",
        reply_markup=order_keyboard,
    )


@router.message(F.location)
async def handle_location(message: Message) -> None:
    order = get_or_create_order(message.from_user)
    order["location"] = (message.location.latitude, message.location.longitude)
    order_id = active_order_id[message.from_user.id]

    await sync_order_message(message.bot, order_id)
    await message.answer(
        "📍 Joylashuvingiz qabul qilindi va haydovchilarga yuborildi.",
        reply_markup=order_keyboard,
    )


@router.message(F.text)
async def handle_order(message: Message) -> None:
    order = get_or_create_order(message.from_user)
    order["text"] = message.text
    order_id = active_order_id[message.from_user.id]

    await sync_order_message(message.bot, order_id)

    confirmation = (
        "✅ <b>Zakazingiz qabul qilindi!</b>\n\n"
        "🚀 Tez orada haydovchilar siz bilan bog'lanadi."
    )
    contact_lines = []
    if ADMIN_USERNAME:
        contact_lines.append(f"✈️ @{ADMIN_USERNAME}")
    if ADMIN_PHONE:
        contact_lines.append(f"📞 Tel: {ADMIN_PHONE}")
    if contact_lines:
        confirmation += "\n\n" + "\n".join(contact_lines)

    await message.answer(confirmation, reply_markup=order_keyboard)


@router.callback_query(F.data.startswith("accept:"))
async def handle_accept(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split(":", 1)[1])
    order = orders.get(order_id)

    if order is None:
        await callback.answer("Bu buyurtma allaqachon bekor qilingan.", show_alert=True)
        return

    driver = callback.from_user
    driver_contact = user_contact(driver.id, driver.username)

    await callback.bot.send_message(
        order["customer_id"],
        "🚗 <b>Haydovchi topildi!</b>\n\n"
        f"👤 Haydovchi: {driver.full_name} ({driver_contact})\n"
        "Tez orada siz bilan bog'lanadi.",
    )

    customer_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[callback.message.reply_markup.inline_keyboard[0]]
    )
    await callback.message.edit_text(
        callback.message.html_text
        + f"\n\n✅ Qabul qildi: {driver.full_name} ({driver_contact})",
        reply_markup=customer_keyboard,
    )
    del orders[order_id]
    active_order_id.pop(order["customer_id"], None)
    await callback.answer("Buyurtma sizga biriktirildi!")


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
