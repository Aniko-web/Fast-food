import asyncio
import logging
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import sqlite3
from datetime import datetime

# Logging sozlamalari
logging.basicConfig(level=logging.INFO)

# Bot tokenini kiriting
BOT_TOKEN = "8415377244:AAEO5bHjGqAKSgi4DK6vn1zEqYkTwEFASY8"
ADMIN_ID = 6227963027  # Admin Telegram ID sini kiriting

# Bot va Dispatcher
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()


# FSM States - Buyurtma jarayoni uchun
class OrderStates(StatesGroup):
    waiting_for_contact = State()
    waiting_for_location = State()


# Ma'lumotlar bazasini yaratish
def init_db():
    conn = sqlite3.connect('fastfood.db')
    cur = conn.cursor()

    cur.execute('''CREATE TABLE IF NOT EXISTS products
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY,
                       name
                       TEXT,
                       category
                       TEXT,
                       price
                       INTEGER,
                       emoji
                       TEXT
                   )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS orders
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       user_id
                       INTEGER,
                       username
                       TEXT,
                       phone
                       TEXT,
                       items
                       TEXT,
                       total
                       INTEGER,
                       date
                       TEXT,
                       status
                       TEXT
                   )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS cart
    (
        user_id
        INTEGER,
        product_id
        INTEGER,
        quantity
        INTEGER,
        PRIMARY
        KEY
                   (
        user_id,
        product_id
                   )
        )''')

    # Eski jadvalga phone ustunini qo'shish (agar yo'q bo'lsa)
    try:
        cur.execute("ALTER TABLE orders ADD COLUMN phone TEXT")
        conn.commit()
        logging.info("Phone ustuni qo'shildi")
    except sqlite3.OperationalError:
        # Ustun allaqachon mavjud
        pass

    conn.commit()
    conn.close()


def seed_products():
    conn = sqlite3.connect('fastfood.db')
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM products")
    if cur.fetchone()[0] == 0:
        products = [
            (1, 'Burger', 'fastfood', 25000, '🍔'),
            (2, 'Hot Dog', 'fastfood', 18000, '🌭'),
            (3, 'Fri kartoshka', 'fastfood', 12000, '🍟'),
            (4, 'Lavash', 'fastfood', 22000, '🌯'),
            (5, 'Pepperoni', 'pizza', 45000, '🍕'),
            (6, 'Margarita', 'pizza', 40000, '🍕'),
            (7, 'Four Cheese', 'pizza', 50000, '🍕'),
            (8, 'Vegetarian', 'pizza', 42000, '🍕'),
            (9, 'Cola', 'drinks', 8000, '🥤'),
            (10, 'Fanta', 'drinks', 8000, '🥤'),
            (11, 'Sprite', 'drinks', 8000, '🥤'),
            (12, 'Suv', 'drinks', 3000, '💧')
        ]
        cur.executemany("INSERT INTO products VALUES (?,?,?,?,?)", products)
        conn.commit()

    conn.close()


def add_to_cart(user_id, product_id):
    conn = sqlite3.connect('fastfood.db')
    cur = conn.cursor()
    cur.execute("""INSERT INTO cart (user_id, product_id, quantity)
                   VALUES (?, ?, 1) ON CONFLICT(user_id, product_id) 
                   DO
    UPDATE SET quantity = quantity + 1""", (user_id, product_id))
    conn.commit()
    conn.close()


def get_cart(user_id):
    conn = sqlite3.connect('fastfood.db')
    cur = conn.cursor()
    cur.execute("""SELECT p.name, p.emoji, p.price, c.quantity
                   FROM cart c
                            JOIN products p ON c.product_id = p.id
                   WHERE c.user_id = ?""", (user_id,))
    items = cur.fetchall()
    conn.close()
    return items


def clear_cart(user_id):
    conn = sqlite3.connect('fastfood.db')
    cur = conn.cursor()
    cur.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_products_by_category(category):
    conn = sqlite3.connect('fastfood.db')
    cur = conn.cursor()
    cur.execute("SELECT id, name, emoji, price FROM products WHERE category = ?", (category,))
    products = cur.fetchall()
    conn.close()
    return products


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def main_menu_keyboard():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍔 Fast Food", callback_data="cat_fastfood")],
        [InlineKeyboardButton(text="🍕 Pitsa", callback_data="cat_pizza")],
        [InlineKeyboardButton(text="🥤 Ichimliklar", callback_data="cat_drinks")],
        [InlineKeyboardButton(text="🛒 Savatcha", callback_data="view_cart")]
    ])
    return kb


