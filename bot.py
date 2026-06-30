import asyncio
import logging
import os
import sqlite3
import re
import hashlib
import requests
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from aiogram.enums import ChatAction, ChatMemberStatus
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from google.cloud import vision
from google.oauth2 import service_account

# === BOT SOZLAMALARI ===
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8821690561:AAHBvwTe8WX1TY8GHr6tYYnmy0AhyTRWK6o")
ADMIN_ID = 5492502957
ADMIN_USERNAME = "@Javoh_1hacker"
CHANNEL_USERNAME = "@qoshiqyaratish"
CHANNEL_LINK = "https://t.me/qoshiqyaratish"

SONG_PRICE_SHORT = 5000
SONG_PRICE_FULL = 15000
SECRET_CODE = "J1a2v3o4h5i6r7"
SECRET_BONUS = 10000

# Google Vision credentials
GOOGLE_CREDENTIALS_FILE = "horizontal-data-501009-n0-fbb206898628.json"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# === DATABASE ===
conn = sqlite3.connect("music_bot.db", check_same_thread=False)
cursor = conn.cursor()

# Users jadvali
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    fullname TEXT,
    username TEXT,
    balance INTEGER DEFAULT 0,
    total_paid INTEGER DEFAULT 0,
    used_secret INTEGER DEFAULT 0,
    pending_deposit INTEGER DEFAULT 0
)
""")

# Yangi ustunlarni qo'shish
for column in ["used_secret", "pending_deposit"]:
    try:
        cursor.execute(f"ALTER TABLE users ADD COLUMN {column} INTEGER DEFAULT 0")
        conn.commit()
    except Exception:
        pass

# Samples jadvali
cursor.execute("""
CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    description TEXT,
    file_id TEXT
)
""")

# Deposits jadvali
cursor.execute("""
CREATE TABLE IF NOT EXISTS deposits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount INTEGER,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    file_id TEXT,
    photo_hash TEXT UNIQUE
)
""")

for column in ["file_id", "photo_hash"]:
    try:
        cursor.execute(f"ALTER TABLE deposits ADD COLUMN {column} TEXT")
        conn.commit()
    except Exception:
        pass

conn.commit()

# === VISION CLIENT ===
def get_vision_client():
    try:
        if os.path.exists(GOOGLE_CREDENTIALS_FILE):
            credentials = service_account.Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE)
            return vision.ImageAnnotatorClient(credentials=credentials)
        return vision.ImageAnnotatorClient()
    except Exception as e:
        logging.error(f"Vision client xatolik: {e}")
        return None

# === DB FUNKSIYALARI ===
def db_register_user(user_id, fullname, username):
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (user_id, fullname, username, balance, used_secret, pending_deposit) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, fullname, username, 0, 0, 0)
        )
        conn.commit()
        return True
    cursor.execute("UPDATE users SET fullname = ?, username = ? WHERE user_id = ?", (fullname, username, user_id))
    conn.commit()
    return False

def db_get_user(user_id):
    cursor.execute("SELECT balance, total_paid, username, fullname, used_secret, pending_deposit FROM users WHERE user_id = ?", (user_id,))
    return cursor.fetchone()

def db_add_balance(user_id, amount):
    cursor.execute("UPDATE users SET balance = balance + ?, total_paid = total_paid + ? WHERE user_id = ?",
                   (amount, amount, user_id))
    conn.commit()

def db_deduct_balance(user_id, amount):
    cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
    conn.commit()

def db_mark_secret_used(user_id):
    cursor.execute("UPDATE users SET used_secret = 1 WHERE user_id = ?", (user_id,))
    conn.commit()

def db_set_pending_deposit(user_id, amount):
    cursor.execute("UPDATE users SET pending_deposit = ? WHERE user_id = ?", (amount, user_id))
    conn.commit()

def db_clear_pending_deposit(user_id):
    cursor.execute("UPDATE users SET pending_deposit = 0 WHERE user_id = ?", (user_id,))
    conn.commit()

def db_get_stats():
    cursor.execute("SELECT COUNT(user_id), SUM(total_paid) FROM users")
    return cursor.fetchone()

def db_get_all_user_ids():
    cursor.execute("SELECT user_id FROM users")
    return [row[0] for row in cursor.fetchall()]

def db_get_samples():
    cursor.execute("SELECT id, title, description, file_id FROM samples")
    return cursor.fetchall()

def db_add_sample(title, description, file_id):
    cursor.execute("INSERT INTO samples (title, description, file_id) VALUES (?, ?, ?)", (title, description, file_id))
    conn.commit()

# === DEPOSIT FUNKSIYALARI ===
def get_image_hash(image_content):
    return hashlib.md5(image_content).hexdigest()

def db_check_duplicate_hash(photo_hash):
    cursor.execute("SELECT id, user_id, status FROM deposits WHERE photo_hash = ?", (photo_hash,))
    return cursor.fetchone()

def db_add_deposit(user_id, amount, file_id, photo_hash):
    cursor.execute(
        "INSERT INTO deposits (user_id, amount, status, file_id, photo_hash) VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, 'pending', file_id, photo_hash)
    )
    conn.commit()
    return cursor.lastrowid

def db_update_deposit_status(deposit_id, status):
    cursor.execute("UPDATE deposits SET status = ? WHERE id = ?", (status, deposit_id))
    conn.commit()

def db_get_user_deposit_count(user_id):
    cursor.execute("SELECT COUNT(*) FROM deposits WHERE user_id = ? AND status = 'accepted'", (user_id,))
    return cursor.fetchone()[0]

# === CHEKNI AVTOMATIK TEKSHIRISH ===
async def extract_text_from_image(image_content):
    try:
        client = get_vision_client()
        if client:
            image = vision.Image(content=image_content)
            response = client.text_detection(image=image)
            texts = response.text_annotations
            if texts:
                return texts[0].description
        return None
    except Exception as e:
        logging.error(f"Vision API xatolik: {e}")
        return None

def extract_amount_from_text(text):
    if not text:
        return None
    
    patterns = [
        r'(\d+[\s,.]*\d*)\s*(?:sum|so\'m|сом|uzs|soum)',
        r'(?:sum|so\'m|сом|uzs|soum)\s*(\d+[\s,.]*\d*)',
        r'(\d+[\s,.]*\d*)\s*₩',
        r'(\d+[\s,.]*\d*)',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            amount_str = re.sub(r'[^\d]', '', str(match))
            if amount_str and len(amount_str) >= 4:
                try:
                    amount = int(amount_str)
                    if 1000 <= amount <= 100000000:
                        return amount
                except ValueError:
                    continue
    return None

async def check_receipt_photo(file_id, expected_amount):
    try:
        file_info = await bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
        response = requests.get(file_url)
        image_content = response.content
        
        photo_hash = get_image_hash(image_content)
        
        existing = db_check_duplicate_hash(photo_hash)
        if existing:
            deposit_id, user_id, status = existing
            if status == 'accepted':
                return False, f"❌ Bu chek allaqachon ishlatilgan!", photo_hash
            elif status == 'pending':
                return False, "⏳ Bu chek allaqachon tekshirilmoqda!", photo_hash
            else:
                return False, "❌ Bu chek avval rad etilgan!", photo_hash
        
        text = await extract_text_from_image(image_content)
        
        if not text:
            return False, "❌ Rasmdan matn topilmadi. Aniqroq rasm yuboring.", photo_hash
        
        logging.info(f"Chekdan olingan matn: {text[:200]}...")
        
        detected_amount = extract_amount_from_text(text)
        
        if not detected_amount:
            return False, "❌ Chekdan summa topilmadi.", photo_hash
        
        if detected_amount >= expected_amount * 0.9 and detected_amount <= expected_amount * 1.1:
            return True, f"✅ To'lov tasdiqlandi! Summa: {detected_amount:,} so'm", photo_hash
        else:
            return False, f"❌ Summa mos emas. Chekda: {detected_amount:,} so'm, Kerakli: {expected_amount:,} so'm", photo_hash
            
    except Exception as e:
        logging.error(f"Chekni tekshirishda xatolik: {e}")
        return False, f"❌ Xatolik: {str(e)}", None

# === FSM STATES ===
class CreateSong(StatesGroup):
    waiting_for_type = State()
    waiting_for_text = State()
    waiting_for_genre = State()

class DepositState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_receipt = State()

class AdminActions(StatesGroup):
    waiting_for_broadcast_choice = State()
    waiting_for_user_id_m = State()
    waiting_for_message = State()
    waiting_for_user_id_p = State()
    waiting_for_money = State()
    waiting_for_sample_title = State()
    waiting_for_sample_desc = State()
    waiting_for_sample_file = State()

# === KEYBOARDS ===
def get_main_menu(user_id):
    buttons = [
        [KeyboardButton(text="🎵 Qo'shiq yaratish"), KeyboardButton(text="🎼 Qo'shiq namunaviy")],
        [KeyboardButton(text="📊 Balans"), KeyboardButton(text="💳 Pul kiritish")]
    ]
    if user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="🔐 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_song_type_menu():
    buttons = [
        [KeyboardButton(text=f"⚡ 30 soniyalik — {SONG_PRICE_SHORT:,} so'm")],
        [KeyboardButton(text=f"🎶 2-3 daqiqalik — {SONG_PRICE_FULL:,} so'm")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_genre_menu():
    buttons = [
        [KeyboardButton(text="🎤 Pop"), KeyboardButton(text="🎧 Rep")],
        [KeyboardButton(text="🔊 Bass"), KeyboardButton(text="🎼 Boshqa")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_admin_menu():
    buttons = [
        [KeyboardButton(text="💰 Pul berish"), KeyboardButton(text="✉️ Xabar yuborish")],
        [KeyboardButton(text="📈 Statistika"), KeyboardButton(text="🎵 Namuna qo'shish")],
        [KeyboardButton(text="⬅️ Bosh menyu")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_subscribe_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url=CHANNEL_LINK)],
        [InlineKeyboardButton(text="✅ Obuna bo'ldim", callback_data="check_sub")]
    ])

def get_broadcast_choice_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Hammaga yuborish", callback_data="broadcast_all")],
        [InlineKeyboardButton(text="👤 1 kishiga yuborish (ID orqali)", callback_data="broadcast_one")]
    ])

def get_deposit_actions_keyboard(deposit_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"deposit_accept_{deposit_id}"),
         InlineKeyboardButton(text="❌ Rad etish", callback_data=f"deposit_reject_{deposit_id}")]
    ])

# === PROXY FUNKSIYALAR ===
async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except Exception as e:
        logging.warning(f"Kanal tekshirishda xatolik: {e}")
        return False

async def check_and_notify(message: Message, state: FSMContext) -> bool:
    if await is_subscribed(message.from_user.id):
        return True
    await state.clear()
    await message.answer(
        "⛔ Botdan foydalanish uchun avval kanalimizga obuna bo'ling!\n\nObuna bo'lgach, ✅ Obuna bo'ldim tugmasini bosing.",
        parse_mode="HTML",
        reply_markup=get_subscribe_keyboard()
    )
    return False

# === HANDLERLAR ===
@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: CallbackQuery, state: FSMContext):
    if await is_subscribed(callback.from_user.id):
        db_register_user(callback.from_user.id, callback.from_user.full_name, callback.from_user.username)
        await state.clear()
        try:
            await callback.message.delete()
        except Exception:
            pass

        welcome_text = (
            f"🎉 Xush kelibsiz, {callback.from_user.full_name}!\n\n"
            "🤖 Qo'shiq Yaratish Botiga muvaffaqiyatli kirdingiz!\n\n"
            "━━━━━━━━━━━━━━━━━━\n✨ BOT IMKONIYATLARI\n━━━━━━━━━━━━━━━━━━\n\n"
            "📝 Har qanday mavzuda mukammal va ma'noli qo'shiq matnlari yarata olaman.\n"
            "👤 Istalgan ismlarga atab maxsus va kreativ treklar tayyorlab beraman!\n"
            "🎵 Pop, Rep, Bass va boshqa janrlarda professional kuylar bastalayman.\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚡ 30 soniyalik — {SONG_PRICE_SHORT:,} so'm\n"
            f"🎶 2-3 daqiqalik — {SONG_PRICE_FULL:,} so'm\n"
            f"⏳ Tayyorlanish: 24 soatgacha\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            "👇 Quyidagi menyudan foydalaning:"
        )
        await callback.message.answer(welcome_text, parse_mode="HTML", reply_markup=get_main_menu(callback.from_user.id))
    else:
        await callback.answer("❌ Siz hali kanalga obuna bo'lmagansiz!", show_alert=True)

@dp.message(F.text == "/start")
async def start_cmd(message: Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    await state.clear()

    if not await is_subscribed(message.from_user.id):
        await message.answer(
            f"👋 Xush kelibsiz, {message.from_user.full_name}!\n\n⛔ Botdan foydalanish uchun avval kanalimizga obuna bo'lishingiz kerak!\n\n👇 Quyidagi tugmani bosib obuna bo'ling:",
            parse_mode="HTML",
            reply_markup=get_subscribe_keyboard()
        )
        return

    is_new = db_register_user(message.from_user.id, message.from_user.full_name, message.from_user.username)

    welcome_text = (
        f"👋 Xush kelibsiz, {message.from_user.full_name}!\n\n"
        "🤖 Men – Sun'iy Intellekt asosida ishlaydigan eng ilg'or musiqa botiman!\n\n"
        "✨ Mening imkoniyatlarim:\n"
        "📝 Har qanday mavzuda mukammal va ma'noli qo'shiq matnlari yarata olaman.\n"
        "👤 Istalgan ismlarga atab maxsus va kreativ treklar tayyorlab beraman!\n"
        "🎵 Pop, Rep, Bass va boshqa janrlarda professional kuylar bastalayman.\n\n"
    )

    if is_new:
        welcome_text += "🎉 Botimizga xush kelibsiz! Qo'shiq buyurtma berish uchun avval balansingizni to'ldiring yoki 🎼 Qo'shiq namunaviy bo'limini ko'rib chiqing.\n\n👇 Quyidagi menyudan foydalaning:"
    else:
        welcome_text += "Quyidagi menyu orqali bot imkoniyatlaridan to'liq foydalanishingiz mumkin 👇"

    await message.answer(welcome_text, reply_markup=get_main_menu(message.from_user.id), parse_mode="HTML")

@dp.message(F.text == SECRET_CODE)
async def secret_code_handler(message: Message, state: FSMContext):
    if not await check_and_notify(message, state):
        return

    user_data = db_get_user(message.from_user.id)
    if not user_data:
        db_register_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
        user_data = db_get_user(message.from_user.id)

    used_secret = user_data[4] if user_data else 0

    if used_secret:
        await message.answer(
            "❌ Siz bu koddan allaqachon foydalangansiz!\nKod faqat 1 marta ishlatiladi.",
            reply_markup=get_main_menu(message.from_user.id)
        )
        return

    db_add_balance(message.from_user.id, SECRET_BONUS)
    db_mark_secret_used(message.from_user.id)

    await message.answer(
        f"🎉 Tabriklaymiz!\n\n"
        f"✅ Maxfiy kod qabul qilindi!\n"
        f"💰 Balansingizga {SECRET_BONUS:,} so'm bonus qo'shildi!\n\n"
        f"🎵 Endi qo'shiq buyurtma berishingiz mumkin!",
        parse_mode="HTML",
        reply_markup=get_main_menu(message.from_user.id)
    )

@dp.message(F.text == "📊 Balans")
async def balance_cmd(message: Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    if not await check_and_notify(message, state):
        return
    await state.clear()

    user_data = db_get_user(message.from_user.id)
    balance = user_data[0] if user_data else 0
    pending = user_data[5] if user_data and len(user_data) > 5 else 0

    text = f"💰 Sizning balansingiz: {balance:,} so'm"
    if pending > 0:
        text += f"\n⏳ Kutilayotgan to'lov: {pending:,} so'm"

    text += f"\n\n📌 Narxlar:\n⚡ 30 soniyalik — {SONG_PRICE_SHORT:,} so'm\n🎶 2-3 daqiqalik — {SONG_PRICE_FULL:,} so'm"

    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "💳 Pul kiritish")
async def deposit_cmd(message: Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    if not await check_and_notify(message, state):
        return
    await state.clear()

    text = (
        "💳 Balansni to'ldirish\n\n"
        "Qancha summa kiritmoqchisiz?\n"
        f"Minimal: {SONG_PRICE_SHORT:,} so'm\n\n"
        "Summani faqat raqamlarda kiriting (masalan: 5000):"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_menu(message.from_user.id))
    await state.set_state(DepositState.waiting_for_amount)

@dp.message(DepositState.waiting_for_amount)
async def process_deposit_amount(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("❌ Iltimos, summani faqat raqamlarda kiriting:")
        return
    
    amount = int(message.text)
    if amount < SONG_PRICE_SHORT:
        await message.answer(f"❌ Minimal summa {SONG_PRICE_SHORT:,} so'm. Qayta kiriting:")
        return
    
    await state.update_data(deposit_amount=amount)
    
    text = (
        "💳 To'lov qilish uchun:\n\n"
        "Karta raqami: 6262570040359129\n\n"
        f"💰 Summa: {amount:,} so'm\n\n"
        f"🆔 Telegram ID: {message.from_user.id}\n\n"
        "✅ To'lovni amalga oshirgach, chek (screenshot)ni yuboring:\n"
        "⚠️ Chek avtomatik tekshiriladi!"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_menu(message.from_user.id))
    await state.set_state(DepositState.waiting_for_receipt)

@dp.message(DepositState.waiting_for_receipt)
async def process_receipt(message: Message, state: FSMContext):
    menu_buttons = ["🎵 Qo'shiq yaratish", "🎼 Qo'shiq namunaviy", "📊 Balans", "💳 Pul kiritish", "👨‍💼 Admin", "🔐 Admin Panel", "⬅️ Bosh menyu"]

    if message.text and message.text in menu_buttons:
        await state.clear()
        if message.text == "💳 Pul kiritish":
            await deposit_cmd(message, state)
        elif message.text == "🎵 Qo'shiq yaratish":
            await create_song_start(message, state)
        elif message.text == "🎼 Qo'shiq namunaviy":
            await song_samples_cmd(message, state)
        elif message.text == "📊 Balans":
            await balance_cmd(message, state)
        elif message.text == "👨‍💼 Admin":
            await admin_contact_cmd(message, state)
        elif message.text == "🔐 Admin Panel":
            await admin_panel_cmd(message)
        else:
            await back_cmd(message, state)
        return

    if not message.photo:
        await message.answer("❌ Iltimos, chekni rasm (screenshot) ko'rinishida yuboring!")
        return
    
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    
    data = await state.get_data()
    expected_amount = data.get('deposit_amount', SONG_PRICE_SHORT)
    
    user_data = db_get_user(message.from_user.id)
    if not user_data:
        db_register_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
        user_data = db_get_user(message.from_user.id)
    
    deposit_count = db_get_user_deposit_count(message.from_user.id)
    photo = message.photo[-1]
    file_id = photo.file_id
    
    db_set_pending_deposit(message.from_user.id, expected_amount)
    
    # Chekni avtomatik tekshirish
    is_valid, result_message, photo_hash = await check_receipt_photo(file_id, expected_amount)
    
    if is_valid and photo_hash:
        # ✅ TO'LOV TASDIQLANDI
        db_add_balance(message.from_user.id, expected_amount)
        db_clear_pending_deposit(message.from_user.id)
        db_add_deposit(message.from_user.id, expected_amount, file_id, photo_hash)
        
        new_balance = db_get_user(message.from_user.id)[0]
        
        await message.answer(
            f"✅ {result_message}\n\n"
            f"💰 Balansingizga {expected_amount:,} so'm qo'shildi!\n"
            f"💳 Joriy balans: {new_balance:,} so'm\n"
            f"📊 Jami depositlar: {deposit_count + 1} ta\n\n"
            f"🎵 Endi qo'shiq buyurtma berishingiz mumkin!",
            parse_mode="HTML",
            reply_markup=get_main_menu(message.from_user.id)
        )
        
        await bot.send_message(
            ADMIN_ID,
            f"💳 AVTOMATIK TO'LOV TASDIQLANDI!\n\n"
            f"👤 Foydalanuvchi: {message.from_user.full_name}\n"
            f"🆔 ID: {message.from_user.id}\n"
            f"💰 Summa: {expected_amount:,} so'm\n"
            f"🔑 Chek hash: {photo_hash[:10]}...\n"
            f"🤖 Chek avtomatik tekshirildi!",
            parse_mode="HTML"
        )
        
        await state.clear()
        
    elif photo_hash:
        # ⚠️ CHEK TASDIQLANMADI - Admin tekshirishi kerak
        deposit_id = db_add_deposit(message.from_user.id, expected_amount, file_id, photo_hash)
        
        user_info = f"@{message.from_user.username}" if message.from_user.username else "Username yo'q"
        caption = (
            f"💳 YANGI CHEK KELDI (AVTOMATIK TEKSHIRILMADI)\n\n"
            f"👤 Foydalanuvchi: {message.from_user.full_name}\n"
            f"🔗 Lichkasi: {user_info}\n"
            f"🆔 ID: {message.from_user.id}\n"
            f"💰 Kutilgan summa: {expected_amount:,} so'm\n"
            f"📊 Jami depositlar: {deposit_count} ta\n"
            f"⚠️ {result_message}\n"
            f"🔑 Chek hash: {photo_hash[:10]}...\n\n"
            "✅ Qo'lda tekshirish kerak!"
        )
        
        await bot.send_photo(
            chat_id=ADMIN_ID,
            photo=file_id,
            caption=caption,
            parse_mode="HTML",
            reply_markup=get_deposit_actions_keyboard(deposit_id)
        )
        
        await message.answer(
            f"⚠️ Chek avtomatik tasdiqlanmadi.\n\n"
            f"📝 Sabab: {result_message}\n\n"
            f"👨‍💼 Chekingiz admin tomonidan tekshiriladi.\n"
            f"⏳ Bu jarayon 24 soatgacha vaqt olishi mumkin.\n"
            f"🔑 Chek ID: {deposit_id}\n\n"
            f"Agar tezroq tasdiqlash kerak bo'lsa, admin bilan bog'laning: {ADMIN_USERNAME}",
            parse_mode="HTML",
            reply_markup=get_main_menu(message.from_user.id)
        )
        
        await state.clear()
    else:
        await message.answer(
            f"❌ Chekni tekshirishda xatolik yuz berdi.\n\n"
            f"📝 {result_message}\n\n"
            f"👨‍💼 Iltimos, admin bilan bog'laning: {ADMIN_USERNAME}",
            parse_mode="HTML",
            reply_markup=get_main_menu(message.from_user.id)
        )
        await state.clear()

# === ADMIN CHEKNI TEKSHIRISH ===
@dp.callback_query(F.data.startswith("deposit_accept_"))
async def deposit_accept(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Siz admin emassiz!", show_alert=True)
        return
    
    deposit_id = int(callback.data.split("_")[2])
    
    cursor.execute("SELECT user_id, amount, photo_hash, status FROM deposits WHERE id = ?", (deposit_id,))
    deposit = cursor.fetchone()
    
    if not deposit:
        await callback.message.edit_text("❌ Bu chek topilmadi!")
        return
    
    user_id, amount, photo_hash, status = deposit
    
    if status != 'pending':
        await callback.message.edit_text(f"❌ Bu chek allaqachon {status} holatida!")
        return
    
    cursor.execute("SELECT id FROM deposits WHERE photo_hash = ? AND status = 'accepted'", (photo_hash,))
    if cursor.fetchone():
        await callback.message.edit_text("❌ Bu chek allaqachon boshqa foydalanuvchi tomonidan ishlatilgan!")
        await callback.answer("❌ Chek takrorlanmoqda!", show_alert=True)
        return
    
    db_add_balance(user_id, amount)
    db_update_deposit_status(deposit_id, 'accepted')
    db_clear_pending_deposit(user_id)
    
    deposit_count = db_get_user_deposit_count(user_id)
    new_balance = db_get_user(user_id)[0]
    
    await callback.message.edit_text(
        f"✅ To'lov tasdiqlandi!\n\n"
        f"👤 Foydalanuvchi ID: {user_id}\n"
        f"💰 Summa: {amount:,} so'm\n"
        f"💳 Yangi balans: {new_balance:,} so'm\n"
        f"🔑 Chek hash: {photo_hash[:10]}...\n"
        f"📊 Jami depositlar: {deposit_count} ta"
    )
    
    try:
        await bot.send_message(
            user_id,
            f"✅ Sizning {amount:,} so'm lik to'lovingiz tasdiqlandi!\n"
            f"💰 Joriy balans: {new_balance:,} so'm\n"
            f"📊 Jami depositlar: {deposit_count} ta\n\n"
            f"🎵 Endi qo'shiq buyurtma berishingiz mumkin!",
            parse_mode="HTML"
        )
    except Exception:
        pass
    
    await callback.answer("✅ To'lov tasdiqlandi!")

@dp.callback_query(F.data.startswith("deposit_reject_"))
async def deposit_reject(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Siz admin emassiz!", show_alert=True)
        return
    
    deposit_id = int(callback.data.split("_")[2])
    
    cursor.execute("SELECT user_id, amount, photo_hash FROM deposits WHERE id = ? AND status = 'pending'", (deposit_id,))
    deposit = cursor.fetchone()
    
    if not deposit:
        await callback.message.edit_text("❌ Bu chek allaqachon ko'rib chiqilgan!")
        return
    
    user_id, amount, photo_hash = deposit
    
    db_update_deposit_status(deposit_id, 'rejected')
    db_clear_pending_deposit(user_id)
    
    await callback.message.edit_text(
        f"❌ To'lov rad etildi!\n\n"
        f"👤 Foydalanuvchi ID: {user_id}\n"
        f"💰 Summa: {amount:,} so'm\n"
        f"🔑 Chek hash: {photo_hash[:10]}..."
    )
    
    try:
        await bot.send_message(
            user_id,
            f"❌ Sizning {amount:,} so'm lik to'lovingiz rad etildi.\n"
            f"Sababini bilish uchun admin bilan bog'laning: {ADMIN_USERNAME}",
            parse_mode="HTML"
        )
    except Exception:
        pass
    
    await callback.answer("❌ To'lov rad etildi!")

# === QO'SHIQ YARATISH ===
@dp.message(F.text == "🎵 Qo'shiq yaratish")
async def create_song_start(message: Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    if not await check_and_notify(message, state):
        return
    await state.clear()

    user_data = db_get_user(message.from_user.id)
    balance = user_data[0] if user_data else 0

    if balance < SONG_PRICE_SHORT:
        await message.answer(
            f"⚠️ Balansingiz yetarli emas.\n\n"
            f"💰 Sizning balansingiz: {balance:,} so'm\n\n"
            f"📌 Narxlar:\n"
            f"⚡ 30 soniyalik — {SONG_PRICE_SHORT:,} so'm\n"
            f"🎶 2-3 daqiqalik — {SONG_PRICE_FULL:,} so'm\n\n"
            "Avval '💳 Pul kiritish' orqali balansingizni to'ldiring.",
            parse_mode="HTML"
        )
        return

    await message.answer(
        f"🎵 Qo'shiq turini tanlang:\n\n"
        f"⚡ 30 soniyalik — {SONG_PRICE_SHORT:,} so'm\n"
        f"🎶 2-3 daqiqalik — {SONG_PRICE_FULL:,} so'm\n\n"
        f"💰 Sizning balansingiz: {balance:,} so'm",
        parse_mode="HTML",
        reply_markup=get_song_type_menu()
    )
    await state.set_state(CreateSong.choosing_type)  # qavs yopilishi shart

