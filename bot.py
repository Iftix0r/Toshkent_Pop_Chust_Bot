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
)

import storage
from config import ADMIN_IDS, ADMIN_PHONE, ADMIN_USERNAME, BOT_TOKEN, DRIVERS_GROUP_ID

router = Router()
order_id_counter = itertools.count(1)
# order_id -> {"customer_id": int, "customer_name": str, "text": str}
orders: dict[int, dict] = {}
# user_id -> {"phone": str, "location": (lat, lon)}
pending_info: dict[int, dict] = {}

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
    pending_info.setdefault(message.from_user.id, {})["phone"] = message.contact.phone_number
    await message.answer("📞 Telefon raqamingiz qabul qilindi.", reply_markup=order_keyboard)


@router.message(F.location)
async def handle_location(message: Message) -> None:
    pending_info.setdefault(message.from_user.id, {})["location"] = (
        message.location.latitude,
        message.location.longitude,
    )
    await message.answer("📍 Joylashuvingiz qabul qilindi.", reply_markup=order_keyboard)


@router.message(F.text)
async def handle_order(message: Message) -> None:
    user = message.from_user
    info = pending_info.pop(user.id, {})

    order_id = next(order_id_counter)
    orders[order_id] = {
        "customer_id": user.id,
        "customer_name": user.full_name,
        "text": message.text,
    }

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

    customer_url = (
        f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"👤 {user.full_name}",
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

    order_text = (
        "🚖 <b>Yangi buyurtma!</b>\n\n"
        f"👤 Mijoz: {user.full_name} ({user_contact(user.id, user.username)})\n"
        f"📄 Ma'lumot: {message.text}"
    )
    if "phone" in info:
        order_text += f"\n📞 Telefon: {info['phone']}"

    await message.bot.send_message(DRIVERS_GROUP_ID, order_text, reply_markup=keyboard)

    if "location" in info:
        latitude, longitude = info["location"]
        await message.bot.send_location(DRIVERS_GROUP_ID, latitude=latitude, longitude=longitude)


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
    await callback.answer("Buyurtma sizga biriktirildi!")


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
