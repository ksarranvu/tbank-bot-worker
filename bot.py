import os
import telebot
from telebot import types
import sqlite3
from datetime import datetime
import qrcode
from io import BytesIO

TOKEN = os.getenv("TOKEN")
bot = telebot.TeleBot(TOKEN)
bot.delete_webhook()

# ===== НАСТРОЙКИ =====
ADMIN_ID = 8896790430
MAIN_BOT_USERNAME = "blackcard_tb_bot"   # ← юзернейм ОСНОВНОГО бота (без @)

# ===== БАЗА ДАННЫХ =====
def init_db():
    conn = sqlite3.connect("staff.db")
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS staff (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            first_seen TEXT,
            last_seen TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_id INTEGER,
            client_id INTEGER,
            client_name TEXT,
            status TEXT DEFAULT 'started',  -- started / completed
            created_at TEXT
        )
    """)
    
    conn.commit()
    conn.close()

def save_staff(user):
    conn = sqlite3.connect("staff.db")
    cur = conn.cursor()
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    username = user.username or "нет"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    cur.execute("""
        INSERT INTO staff (user_id, username, full_name, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            full_name = excluded.full_name,
            last_seen = excluded.last_seen
    """, (user.id, username, full_name, now, now))
    
    conn.commit()
    conn.close()

def get_staff_stats(staff_id):
    conn = sqlite3.connect("staff.db")
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM referrals WHERE staff_id = ?", (staff_id,))
    total = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM referrals WHERE staff_id = ? AND status = 'completed'", (staff_id,))
    completed = cur.fetchone()[0]
    
    conn.close()
    return total, completed

def get_all_stats():
    conn = sqlite3.connect("staff.db")
    cur = conn.cursor()
    
    cur.execute("SELECT user_id, username, full_name FROM staff")
    staff_list = cur.fetchall()
    
    result = []
    for s in staff_list:
        total, completed = get_staff_stats(s[0])
        result.append({
            "user_id": s[0],
            "username": s[1],
            "full_name": s[2],
            "total": total,
            "completed": completed
        })
    
    conn.close()
    return result

init_db()

# ===== КЛАВИАТУРА =====
def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(types.KeyboardButton("📲 Получить мой QR-код"))
    markup.add(types.KeyboardButton("📊 Моя статистика"))
    return markup

# ===== START =====
@bot.message_handler(commands=['start'])
def start(message):
    save_staff(message.from_user)
    
    text = (
        "👋 <b>Бот для сотрудников</b>\n\n"
        "Здесь ты получаешь свой личный QR-код.\n"
        "Все люди, которые перейдут по нему и оформят продукт — будут закреплены за тобой.\n\n"
        "Выбирай действие 👇"
    )
    bot.send_message(message.chat.id, text, reply_markup=main_keyboard(), parse_mode="HTML")

# ===== ГЕНЕРАЦИЯ QR =====
@bot.message_handler(func=lambda m: m.text == "📲 Получить мой QR-код")
def generate_qr(message):
    save_staff(message.from_user)
    
    # Ссылка вида: https://t.me/blackcard_tb_bot?start=emp_123456789
    link = f"https://t.me/{MAIN_BOT_USERNAME}?start=emp_{message.from_user.id}"
    
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(link)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    bio = BytesIO()
    img.save(bio, "PNG")
    bio.seek(0)
    
    caption = (
        f"📲 <b>Твой личный QR-код</b>\n\n"
        f"Все переходы и оформления по этому QR будут закреплены за тобой.\n\n"
        f"Ссылка:\n<code>{link}</code>"
    )
    
    bot.send_photo(message.chat.id, bio, caption=caption, parse_mode="HTML")

# ===== СТАТИСТИКА СОТРУДНИКА =====
@bot.message_handler(func=lambda m: m.text == "📊 Моя статистика")
def my_stats(message):
    total, completed = get_staff_stats(message.from_user.id)
    
    text = (
        f"📊 <b>Твоя статистика</b>\n\n"
        f"👥 Всего приведено: <b>{total}</b>\n"
        f"✅ Выполнили условия: <b>{completed}</b>"
    )
    bot.send_message(message.chat.id, text, parse_mode="HTML")

# ===== АДМИН: ОБЩАЯ СТАТИСТИКА =====
@bot.message_handler(commands=['stats'])
def admin_stats(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    stats = get_all_stats()
    
    if not stats:
        bot.send_message(message.chat.id, "Пока нет данных.")
        return
    
    text = "📊 <b>Статистика по сотрудникам</b>\n\n"
    
    for s in stats:
        text += (
            f"👤 <b>{s['full_name']}</b>\n"
            f"ID: <code>{s['user_id']}</code>\n"
            f"@{s['username']}\n"
            f"Приведено: {s['total']} | Выполнили: {s['completed']}\n"
            f"————————————\n"
        )
        
        if len(text) > 3500:
            bot.send_message(message.chat.id, text, parse_mode="HTML")
            text = ""
    
    if text:
        bot.send_message(message.chat.id, text, parse_mode="HTML")

print("✅ Staff-бот запущен!")
bot.infinity_polling()
