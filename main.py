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

# --- SOZLAMALAR ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8821690561:AAHBvwTe8WX1TY8GHr6tYYnmy0AhyTRWK6o")
ADMIN_ID = 5492502957
ADMIN_USERNAME = "@Javoh_1hacker"
CHANNEL_USERNAME = "@qoshiqyaratish"
CHANNEL_LINK = "https://t.me/qoshiqyaratish"
SONG_PRICE = 5000

# Qo'shiq namunaviy ro'yxati — admin panel orqali o'zgartirilishi mumkin
SONG_SAMPLES = [
    {"title": "🎵 Sevgi qo'shig'i (Namuna)", "description": "Pop uslubida sevgi haqida yaratilgan qo'shiq namunasi.", "audio_file_id": None},
    {"title": "🎧 Rep namunasi", "description": "Zamonaviy rep uslubida ijro etilgan qo'shiq.", "audio_file_id": None},
    {"title": "🔊 Bass namunasi", "description": "Kuchli bass bilan tayyorlangan trек.", "audio_file_id": None},
]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# --- MA'LUMOTLAR BAZASI ---
conn = sqlite3.connect("music_bot.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    fullname TEXT,
    username TEXT,
    balance INTEGER DEFAULT 0,
    total_paid INTEGER DEFAULT 0
)
""")
# Namuna audio fayllarini saqlash jadvali
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
        # Yangi foydalanuvchi — bonus YO'Q, balans 0 dan boshlanadi
        cursor.execute(
            "INSERT INTO users (user_id, fullname, username, balance) VALUES (?, ?, ?, ?)",
            (user_id, fullname, username, 0)
        )
        conn.commit()
        return True
    cursor.execute(
        "UPDATE users SET fullname = ?, username = ? WHERE user_id = ?",
        (fullname, username, user_id)
    )
    conn.commit()
    return False

def db_get_user(user_id):
    cursor.execute("SELECT balance, total_paid, username, fullname FROM users WHERE user_id = ?", (user_id,))
    return cursor.fetchone()

def db_add_balance(user_id, amount):
    cursor.execute(
        "UPDATE users SET balance = balance + ?, total_paid = total_paid + ? WHERE user_id = ?",
        (amount, amount, user_id)
    )
    conn.commit()

def db_deduct_balance(user_id, amount):
    cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
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


# --- HOLATLAR ---
class CreateSong(StatesGroup):
    waiting_for_text = State()
    waiting_for_genre = State()

class DepositState(StatesGroup):
    waiting_for_receipt = State()

class AdminActions(StatesGroup):
    waiting_for_broadcast_choice = State()   # Hammaga yoki 1 kishiga
    waiting_for_user_id_m = State()          # 1 kishiga ID
    waiting_for_message = State()            # Xabar matni/fayli
    waiting_for_user_id_p = State()
    waiting_for_money = State()
    waiting_for_sample_title = State()
    waiting_for_sample_desc = State()
    waiting_for_sample_file = State()


# --- KLAVIATURALAR ---
def get_main_menu(user_id):
    buttons = [
        [KeyboardButton(text="🎵 Qo'shiq yaratish"), KeyboardButton(text="🎼 Qo'shiq namunaviy")],
        [KeyboardButton(text="📊 Balans"), KeyboardButton(text="💳 Pul kiritish")],
        [KeyboardButton(text="👨‍💼 Admin")]
    ]
    if user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="🛠 Admin Panel")])
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


# --- KANAL TEKSHIRUVI ---
# FIX: Bot kanalda admin bo'lmasa ham ishlaydi
# invite link orqali ham tekshirish imkoni yo'q, shuning uchun
# get_chat_member ishlamasa — True qaytarmaymiz, False qaytaramiz
async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR
        ]
    except Exception as e:
        logging.warning(f"Kanal tekshirishda xatolik: {e}")
        # Agar kanal private bo'lsa yoki bot admin bo'lmasa, False qaytaramiz
        # Bot kanalga admin sifatida qo'shilishi kerak!
        return False

async def check_and_notify(message: Message, state: FSMContext) -> bool:
    if await is_subscribed(message.from_user.id):
        return True
    await state.clear()
    await message.answer(
        "⛔ Botdan foydalanish uchun avval kanalimizga obuna bo'ling!\n\n"
        "Obuna bo'lgach, <b>✅ Obuna bo'ldim</b> tugmasini bosing.",
        parse_mode="HTML",
        reply_markup=get_subscribe_keyboard()
    )
    return False


# --- KANAL CALLBACK ---
@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: CallbackQuery):
    if await is_subscribed(callback.from_user.id):
        await callback.message.delete()
        await callback.message.answer(
            "✅ Rahmat! Endi botdan to'liq foydalanishingiz mumkin.",
            reply_markup=get_main_menu(callback.from_user.id)
        )
    else:
        await callback.answer("❌ Siz hali obuna bo'lmadingiz!", show_alert=True)


# --- ASOSIY HANDLERLAR ---
@dp.message(F.text == "/start")
async def start_cmd(message: Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    await state.clear()
    if not await is_subscribed(message.from_user.id):
        await message.answer(
            f"👋 Xush kelibsiz, <b>{message.from_user.full_name}</b>!\n\n"
            "⛔ Botdan foydalanish uchun avval kanalimizga obuna bo'lishingiz kerak!\n\n"
            "👇 Quyidagi tugmani bosib obuna bo'ling:",
            parse_mode="HTML",
            reply_markup=get_subscribe_keyboard()
        )
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
        welcome_text += (
            "🎉 Botimizga xush kelibsiz! Qo'shiq buyurtma berish uchun avval balansingizni "
            "to'ldiring yoki <b>🎼 Qo'shiq namunaviy</b> bo'limini ko'rib chiqing.\n\n"
            "👇 Quyidagi menyudan foydalaning:"
        )
    else:
        welcome_text += "Quyidagi menyu orqali bot imkoniyatlaridan to'liq foydalanishingiz mumkin 👇"

    await message.answer(welcome_text, reply_markup=get_main_menu(message.from_user.id), parse_mode="HTML")


@dp.message(F.text == "📊 Balans")
async def balance_cmd(message: Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    if not await check_and_notify(message, state):
        return
    await state.clear()
    user_data = db_get_user(message.from_user.id)
    balance = user_data[0] if user_data else 0
    await message.answer(
        f"💰 Sizning balansingiz: <b>{balance:,} so'm</b>\n"
        f"<i>(1 ta super qo'shiq = {SONG_PRICE:,} so'm)</i>",
        parse_mode="HTML"
    )


@dp.message(F.text == "💳 Pul kiritish")
async def deposit_cmd(message: Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    if not await check_and_notify(message, state):
        return
    await state.clear()
    text = (
        "💳 <b>Balansni to'ldirish tartibi:</b>\n\n"
        "Karta raqami: <code>8600 0000 0000 0000</code>\n"
        f"Narxi: 1 ta qo'shiq = <b>{SONG_PRICE:,} so'm</b>.\n\n"
        f"Sizning Telegram ID raqamingiz: <code>{message.from_user.id}</code>\n\n"
        "✅ To'lovni amalga oshirgach, <b>chek (screenshot)ni shu yerga yuboring</b> — "
        "u avtomatik ravishda ID ingiz bilan adminga jo'natiladi."
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_menu(message.from_user.id))
    await state.set_state(DepositState.waiting_for_receipt)


@dp.message(DepositState.waiting_for_receipt)
async def process_receipt(message: Message, state: FSMContext):
    menu_buttons = ["🎵 Qo'shiq yaratish", "🎼 Qo'shiq namunaviy", "📊 Balans",
                    "💳 Pul kiritish", "👨‍💼 Admin", "🛠 Admin Panel", "⬅️ Bosh menyu"]
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
        elif message.text == "🛠 Admin Panel":
            await admin_panel_cmd(message)
        else:
            await back_cmd(message, state)
        return

    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    user_info = f"@{message.from_user.username}" if message.from_user.username else "Username yo'q"
    caption = (
        "💳 <b>YANGI TO'LOV CHEKI KELDI!</b>\n\n"
        f"👤 Ismi: {message.from_user.full_name}\n"
        f"🔗 Lichkasi: {user_info}\n"
        f"🆔 Telegram ID: <code>{message.from_user.id}</code>"
    )
    try:
        if message.photo:
            await bot.send_photo(chat_id=ADMIN_ID, photo=message.photo[-1].file_id, caption=caption, parse_mode="HTML")
        elif message.document:
            await bot.send_document(chat_id=ADMIN_ID, document=message.document.file_id, caption=caption, parse_mode="HTML")
        elif message.text:
            await bot.send_message(chat_id=ADMIN_ID, text=caption + f"\n\n📝 Matn: {message.text}", parse_mode="HTML")
        else:
            await message.copy_to(chat_id=ADMIN_ID)
            await bot.send_message(chat_id=ADMIN_ID, text=caption, parse_mode="HTML")
        await message.answer(
            "✅ Chekingiz adminga yuborildi! Tez orada balansingiz to'ldiriladi.",
            reply_markup=get_main_menu(message.from_user.id)
        )
    except Exception as e:
        logging.error(f"Chek yuborishda xatolik: {e}")
        await message.answer("❌ Xatolik yuz berdi. Qayta urinib ko'ring.", reply_markup=get_main_menu(message.from_user.id))
    await state.clear()


@dp.message(F.text == "👨‍💼 Admin")
async def admin_contact_cmd(message: Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    if not await check_and_notify(message, state):
        return
    await state.clear()
    await message.answer(
        f"👨‍💻 Admin bilan bog'lanish: <a href='https://t.me/Javoh_1hacker'>{ADMIN_USERNAME}</a>\n\n"
        "Savollaringiz yoki takliflaringiz bo'lsa, bemalol yozishingiz mumkin.",
        parse_mode="HTML"
    )


@dp.message(F.text == "⬅️ Bosh menyu")
async def back_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Bosh menyudasiz.", reply_markup=get_main_menu(message.from_user.id))


# --- QO'SHIQ NAMUNALARI ---
@dp.message(F.text == "🎼 Qo'shiq namunaviy")
async def song_samples_cmd(message: Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    if not await check_and_notify(message, state):
        return
    await state.clear()

    samples = db_get_samples()
    if not samples:
        await message.answer(
            "🎼 <b>Qo'shiq namunaviy</b>\n\n"
            "Hozircha namuna qo'shiqlar yo'q.\n"
            "Admin tez orada namunalar qo'shadi! 🎵",
            parse_mode="HTML",
            reply_markup=get_main_menu(message.from_user.id)
        )
        return

    await message.answer(
        f"🎼 <b>Qo'shiq namunaviy ({len(samples)} ta)</b>\n\n"
        "Quyida bizning bot orqali yaratilgan namuna qo'shiqlarni eshitishingiz mumkin:",
        parse_mode="HTML"
    )

    for sample in samples:
        sid, title, description, file_id = sample
        if file_id:
            try:
                await bot.send_audio(
                    chat_id=message.chat.id,
                    audio=file_id,
                    caption=f"<b>{title}</b>\n{description}",
                    parse_mode="HTML"
                )
            except Exception:
                await message.answer(f"🎵 <b>{title}</b>\n{description}", parse_mode="HTML")
        else:
            await message.answer(
                f"🎵 <b>{title}</b>\n{description}\n\n<i>(Audio fayl hali qo'shilmagan)</i>",
                parse_mode="HTML"
            )

    await message.answer(
        f"👆 Yuqoridagi namunalar botimiz tomonidan yaratilgan.\n\n"
        f"🎵 O'zingizga shaxsiy qo'shiq buyurtma berish uchun <b>«🎵 Qo'shiq yaratish»</b> tugmasini bosing!\n"
        f"Narxi: <b>{SONG_PRICE:,} so'm</b>",
        parse_mode="HTML",
        reply_markup=get_main_menu(message.from_user.id)
    )


# --- QO'SHIQ YARATISH ---
@dp.message(F.text == "🎵 Qo'shiq yaratish")
async def create_song_start(message: Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
    if not await check_and_notify(message, state):
        return
    await state.clear()
    user_data = db_get_user(message.from_user.id)
    balance = user_data[0] if user_data else 0
    if balance < SONG_PRICE:
        await message.answer(
            f"⚠️ Balansingiz yetarli emas.\n"
            f"Kerakli summa: <b>{SONG_PRICE:,} so'm</b>\n"
            f"Sizning balansingiz: <b>{balance:,} so'm</b>\n\n"
            "Avval '💳 Pul kiritish' orqali balansingizni to'ldiring.",
            parse_mode="HTML"
        )
        return
    await message.answer("📝 Qo'shiq kimga atalgan yoki nima haqida bo'lishi kerak? To'liq matnni yoki g'oyangizni yozib qoldiring:")
    await state.set_state(CreateSong.waiting_for_text)


@dp.message(CreateSong.waiting_for_text)
async def process_song_text(message: Message, state: FSMContext):
    menu_buttons = ["🎵 Qo'shiq yaratish", "🎼 Qo'shiq namunaviy", "📊 Balans",
                    "💳 Pul kiritish", "👨‍💼 Admin", "🛠 Admin Panel"]
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
    menu_buttons = ["🎵 Qo'shiq yaratish", "🎼 Qo'shiq namunaviy", "📊 Balans",
                    "💳 Pul kiritish", "👨‍💼 Admin", "🛠 Admin Panel"]
    if message.text in menu_buttons:
        await state.clear()
        await message.answer("Jarayon bekor qilindi.", reply_markup=get_main_menu(message.from_user.id))
        return
    genre = message.text
    data = await state.get_data()
    song_text = data.get('song_text', 'Matn topilmadi')
    user_data = db_get_user(message.from_user.id)
    if user_data and user_data[0] >= SONG_PRICE:
        db_deduct_balance(message.from_user.id, SONG_PRICE)
    else:
        await message.answer("⚠️ Xatolik: Balansingiz yetarli emas.", reply_markup=get_main_menu(message.from_user.id))
        await state.clear()
        return
    user_info = f"@{message.from_user.username}" if message.from_user.username else "Mavjud emas"
    admin_msg = (
        "🎤 <b>YANGI BUYURTMA KELDI!</b>\n\n"
        f"👤 Kimdan: {message.from_user.full_name}\n"
        f"🔗 Lichkasi: {user_info}\n"
        f"🆔 ID: <code>{message.from_user.id}</code>\n"
        f"🎶 Janri: {genre}\n"
        f"📝 Matn/Mavzu: {song_text}"
    )
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=admin_msg, parse_mode="HTML")
        await message.answer(
            "✅ Qo'shiq matni adminga yuborildi. Sizga qo'shiq 24 soat ichida yuboriladi.",
            reply_markup=get_main_menu(message.from_user.id)
        )
    except Exception as e:
        logging.error(f"Adminga buyurtma yuborishda xatolik: {e}")
        await message.answer("❌ Buyurtmani yuborishda xatolik yuz berdi.", reply_markup=get_main_menu(message.from_user.id))
    await state.clear()


# --- ADMIN PANEL ---
@dp.message(F.text == "🛠 Admin Panel")
async def admin_panel_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("🛠 <b>Boshqaruv paneli</b>", parse_mode="HTML", reply_markup=get_admin_menu())


@dp.message(F.text == "📈 Statistika")
async def stats_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    count, total = db_get_stats()
    samples = db_get_samples()
    await message.answer(
        f"📈 <b>Bot Statistikasi:</b>\n\n"
        f"👥 A'zolar: {count or 0} ta\n"
        f"💰 Jami kiritilgan pul: {total or 0:,} so'm\n"
        f"🎵 Namuna qo'shiqlar: {len(samples)} ta",
        parse_mode="HTML"
    )


@dp.message(F.text == "💰 Pul berish")
async def give_money_start(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
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
        try:
            await bot.send_message(target_id, f"🎉 Balansingiz admin tomonidan {amount:,} so'mga to'ldirildi!")
        except:
            pass
    except ValueError:
        await message.answer("Xato kiritildi. Summa faqat raqam bo'lishi kerak.")
    finally:
        await state.clear()


# --- XABAR YUBORISH (YANGILANGAN) ---
@dp.message(F.text == "✉️ Xabar yuborish")
async def send_msg_start(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminActions.waiting_for_broadcast_choice)
    await message.answer(
        "📨 <b>Xabar/Qo'shiq yuborish</b>\n\nKimga yubormoqchisiz?",
        parse_mode="HTML",
        reply_markup=get_broadcast_choice_keyboard()
    )


@dp.callback_query(F.data == "broadcast_all")
async def broadcast_all_choice(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.update_data(broadcast_type="all")
    await state.set_state(AdminActions.waiting_for_message)
    await callback.message.edit_text(
        "📢 <b>Hammaga yuborish</b>\n\n"
        "Yubormoqchi bo'lgan xabar, qo'shiq yoki faylni yuboring:",
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "broadcast_one")
async def broadcast_one_choice(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.update_data(broadcast_type="one")
    await state.set_state(AdminActions.waiting_for_user_id_m)
    await callback.message.edit_text(
        "👤 <b>1 kishiga yuborish</b>\n\n"
        "Foydalanuvchi <b>Telegram ID</b> sini kiriting:",
        parse_mode="HTML"
    )


@dp.message(AdminActions.waiting_for_user_id_m)
async def send_msg_id(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ ID faqat raqamlardan iborat bo'lishi kerak. Qayta kiriting:")
        return
    await state.update_data(target_id=message.text)
    await message.answer(
        "📝 Xabar matnini yoki qo'shiq (audio/fayl)ni yuboring:",
    )
    await state.set_state(AdminActions.waiting_for_message)


@dp.message(AdminActions.waiting_for_message)
async def send_msg_final(message: Message, state: FSMContext):
    data = await state.get_data()
    broadcast_type = data.get("broadcast_type", "one")

    if broadcast_type == "all":
        # Hammaga yuborish
        user_ids = db_get_all_user_ids()
        success = 0
        failed = 0
        await message.answer(f"⏳ {len(user_ids)} ta foydalanuvchiga yuborilmoqda...")
        for uid in user_ids:
            try:
                await message.copy_to(chat_id=uid)
                success += 1
                await asyncio.sleep(0.05)  # Flood limit oldini olish
            except Exception as e:
                logging.warning(f"Foydalanuvchi {uid} ga yuborib bo'lmadi: {e}")
                failed += 1
        await message.answer(
            f"✅ <b>Tarqatish yakunlandi!</b>\n\n"
            f"✔️ Muvaffaqiyatli: {success} ta\n"
            f"❌ Yuborib bo'lmadi: {failed} ta",
            parse_mode="HTML",
            reply_markup=get_admin_menu()
        )
    else:
        # 1 kishiga yuborish
        target_id = int(data.get("target_id", 0))
        try:
            await message.copy_to(chat_id=target_id)
            await message.answer("✅ Xabar/Qo'shiq foydalanuvchiga muvaffaqiyatli yuborildi.", reply_markup=get_admin_menu())
        except Exception as e:
            await message.answer(f"❌ Xatolik: Xabarni yuborib bo'lmadi.\n\n{e}", reply_markup=get_admin_menu())

    await state.clear()


# --- NAMUNA QO'SHISH (ADMIN) ---
@dp.message(F.text == "🎵 Namuna qo'shish")
async def add_sample_start(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    samples = db_get_samples()
    info = ""
    if samples:
        info = "📋 <b>Mavjud namunalar:</b>\n"
        for s in samples:
            info += f"  • [{s[0]}] {s[1]}\n"
        info += "\n"

    await message.answer(
        f"{info}➕ <b>Yangi namuna qo'shish</b>\n\nNamuna qo'shiqning <b>nomini</b> kiriting:",
        parse_mode="HTML"
    )
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
    await message.answer(
        "🎵 Endi namuna <b>audio faylini</b> yuboring.\n"
        "Yoki audio yo'q bo'lsa, <b>/skip</b> yozing:",
        parse_mode="HTML"
    )
    await state.set_state(AdminActions.waiting_for_sample_file)


@dp.message(AdminActions.waiting_for_sample_file)
async def add_sample_file(message: Message, state: FSMContext):
    data = await state.get_data()
    title = data.get("sample_title", "Nomsiz")
    desc = data.get("sample_desc", "")
    file_id = None

    if message.audio:
        file_id = message.audio.file_id
    elif message.voice:
        file_id = message.voice.file_id
    elif message.document:
        file_id = message.document.file_id
    elif message.text == "/skip":
        file_id = None
    else:
        await message.answer("Audio fayl yuboring yoki /skip yozing:")
        return

    db_add_sample(title, desc, file_id)
    await message.answer(
        f"✅ Namuna muvaffaqiyatli qo'shildi!\n\n"
        f"🎵 <b>{title}</b>\n{desc}",
        parse_mode="HTML",
        reply_markup=get_admin_menu()
    )
    await state.clear()


async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
