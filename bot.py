import os
import telebot
from telebot import types
import sqlite3
from datetime import datetime
from io import BytesIO
from threading import Thread
from flask import Flask, request, jsonify
import qrcode

TOKEN = os.getenv("TOKEN")
ADMIN_ID = 8896790430
API_KEY = os.getenv("API_KEY", "supersecret123")
MAIN_BOT_USERNAME = "blackcard_tb_bot"

bot = telebot.TeleBot(TOKEN)
bot.delete_webhook()
app = Flask(__name__)

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
            status TEXT DEFAULT 'started',
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
            username=excluded.username,
            full_name=excluded.full_name,
            last_seen=excluded.last_seen
    """, (user.id, username, full_name, now, now))
    conn.commit()
    conn.close()

def get_staff_stats(staff_id):
    conn = sqlite3.connect("staff.db")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM referrals WHERE staff_id=?", (staff_id,))
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM referrals WHERE staff_id=? AND status='completed'", (staff_id,))
    completed = cur.fetchone()[0]
    conn.close()
    return total, completed

init_db()

@app.route("/api/my_stats")
def api_my_stats():
    staff_id = request.args.get("user_id")
    if not staff_id:
        return jsonify({"error": "no user"}), 400
    total, completed = get_staff_stats(int(staff_id))
    return jsonify({"total": total, "completed": completed})

@app.route("/api/admin_stats")
def api_admin_stats():
    if request.args.get("key") != API_KEY:
        return jsonify({"error": "forbidden"}), 403
    conn = sqlite3.connect("staff.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, full_name FROM staff")
    rows = cur.fetchall()
    result = []
    for r in rows:
        total, completed = get_staff_stats(r[0])
        result.append({
            "user_id": r[0],
            "username": r[1],
            "full_name": r[2],
            "total": total,
            "completed": completed
        })
    conn.close()
    return jsonify({"staff": result})

def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(types.KeyboardButton("📲 Получить мой QR-код"))
    markup.add(types.KeyboardButton("📊 Моя статистика"))
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    save_staff(message.from_user)
    bot.send_message(
        message.chat.id,
        "👋 <b>Бот для сотрудников</b>\n\nПолучи свой QR и смотри статистику.",
        reply_markup=main_keyboard(),
        parse_mode="HTML"
    )

@bot.message_handler(func=lambda m: m.text == "📲 Получить мой QR-код")
def generate_qr(message):
    save_staff(message.from_user)
    link = f"https://t.me/{MAIN_BOT_USERNAME}?start=emp_{message.from_user.id}"
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    bio = BytesIO()
    img.save(bio, "PNG")
    bio.seek(0)
    bot.send_photo(
        message.chat.id,
        bio,
        caption=f"📲 <b>Твой QR</b>\n\n<code>{link}</code>",
        parse_mode="HTML"
    )

@bot.message_handler(func=lambda m: m.text == "📊 Моя статистика")
def my_stats(message):
    total, completed = get_staff_stats(message.from_user.id)
    bot.send_message(
        message.chat.id,
        f"📊 <b>Твоя статистика</b>\n\nПриведено: <b>{total}</b>\nВыполнили: <b>{completed}</b>",
        parse_mode="HTML"
    )

def run_api():
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    Thread(target=run_api, daemon=True).start()
    print("✅ Staff-бот + API запущены")
    bot.infinity_polling()
