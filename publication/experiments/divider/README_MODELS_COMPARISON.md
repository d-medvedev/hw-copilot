# Сравнение моделей LLM для анализа схем

## Настройка

### 1. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 2. Настройка API ключей

Создайте файл `.env` в корне проекта или в папке `divider`:
```bash
OPENAI_API_KEY=your_openai_key_here
OPENROUTER_API_KEY=your_openrouter_key_here
```

### 3. Конфигурация моделей

Файл `models_config.json` содержит список моделей для тестирования:

```json
{
  "models": [
    {
      "name": "GPT-4o",
      "provider": "openrouter",
      "model_id": "openai/gpt-4o",
      "group": "commercial",
      "size": "large",
      "api_key_env": "OPENROUTER_API_KEY"
    }
  ]
}
```

## Запуск эксперимента

### Режим одной модели (обратная совместимость)
```bash
python voltage_divider_experiment_v4.py
```

### Режим сравнения нескольких моделей
```bash
python voltage_divider_experiment_v4.py
```
(автоматически определяет режим по наличию `models_config.json`)

## Результаты

### Структура результатов:
```
results/
  models_comparison/
    ├── gpt-4o/
    │   ├── error_detection_results.json  # Полные ответы модели
    │   └── error_detection_metrics.json   # Метрики
    ├── claude-3.5-sonnet/
    │   ├── error_detection_results.json
    │   └── error_detection_metrics.json
    ├── comparison_table.txt               # Сравнительная таблица
    └── comparison_report.json            # Сравнительный отчет
```

### Формат сравнительной таблицы:

```
СРАВНИТЕЛЬНАЯ ТАБЛИЦА РЕЗУЛЬТАТОВ МОДЕЛЕЙ
Модель                   Группа          Размер     Precision    Recall       F1-score     TP     FP     FN
GPT-4o                   commercial       large      0.84         0.80         0.82         16     3     4
Claude 3.5 Sonnet        commercial       large      0.85         0.82         0.83         17     3     3
...
```

## Добавление новых моделей

Отредактируйте `models_config.json` и добавьте новую модель:

```json
{
  "name": "Название модели",
  "provider": "openrouter",
  "model_id": "provider/model-name",
  "group": "commercial|opensource",
  "size": "small|large",
  "api_key_env": "OPENROUTER_API_KEY"
}
```

## Поддерживаемые провайдеры

- **openai**: OpenAI API (прямой доступ)
- **openrouter**: OpenRouter API (доступ к множеству моделей)

## Примечания

- Некоторые модели могут не поддерживать structured output (json_schema)
- В этом случае код автоматически переключается на обычный JSON парсинг
- Полные ответы всех моделей сохраняются для детального анализа

