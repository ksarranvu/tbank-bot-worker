import os
import telebot
from telebot import types
import sqlite3
from datetime import datetime
from io import BytesIO
from threading import Thread
from flask import Flask, request, jsonify
from flask_cors import CORS
import qrcode

TOKEN = os.getenv("TOKEN")
ADMIN_ID = 8896790430
API_KEY = os.getenv("API_KEY", "LOX22899")
MAIN_BOT_USERNAME = "blackcard_tb_bot"  # основной бот без @
WEBAPP_URL = "https://ksarranvu.github.io/tbank-bot-worker/"  # ссылка на мини-приложение staff

bot = telebot.TeleBot(TOKEN)
bot.delete_webhook()

app = Flask(__name__)
CORS(app)

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

def save_staff_data(user_id, username="нет", full_name="Без имени"):
    conn = sqlite3.connect("staff.db")
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cur.execute("""
        INSERT INTO staff (user_id, username, full_name, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username,
            full_name=excluded.full_name,
            last_seen=excluded.last_seen
    """, (user_id, username, full_name, now, now))
    conn.commit()
    conn.close()

def save_staff(user):
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Без имени"
    username = user.username or "нет"
    save_staff_data(user.id, username, full_name)

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

# ===== API =====
@app.route("/")
def home():
    return "Staff bot API OK"

@app.route("/api/register", methods=["GET", "POST"])
def api_register():
    data = request.json if request.is_json else {}
    user_id = request.args.get("user_id") or data.get("user_id")
    username = request.args.get("username") or data.get("username") or "нет"
    full_name = request.args.get("full_name") or data.get("full_name") or "Без имени"

    if not user_id:
        return jsonify({"error": "no user_id"}), 400
    try:
        user_id = int(user_id)
    except:
        return jsonify({"error": "bad user_id"}), 400

    save_staff_data(user_id, username, full_name)
    link = f"https://t.me/{MAIN_BOT_USERNAME}?start=emp_{user_id}"
    return jsonify({"ok": True, "user_id": user_id, "link": link})

@app.route("/api/my_stats")
def api_my_stats():
    staff_id = request.args.get("user_id")
    if not staff_id:
        return jsonify({"error": "no user"}), 400
    try:
        total, completed = get_staff_stats(int(staff_id))
    except:
        return jsonify({"error": "bad user_id"}), 400
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

# ===== BOT UI =====
def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(types.KeyboardButton("📲 Получить мой QR-код"))
    markup.add(types.KeyboardButton("📊 Моя статистика"))
    return markup

def webapp_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        text="📱 Открыть кабинет",
        web_app=types.WebAppInfo(url=WEBAPP_URL)
    ))
    return markup

def send_qr_to_user(message):
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
        caption=f"📲 <b>Твой QR</b>\n\nЗакреплён за тобой.\n\n<code>{link}</code>",
        parse_mode="HTML"
    )

@bot.message_handler(commands=['start'])
def start(message):
    save_staff(message.from_user)

    # из мини-приложения: ?start=qr
    if message.text and "qr" in message.text.lower():
        bot.send_message(
            message.chat.id,
            "Готовлю твой QR…",
            reply_markup=main_keyboard()
        )
        send_qr_to_user(message)
        return

    bot.send_message(
        message.chat.id,
        "👋 <b>Бот для сотрудников</b>\n\nПолучи QR и смотри статистику.\nВыбирай действие 👇",
        reply_markup=main_keyboard(),
        parse_mode="HTML"
    )
    bot.send_message(
        message.chat.id,
        "Или открой мини-приложение:",
        reply_markup=webapp_keyboard()
    )

@bot.message_handler(func=lambda m: m.text == "📲 Получить мой QR-код")
def generate_qr(message):
    send_qr_to_user(message)

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
    print("✅ Staff-бот + Flask + CORS")
    bot.infinity_polling()
