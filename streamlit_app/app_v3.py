import streamlit as st
import requests
import base64
from PIL import Image
import io
import os
# from dotenv import load_dotenv  # Отключено из-за проблем
import json
from pathlib import Path
import tempfile
import uuid
from typing import Dict, List, Optional
import time
# Check dependencies without Streamlit calls
try:
    import fitz  # PyMuPDF для работы с PDF
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

# Отключаем загрузку .env из-за проблем с рекурсией
ENV_LOADED = False
ENV_ERROR = "Загрузка .env отключена из-за проблем совместимости"

# Configure the page FIRST
st.set_page_config(
    page_title="Анализатор электронных схем v3.0",
    page_icon="🔌",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Show warnings after page config
if not PDF_SUPPORT:
    st.warning("⚠️ PyMuPDF не установлен. PDF просмотр недоступен.")

if not ENV_LOADED:
    st.warning(f"Не удалось загрузить .env файл: {ENV_ERROR}")
    # Продолжаем работу без .env

# Custom CSS for professional layout
st.markdown("""
<style>
    /* Общие стили */
    .main-container {
        padding: 0;
    }
    
    /* Заголовок */
    .main-header {
        background: linear-gradient(90deg, #1f4e79, #2e7d32);
        color: white;
        padding: 1rem;
        margin: -1rem -1rem 1rem -1rem;
        text-align: center;
        border-radius: 0 0 10px 10px;
    }
    
    /* Левая панель - дерево проектов */
    .project-tree {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 1rem;
        height: 70vh;
        overflow-y: auto;
    }
    
    .project-folder {
        background-color: #e3f2fd;
        border: 1px solid #bbdefb;
        border-radius: 6px;
        padding: 0.5rem;
        margin: 0.5rem 0;
        cursor: pointer;
        transition: all 0.2s;
    }
    
    .project-folder:hover {
        background-color: #bbdefb;
        transform: translateX(2px);
    }
    
    .project-folder.selected {
        background-color: #2196f3;
        color: white;
        border-color: #1976d2;
    }
    
    .file-item {
        background-color: #f5f5f5;
        border: 1px solid #e0e0e0;
        border-radius: 4px;
        padding: 0.3rem 0.5rem;
        margin: 0.2rem 0 0.2rem 1rem;
        font-size: 0.9em;
        cursor: pointer;
        transition: all 0.2s;
    }
    
    .file-item:hover {
        background-color: #e0e0e0;
        transform: translateX(2px);
    }
    
    .file-item.selected {
        background-color: #4caf50;
        color: white;
        border-color: #388e3c;
    }
    
    /* Центральная область - схема */
    .schema-viewer {
        background-color: #fafafa;
        border: 2px dashed #ccc;
        border-radius: 8px;
        padding: 2rem;
        text-align: center;
        min-height: 60vh;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    
    .schema-viewer.has-content {
        border: 2px solid #4caf50;
        background-color: white;
    }
    
    /* Правая панель - чат */
    .chat-container {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 1rem;
        height: 70vh;
        display: flex;
        flex-direction: column;
    }
    
    .chat-messages {
        flex-grow: 1;
        overflow-y: auto;
        margin-bottom: 1rem;
        padding: 0.5rem;
        background-color: white;
        border-radius: 6px;
        border: 1px solid #e0e0e0;
    }
    
    .chat-message {
        margin: 0.5rem 0;
        padding: 0.5rem;
        border-radius: 6px;
    }
    
    .chat-message.user {
        background-color: #e3f2fd;
        margin-left: 2rem;
    }
    
    .chat-message.assistant {
        background-color: #f1f8e9;
        margin-right: 2rem;
    }
    
    /* Нижняя консоль */
    .console-container {
        background-color: #1e1e1e;
        color: #00ff00;
        border-radius: 8px;
        padding: 1rem;
        font-family: 'Courier New', monospace;
        font-size: 0.9em;
        max-height: 200px;
        overflow-y: auto;
        margin-top: 1rem;
    }
    
    /* Кнопка анализа */
    .analyze-button {
        background: linear-gradient(45deg, #ff6b6b, #4ecdc4);
        color: white;
        border: none;
        padding: 0.75rem 2rem;
        border-radius: 25px;
        font-size: 1.1em;
        font-weight: bold;
        cursor: pointer;
        transition: all 0.3s;
        margin: 1rem 0;
    }
    
    .analyze-button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }
    
    /* Файловые иконки */
    .file-icon {
        margin-right: 0.5rem;
    }
    
    .netlist-icon::before { content: "📄"; }
    .requirements-icon::before { content: "📋"; }
    .bom-icon::before { content: "📊"; }
    .pdf-icon::before { content: "📕"; }
    
    /* Статусы */
    .status-ok { color: #4caf50; }
    .status-error { color: #f44336; }
    .status-warning { color: #ff9800; }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if "projects" not in st.session_state:
    st.session_state.projects = {}
if "current_project" not in st.session_state:
    st.session_state.current_project = None
if "selected_file" not in st.session_state:
    st.session_state.selected_file = None
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "console_log" not in st.session_state:
    st.session_state.console_log = ["🔌 Анализатор схем v3.0 запущен", "Готов к работе..."]

def add_console_log(message: str, level: str = "info"):
    """Добавить сообщение в консоль"""
    timestamp = time.strftime("%H:%M:%S")
    if level == "error":
        log_entry = f"[{timestamp}] ❌ {message}"
    elif level == "warning":
        log_entry = f"[{timestamp}] ⚠️ {message}"
    elif level == "success":
        log_entry = f"[{timestamp}] ✅ {message}"
    else:
        log_entry = f"[{timestamp}] ℹ️ {message}"
    
    st.session_state.console_log.append(log_entry)
    if len(st.session_state.console_log) > 50:  # Ограничиваем размер лога
        st.session_state.console_log.pop(0)

def create_project(name: str):
    """Создать новый проект"""
    project_id = str(uuid.uuid4())
    st.session_state.projects[project_id] = {
        "name": name,
        "files": {},
        "created_at": time.time()
    }
    st.session_state.current_project = project_id
    add_console_log(f"Создан проект: {name}", "success")
    return project_id

def add_file_to_project(project_id: str, file_type: str, file_content, filename: str):
    """Добавить файл в проект"""
    if project_id in st.session_state.projects:
        st.session_state.projects[project_id]["files"][file_type] = {
            "content": file_content,
            "filename": filename,
            "uploaded_at": time.time()
        }
        add_console_log(f"Добавлен файл {file_type}: {filename}", "success")

def render_pdf_preview(pdf_content):
    """Отобразить превью PDF"""
    if not PDF_SUPPORT:
        st.error("PDF просмотр недоступен. Установите PyMuPDF: pip install PyMuPDF")
        return
        
    try:
        # Сохраняем PDF во временный файл
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(pdf_content)
            tmp_path = tmp_file.name
        
        # Открываем PDF с помощью PyMuPDF
        doc = fitz.open(tmp_path)
        page = doc[0]  # Первая страница
        
        # Конвертируем в изображение
        mat = fitz.Matrix(2.0, 2.0)  # Увеличиваем разрешение
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")
        
        # Отображаем изображение
        st.image(img_data, use_column_width=True)
        
        doc.close()
        os.unlink(tmp_path)  # Удаляем временный файл
        
    except Exception as e:
        st.error(f"Ошибка при отображении PDF: {str(e)}")
        st.info("Попробуйте переустановить PyMuPDF: pip uninstall PyMuPDF -y && pip install PyMuPDF")

# Main header
st.markdown("""
<div class="main-header">
    <h1>🔌 Анализатор электронных схем v3.0</h1>
    <p>Интеллектуальный анализ схем с поддержкой проектов</p>
</div>
""", unsafe_allow_html=True)

# Main layout: 4 columns
col_left, col_center, col_right = st.columns([2, 4, 2])

# ========== ЛЕВАЯ ПАНЕЛЬ: ДЕРЕВО ПРОЕКТОВ ==========
with col_left:
    st.markdown("### 📁 Проекты")
    
    # Создание нового проекта
    with st.expander("➕ Создать проект", expanded=False):
        new_project_name = st.text_input("Название проекта")
        if st.button("Создать") and new_project_name:
            create_project(new_project_name)
            st.rerun()
    
    # Отображение существующих проектов
    if st.session_state.projects:
        for project_id, project_data in st.session_state.projects.items():
            # Папка проекта
            is_selected = st.session_state.current_project == project_id
            folder_class = "project-folder selected" if is_selected else "project-folder"
            
            if st.button(f"📁 {project_data['name']}", key=f"project_{project_id}"):
                st.session_state.current_project = project_id
                st.session_state.selected_file = None
                add_console_log(f"Выбран проект: {project_data['name']}")
                st.rerun()
            
            # Файлы в проекте (если проект выбран)
            if is_selected:
                files = project_data.get("files", {})
                
                # Загрузка файлов
                st.markdown("**Загрузить файлы:**")
                
                # Netlist
                netlist_file = st.file_uploader("📄 Netlist", type=['txt', 'net', 'cir'], key="netlist_upload")
                if netlist_file:
                    content = netlist_file.read().decode('utf-8')
                    add_file_to_project(project_id, "netlist", content, netlist_file.name)
                    st.rerun()
                
                # Requirements
                req_file = st.file_uploader("📋 Требования", type=['txt', 'md'], key="req_upload")
                if req_file:
                    content = req_file.read().decode('utf-8')
                    add_file_to_project(project_id, "requirements", content, req_file.name)
                    st.rerun()
                
                # BOM
                bom_file = st.file_uploader("📊 Спецификация", type=['csv', 'xlsx', 'txt'], key="bom_upload")
                if bom_file:
                    content = bom_file.read()
                    add_file_to_project(project_id, "bom", content, bom_file.name)
                    st.rerun()
                
                # PDF схема
                pdf_file = st.file_uploader("📕 PDF схемы", type=['pdf'], key="pdf_upload")
                if pdf_file:
                    try:
                        content = pdf_file.read()
                        add_file_to_project(project_id, "pdf", content, pdf_file.name)
                        add_console_log(f"PDF файл загружен: {pdf_file.name} ({len(content)} байт)", "success")
                        st.rerun()
                    except Exception as e:
                        add_console_log(f"Ошибка загрузки PDF: {str(e)}", "error")
                        st.error(f"Ошибка при загрузке PDF: {str(e)}")
                
                st.markdown("---")
                st.markdown("**Файлы проекта:**")
                
                # Отображение загруженных файлов
                for file_type, file_data in files.items():
                    icon_class = f"{file_type}-icon"
                    is_file_selected = st.session_state.selected_file == (project_id, file_type)
                    
                    if st.button(
                        f"{file_data['filename']}", 
                        key=f"file_{project_id}_{file_type}",
                        help=f"Тип: {file_type}"
                    ):
                        st.session_state.selected_file = (project_id, file_type)
                        add_console_log(f"Выбран файл: {file_data['filename']}")
                        st.rerun()
    else:
        st.info("Создайте первый проект для начала работы")

# ========== ЦЕНТРАЛЬНАЯ ОБЛАСТЬ: ПРОСМОТР СХЕМ ==========
with col_center:
    st.markdown("### 🖼️ Просмотр схемы")
    
    # Кнопка анализа
    if st.button("🚀 Запустить анализ", type="primary", use_container_width=True):
        if st.session_state.current_project:
            project = st.session_state.projects[st.session_state.current_project]
            files = project.get("files", {})
            
            if "netlist" in files:
                add_console_log("Запуск анализа схемы...", "info")
                # Здесь будет логика анализа
                add_console_log("Анализ завершен успешно", "success")
            else:
                add_console_log("Ошибка: Netlist не найден", "error")
                st.error("Загрузите netlist для анализа")
        else:
            add_console_log("Ошибка: Проект не выбран", "error")
            st.error("Выберите проект для анализа")
    
    # Отображение содержимого
    if st.session_state.selected_file:
        project_id, file_type = st.session_state.selected_file
        project = st.session_state.projects[project_id]
        file_data = project["files"][file_type]
        
        st.markdown(f"**Файл:** {file_data['filename']}")
        
        if file_type == "pdf":
            # Отображение PDF
            add_console_log(f"Отображение PDF: {file_data['filename']}", "info")
            render_pdf_preview(file_data["content"])
        elif file_type in ["netlist", "requirements"]:
            # Отображение текстовых файлов
            st.code(file_data["content"], language="text")
        elif file_type == "bom":
            # Отображение BOM (упрощенно)
            st.text("Содержимое спецификации:")
            st.text(str(file_data["content"][:500]) + "..." if len(str(file_data["content"])) > 500 else str(file_data["content"]))
    else:
        # Пустое состояние
        st.markdown("""
        <div class="schema-viewer">
            <div>
                <h3>📋 Выберите файл для просмотра</h3>
                <p>Загрузите PDF схемы или выберите другой файл из проекта</p>
            </div>
        </div>
        """, unsafe_allow_html=True)

# ========== ПРАВАЯ ПАНЕЛЬ: ЧАТ ==========
with col_right:
    st.markdown("### 💬 Чат с ассистентом")
    
    # Контейнер для сообщений
    chat_container = st.container()
    
    with chat_container:
        # Отображение истории чата
        for message in st.session_state.chat_messages:
            if message["role"] == "user":
                st.markdown(f"""
                <div class="chat-message user">
                    <strong>👤 Вы:</strong><br>
                    {message["content"]}
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="chat-message assistant">
                    <strong>🤖 Ассистент:</strong><br>
                    {message["content"]}
                </div>
                """, unsafe_allow_html=True)
    
    # Поле ввода сообщения
    user_message = st.text_area(
        "Задайте вопрос:",
        placeholder="Например: Проанализируй схему на ошибки",
        height=100,
        key="chat_input"
    )
    
    if st.button("Отправить", type="secondary", use_container_width=True):
        if user_message and st.session_state.current_project:
            # Добавляем сообщение пользователя
            st.session_state.chat_messages.append({
                "role": "user",
                "content": user_message
            })
            
            # Имитация ответа ассистента (здесь будет интеграция с LLM)
            assistant_response = f"Получен ваш запрос: '{user_message}'. Анализирую схему из проекта '{st.session_state.projects[st.session_state.current_project]['name']}'..."
            
            st.session_state.chat_messages.append({
                "role": "assistant", 
                "content": assistant_response
            })
            
            add_console_log(f"Новое сообщение в чате: {user_message[:50]}...")
            st.rerun()

# ========== НИЖНЯЯ КОНСОЛЬ ==========
st.markdown("### 🖥️ Консоль")
console_content = "\n".join(st.session_state.console_log[-10:])  # Последние 10 сообщений
st.markdown(f"""
<div class="console-container">
{console_content.replace(chr(10), '<br>')}
</div>
""", unsafe_allow_html=True)

# Статус API
with st.sidebar:
    st.markdown("### ⚙️ Статус системы")
    try:
        # Здесь будет проверка API
        st.success("✅ Система готова")
        st.info("🤖 LLM: GPT-4o")
        st.info(f"📁 Проектов: {len(st.session_state.projects)}")
    except:
        st.error("❌ Ошибка подключения")
