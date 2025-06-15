import streamlit as st
import requests
import base64
from PIL import Image
import io
import os
from dotenv import load_dotenv
import time
import json

load_dotenv()

# Configure the page
st.set_page_config(
    page_title="Анализатор электронных схем",
    page_icon="🔌",
    layout="wide"
)

# Title and description
st.title("🔌 Анализатор электронных схем")
st.markdown("""
Этот инструмент поможет вам проанализировать электронные схемы и найти потенциальные проблемы.
""")

# API Configuration
with st.sidebar:
    st.subheader("Настройки API")
    base_url = os.getenv("API_URL", "http://proxy:8000")
    timeout = st.number_input(
        "Таймаут запроса (сек)",
        min_value=1,
        max_value=60,
        value=30,
        help="Максимальное время ожидания ответа от API"
    )

# Initialize session state for chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Create two columns for the layout
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📝 Введите netlist")
    # Текстовое поле для ввода netlist
    netlist = st.text_area(
        "Вставьте netlist вашей схемы:",
        height=300,
        placeholder="Например:\nR1 1 2 1k\nR2 2 3 2k\n..."
    )
    
    # Опциональная загрузка изображения
    st.subheader("🖼️ Изображение схемы (опционально)")
    uploaded_file = st.file_uploader(
        "Загрузите изображение схемы (если есть):",
        type=['png', 'jpg', 'jpeg'],
        help="Изображение поможет в анализе схемы"
    )

with col2:
    st.subheader("❓ Задайте вопрос")
    # Текстовое поле для вопроса
    question = st.text_area(
        "Введите ваш вопрос о схеме:",
        height=100,
        placeholder="Например: Проанализируй схему и найди ошибки"
    )
    
    # Кнопка для отправки запроса
    if st.button("🔍 Анализировать", type="primary"):
        if not netlist:
            st.error("Пожалуйста, введите netlist схемы")
        elif not question:
            st.error("Пожалуйста, задайте вопрос о схеме")
        else:
            try:
                # Подготовка данных для запроса
                data = {
                    "prompt": f"Netlist схемы:\n{netlist}\n\nВопрос: {question}"
                }
                
                # Если есть изображение, добавляем его
                if uploaded_file is not None:
                    image = Image.open(uploaded_file)
                    # Конвертируем изображение в base64
                    buffered = io.BytesIO()
                    image.save(buffered, format="PNG")
                    img_str = base64.b64encode(buffered.getvalue()).decode()
                    data["image_base64"] = img_str
                
                # Отправка запроса к API
                with st.spinner("Анализируем схему..."):
                    # Добавляем отладочную информацию
                    st.sidebar.write(f"Отправка запроса на: {base_url}/ask")
                    st.sidebar.write("Данные запроса:", data)
                    
                    response = requests.post(
                        f"{base_url}/ask",
                        json=data,
                        timeout=timeout
                    )
                    
                    # Добавляем отладочную информацию
                    st.sidebar.write(f"Статус ответа: {response.status_code}")
                    st.sidebar.write("Ответ:", response.text)
                    
                    if response.status_code == 200:
                        result = response.json()
                        st.success("Анализ завершен!")
                        st.markdown("### 📊 Результаты анализа")
                        st.markdown(result["reply"])
                    else:
                        st.error(f"Ошибка при анализе схемы: {response.text}")
            
            except Exception as e:
                st.error(f"Произошла ошибка: {str(e)}")

# Display chat history
st.subheader("История общения")
for message in st.session_state.messages:
    if message["role"] == "user":
        st.write("👤 Вы:", message["content"])
    else:
        st.write("🤖 Ассистент:", message["content"])

# Добавляем информацию о здоровье API
try:
    health = requests.get(f"{base_url}/health")
    if health.status_code == 200:
        st.sidebar.success("✅ API доступен")
        st.sidebar.info(f"Используется модель: {health.json()['model']}")
    else:
        st.sidebar.error("❌ API недоступен")
except:
    st.sidebar.error("❌ API недоступен") 