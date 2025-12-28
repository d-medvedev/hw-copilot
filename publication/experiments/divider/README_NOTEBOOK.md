# Jupyter Notebook для Google Colab

## 📓 Файл: `voltage_divider_experiments_analysis.ipynb`

Этот notebook содержит визуализацию и анализ результатов экспериментов по анализу и синтезу схем делителей напряжения.

## 🚀 Использование в Google Colab

### Вариант 1: Загрузка из GitHub

1. Откройте [Google Colab](https://colab.research.google.com/)
2. File → Upload notebook
3. Загрузите файл `voltage_divider_experiments_analysis.ipynb`

### Вариант 2: Клонирование репозитория

```python
# В Colab выполните:
!git clone <your-repo-url>
%cd <repo-path>/publication/experiments/divider
```

### Вариант 3: Загрузка данных вручную

1. Запустите notebook в Colab
2. Создайте папку `/content/results/`:
   ```python
   !mkdir -p /content/results/models_comparison
   !mkdir -p /content/results/synthesis
   ```
3. Загрузите файлы через Files → Upload:
   - `results/models_comparison/comparison_report.json`
   - `results/synthesis/comparison_report.json`

## 📊 Что содержит notebook

### Часть 1: Анализ схем
- Загрузка и подготовка данных
- Визуализация метрик (Precision, Recall, F1-Score)
- Сравнение моделей
- Precision-Recall scatter plot
- Сравнение коммерческих и open-source моделей

### Часть 2: Синтез схем
- Метрики синтеза (Success Rate, Calculation Accuracy, Requirements Compliance)
- Визуализация результатов синтеза
- Сравнение анализа и синтеза

### Выводы
- Сводные таблицы результатов
- Ключевые наблюдения
- Дополнительная информация о типах ошибок

## 🔧 Зависимости

Notebook автоматически устанавливает:
- `matplotlib` - для графиков
- `seaborn` - для стилизации
- `pandas` - для работы с данными
- `numpy` - для вычислений

## 📈 Примеры визуализаций

1. **График 1**: Сравнение Precision, Recall, F1-Score по моделям
2. **График 2**: Precision-Recall scatter plot
3. **График 3**: Сравнение групп моделей (Commercial vs Open Source)
4. **График 4**: Метрики синтеза (4 подграфика)
5. **График 5**: Сравнение анализа и синтеза (если есть общие модели)

## 💡 Советы по использованию

1. **Если нет реальных данных**: Notebook использует примеры данных для демонстрации
2. **Для реальных данных**: Загрузите JSON файлы результатов в Colab
3. **Экспорт графиков**: Используйте `plt.savefig()` для сохранения графиков
4. **Настройка стиля**: Измените параметры в ячейке с настройкой стиля

## 📝 Структура данных

### Формат данных анализа:
```json
{
  "models": [
    {
      "model_config": {"name": "...", "group": "...", "size": "..."},
      "overall_metrics": {"precision": 0.85, "recall": 0.85, "f1_score": 0.85}
    }
  ]
}
```

### Формат данных синтеза:
```json
{
  "models": [
    {
      "model_config": {"name": "...", "group": "...", "size": "..."},
      "overall_metrics": {
        "success_rate": 1.0,
        "calculation_accuracy": 1.0,
        "requirements_compliance": 0.27,
        "error_rate": 0.0
      }
    }
  ]
}
```

## 🎯 Демонстрация результатов

Notebook готов для:
- Презентации результатов исследования
- Сравнения производительности моделей
- Визуализации метрик качества
- Обсуждения выводов и наблюдений

## 🔄 Обновление данных

Для обновления данных:
1. Запустите эксперименты заново
2. Обновите JSON файлы результатов
3. Перезагрузите данные в notebook
4. Перезапустите ячейки визуализации




