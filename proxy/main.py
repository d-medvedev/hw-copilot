from fastapi import FastAPI, UploadFile, HTTPException
from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from openai import OpenAI
import requests
import os
import logging
import tempfile
from typing import Optional
import json

load_dotenv()
# OpenAI client для транскрибации
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
# DeepSeek конфигурация
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", 500))
MODEL = os.getenv("MODEL", "deepseek-chat")

SYSTEM_PROMPT = (
    "Ты — опытный инженер-электронщик, специализирующийся на анализе электронных схем по их netlist-представлению.",
    "Твоя задача — находить ошибки и потенциальные проблемы в схеме, представленной в виде netlist (например, в SPICE- или псевдо-SPICE-формате).",
    "Анализируй только то, что явно указано в netlist-е. Не делай предположений о компонентах, которые не описаны.",
    "Проверяй: корректность подключения компонентов, соответствие номиналов, наличие обязательных элементов, правильность полярности, замыкания, непрерывность питания и заземления.",
    "Если схема корректна, кратко объясни, почему она считается рабочей.",
    "Не пиши лишнего. Ответ должен быть кратким, но технически точным.",
    f"Формат: 1. [Ошибка] — [Объяснение] — [Как исправить]. Максимум 3 ошибки. Ответ не должен превышать {MAX_TOKENS} токенов.",
    "Отвечай строго на русском языке."
)

app = FastAPI()
logger = logging.getLogger("uvicorn")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене заменить на конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class GPTRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=1000)
    image_base64: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "prompt": "Проанализируй эту схему и найди потенциальные проблемы",
                "image_base64": "base64_encoded_image_string"
            }
        }
    }

@app.get("/health")
async def health_check():
    return {"status": "ok", "model": MODEL}

@app.post("/ask")
async def ask_gpt(req: GPTRequest):
    try:
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }

        # Формируем сообщения для API
        messages = [
            {"role": "system", "content": "\n".join(SYSTEM_PROMPT)},
            {"role": "user", "content": req.prompt}
        ]

        # Если есть изображение, добавляем его в контекст
        if req.image_base64:
            messages[1]["content"] = [
                {"type": "text", "text": req.prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{req.image_base64}",
                        "detail": "high"
                    }
                }
            ]

        # Формируем запрос к DeepSeek API
        payload = {
            "model": MODEL,
            "messages": messages,
            "max_tokens": MAX_TOKENS,
            "temperature": 0.7,
            "stream": False,
            "top_p": 0.95,
            "frequency_penalty": 0,
            "presence_penalty": 0
        }

        # Отправляем запрос к API
        response = requests.post(
            f"{DEEPSEEK_API_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30  # таймаут 30 секунд
        )
        
        # Проверяем ответ
        response.raise_for_status()
        result = response.json()
        
        if "choices" not in result or not result["choices"]:
            raise HTTPException(status_code=500, detail="Неожиданный формат ответа от API")
        
        return {"reply": result["choices"][0]["message"]["content"]}
    except requests.exceptions.Timeout:
        logger.error("Timeout при запросе к DeepSeek API")
        raise HTTPException(status_code=504, detail="Превышено время ожидания ответа от API")
    except requests.exceptions.RequestException as e:
        logger.error(f"DeepSeek API error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
