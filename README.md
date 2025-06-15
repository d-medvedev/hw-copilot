# Circuit Analysis Assistant

Веб-приложение для анализа принципиальных схем с использованием AI. Помогает находить ошибки в схемах и объясняет их работу.

## Установка

### Локальная установка

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Создайте файл `.env` со следующими переменными:
```
OPENAI_API_KEY=your_api_key_here
API_URL=http://localhost:8000
```

### Запуск через Docker

1. Создайте файл `.env` в корневой директории проекта:
```
OPENAI_API_KEY=your_api_key_here
GPT_MODEL=gpt-4-turbo
MAX_TOKENS=500
```

2. Запустите сервисы через Docker Compose:
```bash
docker-compose up --build
```

Приложение будет доступно по адресу http://localhost:8501

## Запуск вручную

1. Запустите API сервер:
```bash
cd proxy
uvicorn main:app --reload
```

2. В отдельном терминале запустите Streamlit приложение:
```bash
cd streamlit_app
streamlit run app.py
```

## Структура проекта

- `proxy/` - FastAPI сервер для обработки запросов к OpenAI API
- `streamlit_app/` - Streamlit интерфейс для взаимодействия с пользователем
- `requirements.txt` - зависимости Python
- `Dockerfile` - конфигурация Docker для обоих сервисов
- `docker-compose.yml` - конфигурация для запуска через Docker Compose
