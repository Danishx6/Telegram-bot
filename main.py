import telebot
import os
import time
import sqlite3
from flask import Flask, render_template_string
from keep_alive import keep_alive

# === CONFIG ===
TOKEN = "8099512038:AAHkAjgY5YBc5N5CwekoYMleXiZ81qUJxFo"
CHANNEL_USERNAME = "Linkmate"
DB_FILE = "file_storage.db"
ACCESS_WINDOW_SECONDS = 600  # 10 minutes

ADMIN_USERNAMES = ["Danish_x"]  

bot = telebot.TeleBot(TOKEN)

# === DB SETUP ===
with sqlite3.connect(DB_FILE) as conn:
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS files (
        file_key TEXT PRIMARY KEY,
        file_id TEXT,
        file_type TEXT,
        timestamp REAL
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS access_log (
        user_id INTEGER,
        file_key TEXT,
        access_time REAL,
        PRIMARY KEY(user_id, file_key)
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS groups (
        group_key TEXT,
        file_key TEXT
    )''')
    conn.commit()

# === Helper: Save file ===
def save_file(file_key, file_id, file_type):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("REPLACE INTO files (file_key, file_id, file_type, timestamp) VALUES (?, ?, ?, ?)",
                       (file_key, file_id, file_type, time.time()))
        conn.commit()

# === Helper: Load all files ===
def load_files():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_key, file_id, file_type, timestamp FROM files")
        return {row[0]: {'file_id': row[1], 'type': row[2], 'timestamp': row[3]} for row in cursor.fetchall()}

file_storage = load_files()

current_group = {}

def is_admin(user_id, username=None):
    if username and username in ADMIN_USERNAMES:
        return True
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ["administrator", "creator"]
    except:
        return False

# === Command: /newgroup ===
@bot.message_handler(commands=['newgroup'])
def newgroup(message):
    if not is_admin(message.from_user.id, message.from_user.username):
        bot.reply_to(message, "❌ Only admins can start a new group.")
        return
    group_key = str(int(time.time()))
    current_group[message.from_user.id] = group_key
    bot.reply_to(message, "📆 Group started! Now upload files. When done, send /endgroup to finish and get the link.")

# === Command: /endgroup ===
@bot.message_handler(commands=['endgroup'])
def endgroup(message):
    if not is_admin(message.from_user.id, message.from_user.username):
        bot.reply_to(message, "❌ Only admins can end a group.")
        return
    user_id = message.from_user.id
    group_key = current_group.pop(user_id, None)
    if not group_key:
        bot.reply_to(message, "⚠️ No active group found. Start one with /newgroup first.")
    else:
        link = f"https://t.me/{bot.get_me().username}?start={group_key}"
        bot.reply_to(message, f"✅ Group finalized!\n🔗 Share this link:\n{link}")

# === Command: /start ===
@bot.message_handler(commands=['start'])
def start(message):
    args = message.text.split()
    if len(args) > 1:
        key = args[1]
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT file_key FROM groups WHERE group_key = ?", (key,))
            rows = cursor.fetchall()

            now = time.time()
            cursor.execute("SELECT access_time FROM access_log WHERE user_id = ? AND file_key = ?", (message.from_user.id, key))
            row = cursor.fetchone()
            already_accessed = row and now - row[0] < ACCESS_WINDOW_SECONDS

            if rows:
                if not already_accessed:
                    cursor.execute("REPLACE INTO access_log (user_id, file_key, access_time) VALUES (?, ?, ?)",
                                   (message.from_user.id, key, now))
                    conn.commit()

                    sent_any = False
                    for r in rows:
                        file_key = r[0]
                        file_storage = load_files()
                        file_info = file_storage.get(file_key)
                        if file_info:
                            try:
                                if file_info['type'] == 'Photo':
                                    bot.send_photo(message.chat.id, file_info['file_id'], caption="🖼️ Access valid for 10 minutes.", protect_content=True)
                                elif file_info['type'] == 'Video':
                                    bot.send_video(message.chat.id, file_info['file_id'], caption="🎞️ Access valid for 10 minutes.", protect_content=True)
                                elif file_info['type'] == 'Audio':
                                    bot.send_audio(message.chat.id, file_info['file_id'], caption="🎵 Access valid for 10 minutes.", protect_content=True)
                                else:
                                    bot.send_document(message.chat.id, file_info['file_id'], caption="📄 Access valid for 10 minutes.", protect_content=True)
                                time.sleep(1.2)
                                sent_any = True
                            except Exception as e:
                                bot.send_message(message.chat.id, f"⚠️ Error sending one of the files: {e}")
                    if not sent_any:
                        bot.send_message(message.chat.id, "❗ No files could be sent.")
                else:
                    remaining = int(ACCESS_WINDOW_SECONDS - (now - row[0]))
                    bot.send_message(message.chat.id, f"⏳ Try again in {remaining} seconds.")
                return

            file_storage = load_files()
            file_key = key
            if file_key in file_storage:
                if not already_accessed:
                    cursor.execute("REPLACE INTO access_log (user_id, file_key, access_time) VALUES (?, ?, ?)",
                                   (message.from_user.id, file_key, now))
                    conn.commit()

                    file_info = file_storage[file_key]
                    caption = "⚠️ You can access this file for the next 10 minutes."
                    try:
                        if file_info['type'] == 'Photo':
                            bot.send_photo(message.chat.id, file_info['file_id'], caption=caption, protect_content=True)
                        elif file_info['type'] == 'Video':
                            bot.send_video(message.chat.id, file_info['file_id'], caption=caption, protect_content=True)
                        elif file_info['type'] == 'Audio':
                            bot.send_audio(message.chat.id, file_info['file_id'], caption=caption, protect_content=True)
                        else:
                            bot.send_document(message.chat.id, file_info['file_id'], caption=caption, protect_content=True)
                    except Exception as e:
                        bot.send_message(message.chat.id, f"❗ Error sending file: {e}")
                else:
                    remaining = int(ACCESS_WINDOW_SECONDS - (now - row[0]))
                    bot.send_message(message.chat.id, f"⏳ You already accessed this file. Try again in {remaining} seconds.")
            else:
                bot.send_message(message.chat.id, "❗ File not found.")
    else:
        bot.send_message(message.chat.id, "👋 Send me a file and I’ll give you a private shareable link!")

# === Command: /stats ===
@bot.message_handler(commands=['stats'])
def stats(message):
    if not is_admin(message.from_user.id, message.from_user.username):
        bot.reply_to(message, "❌ Only admins can view stats.")
        return
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM files")
        count = cursor.fetchone()[0]
    bot.send_message(message.chat.id, f"📆 Total saved files: {count}")

# === Command: /delete_old_files ===
@bot.message_handler(commands=['delete_old_files'])
def delete_old_files(message):
    if not is_admin(message.from_user.id, message.from_user.username):
        bot.reply_to(message, "❌ Only admins can delete files.")
        return
    threshold_time = time.time() - 7 * 24 * 60 * 60  # 7 days
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM files WHERE timestamp < ?", (threshold_time,))
        deleted = cursor.rowcount
        conn.commit()
    bot.send_message(message.chat.id, f"🚑 Deleted {deleted} files older than 7 days.")

# === File handler ===
@bot.message_handler(content_types=['document', 'photo', 'video', 'audio'])
def handle_file(message):
    if not is_admin(message.from_user.id, message.from_user.username):
        bot.reply_to(message, "❌ Only admins are allowed to upload files.")
        return

    file_id = None
    file_type = None

    if message.document:
        file_id = message.document.file_id
        file_type = "Document"
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_type = "Photo"
    elif message.video:
        file_id = message.video.file_id
        file_type = "Video"
    elif message.audio:
        file_id = message.audio.file_id
        file_type = "Audio"

    if file_id:
        file_key = str(int(time.time() * 1000))  # milliseconds
        save_file(file_key, file_id, file_type)

        user_id = message.from_user.id
        group_key = current_group.get(user_id)
        if group_key:
            with sqlite3.connect(DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO groups (group_key, file_key) VALUES (?, ?)", (group_key, file_key))
                conn.commit()
        else:
            link = f"https://t.me/{bot.get_me().username}?start={file_key}"
            bot.reply_to(message, f"✅ Your {file_type} was saved!\n\n🔗 Share this link:\n{link}")

# === Web UI ===
app = Flask('')

@app.route('/')
def dashboard():
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        cur.execute("SELECT file_key, file_type, timestamp FROM files ORDER BY timestamp DESC")
        files = [f"<li><b>{row[1]}</b> - <code>{row[0]}</code> - {time.ctime(row[2])}</li>" for row in cur.fetchall()]
        cur.execute("SELECT COUNT(*) FROM files")
        count = cur.fetchone()[0]
    return render_template_string("""
    <h2>📁 Saved Files: {{ count }}</h2>
    <ul>{{ files|safe }}</ul>
    """, count=count, files="\n".join(files))

keep_alive()
print("🤖 Bot is running...")
bot.infinity_polling(timeout=10, long_polling_timeout=5)
