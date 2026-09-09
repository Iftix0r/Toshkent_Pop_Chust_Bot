import asyncio
import itertools
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import BOT_TOKEN, DRIVERS_GROUP_ID

router = Router()
order_id_counter = itertools.count(1)
# order_id -> {"customer_id": int, "customer_name": str, "text": str}
orders: dict[int, dict] = {}


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        f"👋 <b>Assalomu alaykum!</b> <i>{message.from_user.full_name}</i>\n\n"
        "📝 <b>Zakazingizni yozing</b> (qayerga borasiz, "
        "telefon raqam va boshqa ma'lumotlar):"
    )


@router.message(F.text)
async def handle_order(message: Message) -> None:
    order_id = next(order_id_counter)
    orders[order_id] = {
        "customer_id": message.from_user.id,
        "customer_name": message.from_user.full_name,
        "text": message.text,
    }

    await message.answer(
        "✅ <b>Zakazingiz qabul qilindi!</b>\n\n"
        "🚀 Tez orada haydovchilar siz bilan bog'lanadi."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Qabul qilish", callback_data=f"accept:{order_id}"
                )
            ]
        ]
    )
    username = message.from_user.username
    contact = f"@{username}" if username else f'<a href="tg://user?id={message.from_user.id}">profil</a>'

    await message.bot.send_message(
        DRIVERS_GROUP_ID,
        "🚖 <b>Yangi buyurtma!</b>\n\n"
        f"👤 Mijoz: {message.from_user.full_name} ({contact})\n"
        f"📄 Ma'lumot: {message.text}",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("accept:"))
async def handle_accept(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split(":", 1)[1])
    order = orders.get(order_id)

    if order is None:
        await callback.answer("Bu buyurtma allaqachon bekor qilingan.", show_alert=True)
        return

    driver = callback.from_user
    driver_username = driver.username
    driver_contact = (
        f"@{driver_username}"
        if driver_username
        else f'<a href="tg://user?id={driver.id}">profil</a>'
    )

    await callback.bot.send_message(
        order["customer_id"],
        "🚗 <b>Haydovchi topildi!</b>\n\n"
        f"👤 Haydovchi: {driver.full_name} ({driver_contact})\n"
        "Tez orada siz bilan bog'lanadi.",
    )

    await callback.message.edit_text(
        callback.message.html_text
        + f"\n\n✅ Qabul qildi: {driver.full_name} ({driver_contact})",
        reply_markup=None,
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