def products_keyboard(category):
    products = get_products_by_category(category)
    buttons = []
    for prod_id, name, emoji, price in products:
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} {name} - {price:,} so'm".replace(',', ' '),
            callback_data=f"add_{prod_id}"
        )])
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cart_keyboard():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="confirm_order")],
        [InlineKeyboardButton(text="❌ Tozalash", callback_data="clear_cart")],
        [InlineKeyboardButton(text="⬅️ Menyuga qaytish", callback_data="back_menu")]
    ])
    return kb


def contact_keyboard():
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return kb


def location_keyboard():
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Joylashuvni yuborish", request_location=True)],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return kb


# ============= ASOSIY KOMANDALAR =============

@router.message(Command("start"))
async def cmd_start(message: Message):
    user_name = message.from_user.first_name
    await message.answer(
        f"👋 Assalomu alaykum, {user_name}!\n"
        "FastFood botiga xush kelibsiz! 🍔\n\n"
        "🍕 Mazali taomlar buyurtma qiling va tez yetkazib beramiz 🚀\n\n"
        "Quyidagilardan birini tanlang 👇",
        reply_markup=main_menu_keyboard()
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    await message.answer(
        "📋 Menyu bo'limlari:\n\n"
        "Quyidagilardan birini tanlang 👇",
        reply_markup=main_menu_keyboard()
    )


@router.message(Command("cart"))
async def cmd_cart(message: Message):
    items = get_cart(message.from_user.id)
    if not items:
        await message.answer("🛒 Savatingiz bo'sh")
        return

    text = "🛍 Sizning buyurtmangiz:\n\n"
    total = 0
    for name, emoji, price, qty in items:
        item_total = price * qty
        total += item_total
        text += f"{emoji} {name} x{qty} — {item_total:,} so'm\n".replace(',', ' ')

    text += f"\n💰 Jami: {total:,} so'm".replace(',', ' ')
    await message.answer(text, reply_markup=cart_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        "📚 Botdan foydalanish yo'riqnomasi:\n\n"
        "/start - Botni ishga tushirish\n"
        "/menu - Mahsulotlar menyusi\n"
        "/cart - Savatchani ko'rish\n"
        "/help - Yordam\n\n"
    )

    if is_admin(message.from_user.id):
        help_text += (
            "🔐 Admin komandalar:\n"
            "/admin - Statistika\n"
            "/orders - Buyurtmalar ro'yxati\n\n"
        )

    help_text += "❓ Savollar bo'lsa, admin bilan bog'laning: @admin"
    await message.answer(help_text)


# ============= ADMIN PANEL =============

@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Sizda admin huquqlari yo'q!")
        return

    conn = sqlite3.connect('fastfood.db')
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM orders")
    total_orders = cur.fetchone()[0]

    cur.execute("SELECT SUM(total) FROM orders")
    total_revenue = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(DISTINCT user_id) FROM orders")
    total_users = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM orders WHERE status='yangi'")
    pending_orders = cur.fetchone()[0]

    conn.close()

    text = (
            "📊 *Admin Panel - Statistika*\n\n"
            f"📦 Jami buyurtmalar: {total_orders}\n"
            f"💰 Jami daromad: {total_revenue:,} so'm\n".replace(',', ' ') +
            f"👥 Foydalanuvchilar: {total_users}\n"
            f"🔄 Yangi buyurtmalar: {pending_orders}\n\n"
            "📋 Komandalar:\n"
            "/orders - Barcha buyurtmalar\n"
            "/admin - Statistikani yangilash"
    )

    await message.answer(text, parse_mode="Markdown")


@router.message(Command("orders"))
async def view_orders(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔️ Sizda admin huquqlari yo'q!")
        return

    conn = sqlite3.connect('fastfood.db')
    cur = conn.cursor()
    cur.execute("""SELECT id, username, phone, items, total, date, status
                   FROM orders
                   ORDER BY id DESC LIMIT 10""")
    orders = cur.fetchall()
    conn.close()

    if not orders:
        await message.answer("📦 Buyurtmalar yo'q")
        return

    text = "📦 So'ngi 10 ta buyurtma:\n\n"
    for order_id, username, phone, items, total, date, status in orders:
        status_emoji = "🔄" if status == "yangi" else "✅"
        text += (
            f"{status_emoji} #{order_id} - @{username}\n"
            f"   📱 {phone}\n"
            f"   {items}\n"
            f"   💰 {total:,} so'm | 📅 {date}\n\n".replace(',', ' ')
        )

    await message.answer(text)


# ============= CALLBACK HANDLERS =============

@router.callback_query(F.data.startswith("cat_"))
async def category_handler(callback: CallbackQuery):
    category = callback.data.split("_")[1]

    category_names = {
        'fastfood': '🍔 Fast Food',
        'pizza': '🍕 Pitsa',
        'drinks': '🥤 Ichimliklar'
    }

    await callback.message.edit_text(
        f"{category_names[category]} bo'limi:\n\n"
        "Mahsulotni tanlang 👇",
        reply_markup=products_keyboard(category)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("add_"))
async def add_product(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    add_to_cart(callback.from_user.id, product_id)

    conn = sqlite3.connect('fastfood.db')
    cur = conn.cursor()
    cur.execute("SELECT name, emoji FROM products WHERE id = ?", (product_id,))
    name, emoji = cur.fetchone()
    conn.close()

    await callback.answer(f"✅ {emoji} {name} savatchaga qo'shildi!", show_alert=True)


@router.callback_query(F.data == "view_cart")
async def view_cart(callback: CallbackQuery):
    items = get_cart(callback.from_user.id)
    if not items:
        await callback.message.edit_text(
            "🛒 Savatingiz bo'sh\n\n"
            "Mahsulot qo'shish uchun menyuga o'ting 👇",
            reply_markup=main_menu_keyboard()
        )
        return

    text = "🛍 Sizning buyurtmangiz:\n\n"
    total = 0
    for name, emoji, price, qty in items:
        item_total = price * qty
        total += item_total
        text += f"{emoji} {name} x{qty} — {item_total:,} so'm\n".replace(',', ' ')

    text += f"\n💰 Jami: {total:,} so'm".replace(',', ' ')
    await callback.message.edit_text(text, reply_markup=cart_keyboard())
    await callback.answer()


@router.callback_query(F.data == "clear_cart")
async def clear_cart_handler(callback: CallbackQuery):
    clear_cart(callback.from_user.id)
    await callback.message.edit_text(
        "🗑 Savatcha tozalandi!\n\n"
        "Menyuga qaytish uchun tugmani bosing 👇",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer("Savatcha tozalandi!")


@router.callback_query(F.data == "confirm_order")
async def confirm_order_handler(callback: CallbackQuery, state: FSMContext):
    items = get_cart(callback.from_user.id)
    if not items:
        await callback.answer("Savatcha bo'sh!", show_alert=True)
        return

    # Buyurtma ma'lumotlarini state ga saqlash
    await state.update_data(order_items=items)
    await state.set_state(OrderStates.waiting_for_contact)

    await callback.message.answer(
        "📱 Iltimos, telefon raqamingizni yuboring\n\n"
        "Quyidagi tugmani bosing yoki raqamni qo'lda kiriting\n"
        "(masalan: +998901234567)",
        reply_markup=contact_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "back_menu")
async def back_to_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "📋 Asosiy menyu:\n\n"
        "Quyidagilardan birini tanlang 👇",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()


# ============= CONTACT VA LOCATION HANDLERS =============

@router.message(OrderStates.waiting_for_contact, F.contact)
async def process_contact(message: Message, state: FSMContext):
    phone = message.contact.phone_number

    # Telefon raqamni state ga saqlash
    await state.update_data(phone=phone)
    await state.set_state(OrderStates.waiting_for_location)

    await message.answer(
        f"✅ Telefon raqam qabul qilindi: {phone}\n\n"
        "📍 Endi yetkazib berish manzilini yuboring:",
        reply_markup=location_keyboard()
    )


@router.message(OrderStates.waiting_for_contact, F.text)
async def process_phone_text(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer(
            "❌ Bekor qilindi\n\n"
            "Menyuga qaytish uchun /menu ni bosing",
            reply_markup=main_menu_keyboard()
        )
        return

    # Telefon raqamni tekshirish (oddiy format)
    phone = message.text.strip()
    if len(phone) < 9:
        await message.answer(
            "❌ Noto'g'ri format!\n\n"
            "Iltimos, to'g'ri telefon raqam kiriting\n"
            "(masalan: +998901234567)",
            reply_markup=contact_keyboard()
        )
        return

    # Telefon raqamni state ga saqlash
    await state.update_data(phone=phone)
    await state.set_state(OrderStates.waiting_for_location)

    await message.answer(
        f"✅ Telefon raqam qabul qilindi: {phone}\n\n"
        "📍 Endi yetkazib berish manzilini yuboring:",
        reply_markup=location_keyboard()
    )


@router.message(OrderStates.waiting_for_location, F.location)
async def process_location(message: Message, state: FSMContext):
    data = await state.get_data()
    items = data.get('order_items', [])
    phone = data.get('phone', 'Kiritilmagan')

    if not items:
        await message.answer(
            "❌ Buyurtma topilmadi. Qaytadan boshlang.",
            reply_markup=main_menu_keyboard()
        )
        await state.clear()
        return

    location = message.location

    order_text = "🛍 Buyurtma:\n\n"
    total = 0
    items_list = []

    for name, emoji, price, qty in items:
        item_total = price * qty
        total += item_total
        order_text += f"{emoji} {name} x{qty} — {item_total:,} so'm\n".replace(',', ' ')
        items_list.append(f"{name} x{qty}")

    order_text += f"\n💰 Jami: {total:,} so'm".replace(',', ' ')

    # Ma'lumotlar bazasiga saqlash
    conn = sqlite3.connect('fastfood.db')
    cur = conn.cursor()
    cur.execute("""INSERT INTO orders (user_id, username, phone, items, total, date, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (message.from_user.id,
                 message.from_user.username or "Noma'lum",
                 phone,
                 ", ".join(items_list),
                 total,
                 datetime.now().strftime("%Y-%m-%d %H:%M"),
                 "yangi"))
    order_id = cur.lastrowid
    conn.commit()
    conn.close()

    # Foydalanuvchiga xabar
    await message.answer(
        "✅ Buyurtmangiz qabul qilindi! 🎉\n"
        "⏰ Operator tez orada siz bilan bog'lanadi.\n\n"
        f"📦 Buyurtma raqami: #{order_id}\n"
        f"{order_text}",
        reply_markup=main_menu_keyboard()
    )

    # Adminga xabar yuborish
    try:
        admin_text = (
            "🔔 YANGI BUYURTMA!\n\n"
            f"📦 Buyurtma #{order_id}\n"
            f"👤 @{message.from_user.username or 'Noma\'lum'}\n"
            f"🆔 ID: {message.from_user.id}\n"
            f"📱 Tel: {phone}\n\n"
            f"{order_text}"
        )
        await bot.send_message(ADMIN_ID, admin_text)
        await bot.send_location(ADMIN_ID, location.latitude, location.longitude)
        logging.info(f"Buyurtma #{order_id} adminga yuborildi")
    except Exception as e:
        logging.error(f"Adminga xabar yuborishda xatolik: {e}")

    clear_cart(message.from_user.id)
    await state.clear()


@router.message(OrderStates.waiting_for_location, F.text == "❌ Bekor qilish")
async def cancel_order(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ Bekor qilindi\n\n"
        "Menyuga qaytish uchun /menu ni bosing",
        reply_markup=main_menu_keyboard()
    )


@router.message(F.text)
async def search_products(message: Message):
    if message.text.startswith('/'):
        return

    query = message.text.lower()
    conn = sqlite3.connect('fastfood.db')
    cur = conn.cursor()
    cur.execute("SELECT name, emoji, price FROM products WHERE LOWER(name) LIKE ?",
                (f'%{query}%',))
    results = cur.fetchall()
    conn.close()

    if not results:
        await message.answer(
            "🔍 Hech narsa topilmadi.\n"
            "Menyuga o'tish uchun /menu ni bosing"
        )
        return

    text = f"🔍 '{query}' bo'yicha natijalar:\n\n"
    for name, emoji, price in results:
        text += f"{emoji} {name} — {price:,} so'm\n".replace(',', ' ')

    await message.answer(text, reply_markup=main_menu_keyboard())


# ============= ASOSIY FUNKSIYA =============

async def main():
    print("Bot ishladi...✅")
    init_db()
    seed_products()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
