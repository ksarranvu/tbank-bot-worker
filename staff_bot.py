import asyncio
import logging
import qrcode
from io import BytesIO
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from dotenv import load_dotenv
import os

from database import (
    init_db, add_employee, get_employee_stats, get_all_stats,
    get_employee_name
)

load_dotenv()

STAFF_TOKEN = os.getenv("STAFF_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=STAFF_TOKEN)
dp = Dispatcher()

logging.basicConfig(level=logging.INFO)

# ========== Клавиатуры ==========

def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Получить мой QR-код", callback_data="get_qr")],
        [InlineKeyboardButton(text="📊 Моя статистика", callback_data="my_stats")],
    ])

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Получить мой QR-код", callback_data="get_qr")],
        [InlineKeyboardButton(text="📊 Моя статистика", callback_data="my_stats")],
        [InlineKeyboardButton(text="📈 Полный отчёт", callback_data="full_report")],
    ])

# ========== Уведомления ==========

async def notify_admin(text: str):
    try:
        await bot.send_message(ADMIN_ID, text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.error(f"Не удалось отправить уведомление админу: {e}")

# ========== Хендлеры ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = message.from_user
    await add_employee(user.id, user.full_name, user.username)

    text = (
        f"<b>Привет, {user.first_name}!</b>\n\n"
        "Это бот для сотрудников <b>BlackCard</b>.\n\n"
        "Здесь ты можешь получить свой персональный QR-код "
        "и отслеживать результаты."
    )

    kb = admin_kb() if user.id == ADMIN_ID else main_kb()
    await message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)

@dp.callback_query(F.data == "get_qr")
async def get_qr(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    link = f"https://t.me/blackcard_tb_bot?start=ref_{user_id}"

    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1a1a1a", back_color="white")

    bio = BytesIO()
    img.save(bio, "PNG")
    bio.seek(0)

    photo = BufferedInputFile(bio.read(), filename="qr.png")

    text = (
        f"<b>Твой персональный QR-код</b>\n\n"
        f"Ссылка:\n<code>{link}</code>\n\n"
        "Отправляй этот QR людям.\n"
        "Когда они оформят продукт — тебе засчитается."
    )

    await callback.message.answer_photo(photo, caption=text, parse_mode=ParseMode.HTML)
    await callback.answer()

@dp.callback_query(F.data == "my_stats")
async def my_stats(callback: types.CallbackQuery):
    stats = await get_employee_stats(callback.from_user.id)

    text = (
        f"<b>📊 Твоя статистика</b>\n\n"
        f"👥 Перешли по QR: <b>{stats['clicked']}</b>\n"
        f"📝 Оформили заявку: <b>{stats['applied']}</b>\n"
        f"✅ Выполнили условия: <b>{stats['completed']}</b>"
    )
    await callback.message.answer(text, parse_mode=ParseMode.HTML)
    await callback.answer()

@dp.callback_query(F.data == "full_report")
async def full_report(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return

    rows = await get_all_stats()
    if not rows:
        await callback.message.answer("Пока нет данных.")
        await callback.answer()
        return

    text = "<b>📈 Полный отчёт по сотрудникам</b>\n\n"

    for row in rows:
        user_id, full_name, username, clicked, applied, completed = row
        name = full_name or "Без имени"
        uname = f"@{username}" if username else "—"
        text += (
            f"<b>{name}</b> ({uname})\n"
            f"ID: <code>{user_id}</code>\n"
            f"Переходы: {clicked} | Оформили: {applied} | Выполнили: {completed}\n\n"
        )

    await callback.message.answer(text, parse_mode=ParseMode.HTML)
    await callback.answer()

async def main():
    await init_db()
    print("Staff bot started...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
