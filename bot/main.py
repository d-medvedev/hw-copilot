### bot/main.py
from aiogram import Bot, Dispatcher, types
from aiogram.types import ContentType, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from dotenv import load_dotenv
import os
import aiohttp
import base64

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
PROXY_API_URL = os.getenv("PROXY_API_URL", "http://localhost:8000")
BOT_VERSION = os.getenv("BOT_VERSION", "0.2")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=["start"])
async def handle_start(message: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(text="🌱 Уход за томатами", callback_data="tomatoes"),
        InlineKeyboardButton(text="🐛 Вредители растений", callback_data="pests"),
        InlineKeyboardButton(text="💧 Когда поливать?", callback_data="watering")
    )
    await message.reply(f"Привет! Я агробот 🤖 v{BOT_VERSION}\nЗадай вопрос или выбери готовый:", reply_markup=keyboard)

@dp.callback_query_handler()
async def handle_callback(callback_query: types.CallbackQuery):
    prompts = {
        "tomatoes": "Как ухаживать за томатами в открытом грунте?",
        "pests": "Какие признаки появления вредителей на листьях?",
        "watering": "Как часто нужно поливать огурцы летом?"
    }
    prompt = prompts.get(callback_query.data)
    if prompt:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{PROXY_API_URL}/ask", json={"prompt": prompt}) as result:
                data = await result.json()
                reply = data.get("reply", "Ошибка при обработке запроса")
                await callback_query.message.answer(reply)
    await callback_query.answer()

@dp.message_handler(content_types=ContentType.TEXT)
async def handle_text(message: types.Message):
    prompt = message.text
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{PROXY_API_URL}/ask", json={"prompt": prompt}) as result:
            data = await result.json()
            reply = data.get("reply", "Ошибка при обработке текста")
            await message.reply(reply)

@dp.message_handler(content_types=ContentType.PHOTO)
async def handle_photo(message: types.Message):
    caption = message.caption or "Что изображено на фото?"
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_path = file.file_path
    photo_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"

    async with aiohttp.ClientSession() as session:
        async with session.get(photo_url) as resp:
            img_bytes = await resp.read()
            img_b64 = base64.b64encode(img_bytes).decode()

        payload = {"prompt": caption, "image_base64": img_b64}
        async with session.post(f"{PROXY_API_URL}/ask", json=payload) as result:
            data = await result.json()
            reply = data.get("reply", "Ошибка при обработке изображения")
            await message.reply(reply)

@dp.message_handler(content_types=ContentType.VOICE)
async def handle_voice(message: types.Message):
    try:
        voice = message.voice
        file = await bot.get_file(voice.file_id)
        file_path = file.file_path
        voice_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"

        async with aiohttp.ClientSession() as session:
            async with session.get(voice_url) as resp:
                audio_bytes = await resp.read()

            form = aiohttp.FormData()
            form.add_field("file", audio_bytes, filename="voice.ogg", content_type="audio/ogg")
            async with session.post(f"{PROXY_API_URL}/transcribe", data=form) as result:
                data = await result.json()
                reply = data.get("reply", "Ошибка обработки аудио")
                await message.reply(reply)
    except Exception as e:
        await message.reply("Ошибка обработки голосового сообщения.")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
