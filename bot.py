import asyncio
import itertools
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ButtonStyle, ChatType, ParseMode
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
from config import ADMIN_IDS, BOT_TOKEN, DRIVERS_GROUP_ID

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE)
order_id_counter = itertools.count(1)
# order_id -> {"customer_id", "customer_name", "username", "phone", "location", "text", "message_id"}
orders: dict[int, dict] = {}
# customer_id -> order_id of their currently open (not yet accepted) order
active_order_id: dict[int, int] = {}
# admin ids currently expected to send the next message as a broadcast
awaiting_broadcast: set[int] = set()

TASHKENT_TZ = ZoneInfo("Asia/Tashkent")

admin_panel_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📊 Statistika", callback_data="admin:stats", style=ButtonStyle.PRIMARY
            )
        ],
        [
            InlineKeyboardButton(
                text="📢 Reklama yuborish",
                callback_data="admin:broadcast",
                style=ButtonStyle.SUCCESS,
            )
        ],
    ]
)

admin_contact_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="👮 Admin",
                url="https://t.me/HusniddinMirzo_2012",
                style=ButtonStyle.PRIMARY,
            )
        ]
    ]
)

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
        "order_number": storage.increment_order_count(user.id),
        "created_at": datetime.now(TASHKENT_TZ),
    }
    orders[order_id] = order
    active_order_id[user.id] = order_id
    return order


ORDER_SEPARATOR = "--------------------------------"


def build_order_text(order: dict) -> str:
    fields = [
        f"👤 Mijoz: {order['customer_name']} "
        f"({user_contact(order['customer_id'], order['username'])})",
        f"🆔 Mijoz ID: <code>{order['customer_id']}</code>",
        f"🔢 Buyurtma: {order['order_number']}-chi",
        f"🕒 Vaqt: {order['created_at'].strftime('%d.%m.%Y %H:%M')}",
    ]
    if order.get("phone"):
        fields.append(f"📞 Telefon: {order['phone']}")
    if order.get("location"):
        latitude, longitude = order["location"]
        fields.append(
            "📍 Joylashuv: "
            f'<a href="https://maps.google.com/?q={latitude},{longitude}">xaritada ko\'rish</a>'
        )
    if order.get("text"):
        fields.append(f"📄 Ma'lumot: {order['text']}")

    body = f"\n{ORDER_SEPARATOR}\n".join(fields)
    return f"🚖 <b>Yangi buyurtma!</b>\n\n{body}"


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

    if user.id in ADMIN_IDS:
        await message.answer(
            "🎛 <b>Admin panel</b>\n\nQuyidagi tugmalardan birini tanlang:",
            reply_markup=admin_panel_keyboard,
        )
        return

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


@router.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    await callback.message.answer(f"📊 Foydalanuvchilar soni: <b>{storage.users_count()}</b>")
    await callback.answer()


@router.callback_query(F.data == "admin:broadcast")
async def admin_broadcast_prompt(callback: CallbackQuery) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer()
        return
    awaiting_broadcast.add(callback.from_user.id)
    await callback.message.answer(
        "📢 Reklama sifatida yubormoqchi bo'lgan xabaringizni yuboring "
        "(matn, rasm, video va h.k.):"
    )
    await callback.answer()


def is_awaiting_broadcast(message: Message) -> bool:
    return message.from_user.id in awaiting_broadcast


@router.message(is_awaiting_broadcast)
async def handle_broadcast_content(message: Message) -> None:
    awaiting_broadcast.discard(message.from_user.id)

    sent = 0
    failed = 0
    for user_id in storage.all_user_ids():
        try:
            await message.copy_to(user_id)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    await message.answer(
        f"📢 Reklama yuborildi.\n✅ Yetkazildi: {sent}\n❌ Yetkazilmadi: {failed}"
    )


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

    await message.answer(
        "✅ <b>Zakazingiz qabul qilindi!</b>\n\n"
        "🚀 Tez orada haydovchilar siz bilan bog'lanadi.",
        reply_markup=order_keyboard,
    )
    await message.answer("🛠 Haydovchi bilan muammo bo'lsa:", reply_markup=admin_contact_keyboard)


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
