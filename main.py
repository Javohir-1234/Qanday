import asyncio
import logging
import os
import sqlite3
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.enums import ChatAction, ChatMemberStatus
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8821690561:AAEevaxTzOcmy8l_HjCSyRdLz1FRlcBCvcs")
ADMIN_ID = 5492502957
ADMIN_USERNAME = "@Javoh_1hacker"
CHANNEL_USERNAME = "@qoshiqyaratish"
CHANNEL_LINK = "https://t.me/qoshiqyaratish"
SONG_PRICE_SHORT = 5000    # 30 soniyalik
SONG_PRICE_FULL = 15000   # 2-3 daqiqalik
SECRET_CODE = "J1a2v3o4h5i6r7"
SECRET_BONUS = 10000

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

conn = sqlite3.connect("music_bot.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    fullname TEXT,
    username TEXT,
    balance INTEGER DEFAULT 0,
    total_paid INTEGER DEFAULT 0,
    used_secret INTEGER DEFAULT 0
)
""")
try:
    cursor.execute("ALTER TABLE users ADD COLUMN used_secret INTEGER DEFAULT 0")
    conn.commit()
except Exception:
    pass
cursor.execute("""
CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    description TEXT,
    file_id TEXT
)
""")
conn.commit()

def db_register_user(user_id, fullname, username):
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (user_id, fullname, username, balance, used_secret) VALUES (?, ?, ?, ?, ?)", (user_id, fullname, username, 0, 0))
        conn.commit()
        return True
    cursor.execute("UPDATE users SET fullname = ?, username = ? WHERE user_id = ?", (fullname, username, user_id))
    conn.commit()
    return False

def db_get_user(user_id):
    cursor.execute("SELECT balance, total_paid, username, fullname, used_secret FROM users WHERE user_id = ?", (user_id,))
    return cursor.fetchone()

def db_add_balance(user_id, amount):
    cursor.execute("UPDATE users SET balance = balance + ?, total_paid = total_paid + ? WHERE user_id = ?", (amount, amount, user_id))
    conn.commit()

def db_deduct_balance(user_id, amount):
    cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
    conn.commit()

def db_mark_secret_used(user_id):
    cursor.execute("UPDATE users SET used_secret = 1 WHERE user_id = ?", (user_id,))
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

def db_delete_sample(sample_id):
    cursor.execute("DELETE FROM samples WHERE id = ?", (sample_id,))
    conn.commit()

class CreateSong(StatesGroup):
    waiting_for_type = State()
    waiting_for_text = State()
    waiting_for_genre = State()

class DepositState(StatesGroup):
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

def get_main_menu(user_id):
    buttons = [
        [KeyboardButton(text="🎵 Qo'shiq yaratish"), KeyboardButton(text="🎼 Qo'shiq namunaviy")],
        [KeyboardButton(text="📊 Balans"), KeyboardButton(text="💳 Pul kiritish")],
        [KeyboardButton(text="👨‍💼 Admin")]
    ]
    if user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="🛠 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_song_type_menu():
    buttons = [
        [KeyboardButton(text="⚡ 30 soniyalik — 5,000 so'm")],
        [KeyboardButton(text="🎶 2-3 daqiqalik — 15,000 so'm")]
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
    await message.answer("⛔ Botdan foydalanish uchun avval kanalimizga obuna bo'ling!\n\nObuna bo'lgach, <b>✅ Obuna bo'ldim</b> tugmasini bosing.", parse_mode="HTML", reply_markup=get_subscribe_keyboard())
    return False

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: CallbackQuery, state: FSMContext):
    if await is_subscribed(callback.from_user.id):
        db_register_user(callback.from_user.id, callback.from_user.full_name, callback.from_user.username)
        await state.clear()
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(
            f"🎉 <b>Xush kelibsiz, {callback.from_user.full_name}!</b>\n\n"
            "🤖 <b>Qo'shiq Yaratish Botiga muvaffaqiyatli kirdingiz!</b>\n\n"
            "━━━━━━━━━━━━━━━━━━\n✨ <b>BOT IMKONIYATLARI</b>\n━━━━━━━━━━━━━━━━━━\n\n"
            "🎵 Ismga atab maxsus qo'shiq\n🎤 Pop, Rep, Bass va boshqa janrlar\n"
            "📝 Professional qo'shiq matnlari\n⚡ Tez va sifatli xizmat\n🎼 Tayyor namunaviy qo'shiqlar\n\n"
            f"━━━━━━━━━━━━━━━━━━\n💰 <b>Narxi:</b> {SONG_PRICE:,} so'm\n⏳ <b>Tayyorlanish:</b> 24 soatgacha\n━━━━━━━━━━━━━━━━━━\n\n"
            "🔥 O'zingizga yoki yaqinlaringizga atalgan maxsus qo'shiq buyurtma berishingiz mumkin.\n\n"
            "👇 <b>Quyidagi menyudan foydalaning:</b>",
            parse_mode="HTML", reply_markup=get_main_menu(callback.from_user.id)
        )
    else:
        await callback.answer("❌ Siz hali kanalga obuna bo'lmagansiz!", show_alert=True)

@dp.message(F.text == "/start")
async def start_cmd(message: Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    await state.clear()
    if not await is_subscribed(message.from_user.id):
        await message.answer(f"👋 Xush kelibsiz, <b>{message.from_user.full_name}</b>!\n\n⛔ Botdan foydalanish uchun avval kanalimizga obuna bo'lishingiz kerak!\n\n👇 Quyidagi tugmani bosib obuna bo'ling:", parse_mode="HTML", reply_markup=get_subscribe_keyboard())
        return
    is_new = db_register_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    welcome_text = (
        f"👋 Xush kelibsiz, <b>{message.from_user.full_name}</b>!\n\n"
        "🤖 <b>Men – Sun'iy Intellekt asosida ishlaydigan eng ilg'or musiqa botiman!</b>\n\n"
        "✨ <b>Mening imkoniyatlarim:</b>\n"
        "📝 Har qanday mavzuda mukammal va ma'noli <b>qo'shiq matnlari</b> yarata olaman.\n"
        "👤 Istalgan <b>ismlarga atab</b> maxsus va kreativ treklar tayyorlab beraman!\n"
        "🎵 Pop, Rep, Bass va boshqa janrlarda professional kuylar bastalayman.\n\n"
    )
    if is_new:
        welcome_text += "🎉 Botimizga xush kelibsiz! Qo'shiq buyurtma berish uchun avval balansingizni to'ldiring yoki <b>🎼 Qo'shiq namunaviy</b> bo'limini ko'rib chiqing.\n\n👇 Quyidagi menyudan foydalaning:"
    else:
        welcome_text += "Quyidagi menyu orqali bot imkoniyatlaridan to'liq foydalanishingiz mumkin 👇"
    await message.answer(welcome_text, reply_markup=get_main_menu(message.from_user.id), parse_mode="HTML")

# --- MAXFIY KOD ---
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
        await message.answer("❌ Siz bu koddan allaqachon foydalangansiz!\nKod faqat 1 marta ishlatiladi.", reply_markup=get_main_menu(message.from_user.id))
        return
    db_add_balance(message.from_user.id, SECRET_BONUS)
    db_mark_secret_used(message.from_user.id)
    await message.answer(
        f"🎉 <b>Tabriklaymiz!</b>\n\n"
        f"✅ Maxfiy kod qabul qilindi!\n"
        f"💰 Balansingizga <b>{SECRET_BONUS:,} so'm</b> bonus qo'shildi!\n\n"
        f"🎵 Endi qo'shiq buyurtma berishingiz mumkin!",
        parse_mode="HTML", reply_markup=get_main_menu(message.from_user.id)
    )

@dp.message(F.text == "📊 Balans")
async def balance_cmd(message: Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    if not await check_and_notify(message, state): return
    await state.clear()
    user_data = db_get_user(message.from_user.id)
    balance = user_data[0] if user_data else 0
    await message.answer(
        f"💰 Sizning balansingiz: <b>{balance:,} so'm</b>\n\n"
        f"📌 Narxlar:\n"
        f"⚡ 30 soniyalik — <b>5,000 so'm</b>\n"
        f"🎶 2-3 daqiqalik — <b>15,000 so'm</b>",
        parse_mode="HTML"
    )

@dp.message(F.text == "💳 Pul kiritish")
async def deposit_cmd(message: Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    if not await check_and_notify(message, state): return
    await state.clear()
    text = (
        "💳 <b>Balansni to'ldirish tartibi:</b>\n\n"
        "Karta raqami: <code>6262570040359129</code>\n\n"
        f"📌 Narxlar:\n"
        f"⚡ 30 soniyalik — <b>5,000 so'm</b>\n"
        f"🎶 2-3 daqiqalik — <b>15,000 so'm</b>\n\n"
        f"Sizning Telegram ID raqamingiz: <code>{message.from_user.id}</code>\n\n"
        "✅ To'lovni amalga oshirgach, <b>chek (screenshot)ni shu yerga yuboring</b> — "
        "u avtomatik ravishda ID ingiz bilan adminga jo'natiladi. Agar botga ishonmasangiz adminga yozing"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_menu(message.from_user.id))
    await state.set_state(DepositState.waiting_for_receipt)

@dp.message(DepositState.waiting_for_receipt)
async def process_receipt(message: Message, state: FSMContext):
    menu_buttons = ["🎵 Qo'shiq yaratish", "🎼 Qo'shiq namunaviy", "📊 Balans", "💳 Pul kiritish", "👨‍💼 Admin", "🛠 Admin Panel", "⬅️ Bosh menyu"]
    if message.text and message.text in menu_buttons:
        await state.clear()
        if message.text == "💳 Pul kiritish": await deposit_cmd(message, state)
        elif message.text == "🎵 Qo'shiq yaratish": await create_song_start(message, state)
        elif message.text == "🎼 Qo'shiq namunaviy": await song_samples_cmd(message, state)
        elif message.text == "📊 Balans": await balance_cmd(message, state)
        elif message.text == "👨‍💼 Admin": await admin_contact_cmd(message, state)
        elif message.text == "🛠 Admin Panel": await admin_panel_cmd(message)
        else: await back_cmd(message, state)
        return
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    user_info = f"@{message.from_user.username}" if message.from_user.username else "Username yo'q"
    caption = (f"💳 <b>YANGI TO'LOV CHEKI KELDI!</b>\n\n👤 Ismi: {message.from_user.full_name}\n🔗 Lichkasi: {user_info}\n🆔 Telegram ID: <code>{message.from_user.id}</code>")
    try:
        if message.photo: await bot.send_photo(chat_id=ADMIN_ID, photo=message.photo[-1].file_id, caption=caption, parse_mode="HTML")
        elif message.document: await bot.send_document(chat_id=ADMIN_ID, document=message.document.file_id, caption=caption, parse_mode="HTML")
        elif message.text: await bot.send_message(chat_id=ADMIN_ID, text=caption + f"\n\n📝 Matn: {message.text}", parse_mode="HTML")
        else:
            await message.copy_to(chat_id=ADMIN_ID)
            await bot.send_message(chat_id=ADMIN_ID, text=caption, parse_mode="HTML")
        await message.answer("✅ Chekingiz adminga yuborildi! Tez orada balansingiz to'ldiriladi.", reply_markup=get_main_menu(message.from_user.id))
    except Exception as e:
        logging.error(f"Chek yuborishda xatolik: {e}")
        await message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.", reply_markup=get_main_menu(message.from_user.id))
    await state.clear()

@dp.message(F.text == "👨‍💼 Admin")
async def admin_contact_cmd(message: Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    if not await check_and_notify(message, state): return
    await state.clear()
    await message.answer(f"👨‍💻 Admin bilan bog'lanish: <a href='https://t.me/Javoh_1hacker'>{ADMIN_USERNAME}</a>\n\nSavollaringiz yoki takliflaringiz bo'lsa, bemalol yozishingiz mumkin.", parse_mode="HTML")

@dp.message(F.text == "⬅️ Bosh menyu")
async def back_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Bosh menyudasiz.", reply_markup=get_main_menu(message.from_user.id))

@dp.message(F.text == "🎼 Qo'shiq namunaviy")
async def song_samples_cmd(message: Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    if not await check_and_notify(message, state): return
    await state.clear()
    samples = db_get_samples()
    if not samples:
        await message.answer("🎼 <b>Qo'shiq namunaviy</b>\n\nHozircha namuna qo'shiqlar yo'q.\nAdmin tez orada namunalar qo'shadi! 🎵", parse_mode="HTML", reply_markup=get_main_menu(message.from_user.id))
        return
    await message.answer(f"🎼 <b>Qo'shiq namunaviy ({len(samples)} ta)</b>\n\nQuyida bizning bot orqali yaratilgan namuna qo'shiqlarni eshitishingiz mumkin:", parse_mode="HTML")
    for sample in samples:
        sid, title, description, file_id = sample
        if file_id:
            try: await bot.send_audio(chat_id=message.chat.id, audio=file_id, caption=f"<b>{title}</b>\n{description}", parse_mode="HTML")
            except Exception: await message.answer(f"🎵 <b>{title}</b>\n{description}", parse_mode="HTML")
        else:
            await message.answer(f"🎵 <b>{title}</b>\n{description}\n\n<i>(Audio fayl hali qo'shilmagan)</i>", parse_mode="HTML")
    await message.answer(
        f"👆 Yuqoridagi namunalar botimiz tomonidan yaratilgan.\n\n"
        f"🎵 O'zingizga shaxsiy qo'shiq buyurtma berish uchun <b>«🎵 Qo'shiq yaratish»</b> tugmasini bosing!\n\n"
        f"📌 Narxlar:\n"
        f"⚡ 30 soniyalik — <b>5,000 so'm</b>\n"
        f"🎶 2-3 daqiqalik — <b>15,000 so'm</b>",
        parse_mode="HTML", reply_markup=get_main_menu(message.from_user.id)
    )

@dp.message(F.text == "🎵 Qo'shiq yaratish")
async def create_song_start(message: Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    if not await check_and_notify(message, state): return
    await state.clear()
    user_data = db_get_user(message.from_user.id)
    balance = user_data[0] if user_data else 0
    if balance < SONG_PRICE_SHORT:
        await message.answer(
            f"⚠️ Balansingiz yetarli emas.\n\n"
            f"💰 Sizning balansingiz: <b>{balance:,} so'm</b>\n\n"
            f"📌 Narxlar:\n"
            f"⚡ 30 soniyalik — <b>5,000 so'm</b>\n"
            f"🎶 2-3 daqiqalik — <b>15,000 so'm</b>\n\n"
            "Avval '💳 Pul kiritish' orqali balansingizni to'ldiring.",
            parse_mode="HTML"
        )
        return
    await message.answer(
        f"🎵 <b>Qo'shiq turini tanlang:</b>\n\n"
        f"⚡ <b>30 soniyalik</b> — 5,000 so'm\n"
        f"🎶 <b>2-3 daqiqalik</b> — 15,000 so'm\n\n"
        f"💰 Sizning balansingiz: <b>{balance:,} so'm</b>",
        parse_mode="HTML",
        reply_markup=get_song_type_menu()
    )
    await state.set_state(CreateSong.waiting_for_type)

@dp.message(CreateSong.waiting_for_type)
async def process_song_type(message: Message, state: FSMContext):
    menu_buttons = ["🎵 Qo'shiq yaratish", "🎼 Qo'shiq namunaviy", "📊 Balans", "💳 Pul kiritish", "👨‍💼 Admin", "🛠 Admin Panel"]
    if message.text in menu_buttons:
        await state.clear()
        await message.answer("Jarayon bekor qilindi.", reply_markup=get_main_menu(message.from_user.id))
        return

    if message.text == "⚡ 30 soniyalik — 5,000 so'm":
        price = SONG_PRICE_SHORT
        song_type = "30 soniyalik"
    elif message.text == "🎶 2-3 daqiqalik — 15,000 so'm":
        price = SONG_PRICE_FULL
        song_type = "2-3 daqiqalik"
    else:
        await message.answer("Iltimos, quyidagi tugmalardan birini tanlang:", reply_markup=get_song_type_menu())
        return

    user_data = db_get_user(message.from_user.id)
    balance = user_data[0] if user_data else 0
    if balance < price:
        await message.answer(
            f"⚠️ Balansingiz yetarli emas.\n"
            f"Kerakli summa: <b>{price:,} so'm</b>\n"
            f"Sizning balansingiz: <b>{balance:,} so'm</b>\n\n"
            "Avval '💳 Pul kiritish' orqali balansingizni to'ldiring.",
            parse_mode="HTML",
            reply_markup=get_main_menu(message.from_user.id)
        )
        await state.clear()
        return

    await state.update_data(song_type=song_type, song_price=price)
    await message.answer(
        f"✅ <b>{song_type}</b> tanlandi — {price:,} so'm\n\n"
        "📝 Qo'shiq kimga atalgan yoki nima haqida bo'lishi kerak?\nTo'liq matnni yoki g'oyangizni yozib qoldiring:",
        parse_mode="HTML",
        reply_markup=get_main_menu(message.from_user.id)
    )
    await state.set_state(CreateSong.waiting_for_text)

@dp.message(CreateSong.waiting_for_text)
async def process_song_text(message: Message, state: FSMContext):
    menu_buttons = ["🎵 Qo'shiq yaratish", "🎼 Qo'shiq namunaviy", "📊 Balans", "💳 Pul kiritish", "👨‍💼 Admin", "🛠 Admin Panel"]
    if message.text in menu_buttons:
        await state.clear()
        await message.answer("Jarayon bekor qilindi.", reply_markup=get_main_menu(message.from_user.id))
        return
    if not message.text:
        await message.answer("Iltimos, qo'shiq matnini matn ko'rinishida yuboring:")
        return
    await state.update_data(song_text=message.text)
    await message.answer("🎵 Qo'shiq qaysi musiqa uslubida (janrda) bo'lsin? Tanlang:", reply_markup=get_genre_menu())
    await state.set_state(CreateSong.waiting_for_genre)

@dp.message(CreateSong.waiting_for_genre)
async def process_song_genre(message: Message, state: FSMContext):
    menu_buttons = ["🎵 Qo'shiq yaratish", "🎼 Qo'shiq namunaviy", "📊 Balans", "💳 Pul kiritish", "👨‍💼 Admin", "🛠 Admin Panel"]
    if message.text in menu_buttons:
        await state.clear()
        await message.answer("Jarayon bekor qilindi.", reply_markup=get_main_menu(message.from_user.id))
        return
    genre = message.text
    data = await state.get_data()
    song_text = data.get('song_text', 'Matn topilmadi')
    song_type = data.get('song_type', '30 soniyalik')
    price = data.get('song_price', SONG_PRICE_SHORT)
    user_data = db_get_user(message.from_user.id)
    if user_data and user_data[0] >= price:
        db_deduct_balance(message.from_user.id, price)
    else:
        await message.answer("⚠️ Xatolik: Balansingiz yetarli emas.", reply_markup=get_main_menu(message.from_user.id))
        await state.clear()
        return
    user_info = f"@{message.from_user.username}" if message.from_user.username else "Mavjud emas"
    admin_msg = (
        f"🎤 <b>YANGI BUYURTMA KELDI!</b>\n\n"
        f"👤 Kimdan: {message.from_user.full_name}\n"
        f"🔗 Lichkasi: {user_info}\n"
        f"🆔 ID: <code>{message.from_user.id}</code>\n"
        f"⏱ Turi: {song_type}\n"
        f"💰 Narxi: {price:,} so'm\n"
        f"🎶 Janri: {genre}\n"
        f"📝 Matn/Mavzu: {song_text}"
    )
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=admin_msg, parse_mode="HTML")
        await message.answer("✅ Qo'shiq matni adminga yuborildi. Sizga qo'shiq 24 soat ichida yuboriladi.", reply_markup=get_main_menu(message.from_user.id))
    except Exception as e:
        logging.error(f"Adminga buyurtma yuborishda xatolik: {e}")
        await message.answer("❌ Buyurtmani yuborishda xatolik yuz berdi.", reply_markup=get_main_menu(message.from_user.id))
    await state.clear()

@dp.message(F.text == "🛠 Admin Panel")
async def admin_panel_cmd(message: Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("🛠 <b>Boshqaruv paneli</b>", parse_mode="HTML", reply_markup=get_admin_menu())

@dp.message(F.text == "📈 Statistika")
async def stats_cmd(message: Message):
    if message.from_user.id != ADMIN_ID: return
    count, total = db_get_stats()
    samples = db_get_samples()
    await message.answer(f"📈 <b>Bot Statistikasi:</b>\n\n👥 A'zolar: {count or 0} ta\n💰 Jami kiritilgan pul: {total or 0:,} so'm\n🎵 Namuna qo'shiqlar: {len(samples)} ta", parse_mode="HTML")

@dp.message(F.text == "💰 Pul berish")
async def give_money_start(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Foydalanuvchi ID raqamini kiriting:")
    await state.set_state(AdminActions.waiting_for_user_id_p)

@dp.message(AdminActions.waiting_for_user_id_p)
async def give_money_id(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("ID faqat raqamlardan iborat bo'lishi kerak. Qayta kiriting:")
        return
    await state.update_data(target_id=message.text)
    await message.answer("Summani kiriting (Faqat raqamda):")
    await state.set_state(AdminActions.waiting_for_money)

@dp.message(AdminActions.waiting_for_money)
async def give_money_final(message: Message, state: FSMContext):
    try:
        amount = int(message.text)
        data = await state.get_data()
        target_id = int(data['target_id'])
        db_add_balance(target_id, amount)
        await message.answer("✅ Pul balansga muvaffaqiyatli qo'shildi.")
        try: await bot.send_message(target_id, f"🎉 Balansingiz admin tomonidan {amount:,} so'mga to'ldirildi!")
        except Exception: pass
    except ValueError:
        await message.answer("Xato kiritildi. Summa faqat raqam bo'lishi kerak.")
    finally:
        await state.clear()

@dp.message(F.text == "✉️ Xabar yuborish")
async def send_msg_start(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.set_state(AdminActions.waiting_for_broadcast_choice)
    await message.answer("📨 <b>Xabar/Qo'shiq yuborish</b>\n\nKimga yubormoqchisiz?", parse_mode="HTML", reply_markup=get_broadcast_choice_keyboard())

@dp.callback_query(F.data == "broadcast_all")
async def broadcast_all_choice(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: return
    await state.update_data(broadcast_type="all")
    await state.set_state(AdminActions.waiting_for_message)
    await callback.message.edit_text("📢 <b>Hammaga yuborish</b>\n\nYubormoqchi bo'lgan xabar, qo'shiq yoki faylni yuboring:", parse_mode="HTML")

@dp.callback_query(F.data == "broadcast_one")
async def broadcast_one_choice(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID: return
    await state.update_data(broadcast_type="one")
    await state.set_state(AdminActions.waiting_for_user_id_m)
    await callback.message.edit_text("👤 <b>1 kishiga yuborish</b>\n\nFoydalanuvchi <b>Telegram ID</b> sini kiriting:", parse_mode="HTML")

@dp.message(AdminActions.waiting_for_user_id_m)
async def send_msg_id(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ ID faqat raqamlardan iborat bo'lishi kerak. Qayta kiriting:")
        return
    await state.update_data(target_id=message.text)
    await message.answer("📝 Xabar matnini yoki qo'shiq (audio/fayl)ni yuboring:")
    await state.set_state(AdminActions.waiting_for_message)

@dp.message(AdminActions.waiting_for_message)
async def send_msg_final(message: Message, state: FSMContext):
    data = await state.get_data()
    broadcast_type = data.get("broadcast_type", "one")
    if broadcast_type == "all":
        user_ids = db_get_all_user_ids()
        success = 0
        failed = 0
        await message.answer(f"⏳ {len(user_ids)} ta foydalanuvchiga yuborilmoqda...")
        for uid in user_ids:
            try:
                await message.copy_to(chat_id=uid)
                success += 1
                await asyncio.sleep(0.05)
            except Exception as e:
                logging.warning(f"Foydalanuvchi {uid} ga yuborib bo'lmadi: {e}")
                failed += 1
        await message.answer(f"✅ <b>Tarqatish yakunlandi!</b>\n\n✔️ Muvaffaqiyatli: {success} ta\n❌ Yuborib bo'lmadi: {failed} ta", parse_mode="HTML", reply_markup=get_admin_menu())
    else:
        target_id = int(data.get("target_id", 0))
        try:
            await message.copy_to(chat_id=target_id)
            await message.answer("✅ Xabar/Qo'shiq foydalanuvchiga muvaffaqiyatli yuborildi.", reply_markup=get_admin_menu())
        except Exception as e:
            await message.answer(f"❌ Xatolik: Xabarni yuborib bo'lmadi.\n\n{e}", reply_markup=get_admin_menu())
    await state.clear()

@dp.message(F.text == "🎵 Namuna qo'shish")
async def add_sample_start(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    samples = db_get_samples()
    info = ""
    if samples:
        info = "📋 <b>Mavjud namunalar:</b>\n"
        for s in samples: info += f"  • [{s[0]}] {s[1]}\n"
        info += "\n"
    await message.answer(f"{info}➕ <b>Yangi namuna qo'shish</b>\n\nNamuna qo'shiqning <b>nomini</b> kiriting:", parse_mode="HTML")
    await state.set_state(AdminActions.waiting_for_sample_title)

@dp.message(AdminActions.waiting_for_sample_title)
async def add_sample_title(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Iltimos, nom kiriting:")
        return
    await state.update_data(sample_title=message.text)
    await message.answer("📝 Namuna uchun qisqacha <b>tavsif</b> yozing (janri, kim uchun va boshqa):", parse_mode="HTML")
    await state.set_state(AdminActions.waiting_for_sample_desc)

@dp.message(AdminActions.waiting_for_sample_desc)
async def add_sample_desc(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Iltimos, tavsif kiriting:")
        return
    await state.update_data(sample_desc=message.text)
    await message.answer("🎵 Endi namuna <b>audio faylini</b> yuboring.\nYoki audio yo'q bo'lsa, <b>/skip</b> yozing:", parse_mode="HTML")
    await state.set_state(AdminActions.waiting_for_sample_file)

@dp.message(AdminActions.waiting_for_sample_file)
async def add_sample_file(message: Message, state: FSMContext):
    data = await state.get_data()
    title = data.get("sample_title", "Nomsiz")
    desc = data.get("sample_desc", "")
    file_id = None
    if message.audio: file_id = message.audio.file_id
    elif message.voice: file_id = message.voice.file_id
    elif message.document: file_id = message.document.file_id
    elif message.text == "/skip": file_id = None
    else:
        await message.answer("Audio fayl yuboring yoki /skip yozing:")
        return
    db_add_sample(title, desc, file_id)
    await message.answer(f"✅ Namuna muvaffaqiyatli qo'shildi!\n\n🎵 <b>{title}</b>\n{desc}", parse_mode="HTML", reply_markup=get_admin_menu())
    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
