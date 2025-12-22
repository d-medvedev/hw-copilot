#!/usr/bin/env python3
"""
Скрипт для запуска эксперимента для одной модели
"""

import json
import sys
from pathlib import Path
from voltage_divider_experiment_v4 import (
    load_models_config,
    run_experiment_for_model,
    create_test_cases,
    generate_comparison_table
)

def main():
    """Запуск эксперимента для одной модели"""
    
    if len(sys.argv) < 2:
        print("Использование: python run_single_model.py <model_name>")
        print("\nДоступные модели:")
        models = load_models_config()
        for m in models:
            print(f"  - {m['name']}")
        return
    
    target_model_name = sys.argv[1]
    
    print(f"🔬 Запуск эксперимента для модели: {target_model_name}")
    print("=" * 60)
    
    # Загружаем конфигурацию
    models_config = load_models_config()
    
    # Находим нужную модель
    model_config = None
    for m in models_config:
        if m["name"].lower() == target_model_name.lower() or target_model_name.lower() in m["name"].lower():
            model_config = m
            break
    
    if not model_config:
        print(f"❌ Модель '{target_model_name}' не найдена в конфигурации")
        print("\nДоступные модели:")
        for m in models_config:
            print(f"  - {m['name']}")
        return
    
    print(f"✅ Найдена модель: {model_config['name']}")
    print(f"   Model ID: {model_config['model_id']}")
    print(f"   Provider: {model_config.get('provider', 'openai')}")
    
    # Создаем тестовые случаи
    test_cases = create_test_cases()
    print(f"\n📋 Тестовых случаев: {len(test_cases)}")
    print(f"   ⏱️  Ожидаемое время выполнения: ~{len(test_cases) * 5 // 60} минут")
    print(f"   💰 Примерная стоимость: ~{len(test_cases) * 0.01:.2f} USD (зависит от модели)")
    print(f"\n   💡 Совет: Если эксперимент зависнет, нажмите Ctrl+C для безопасного прерывания")
    
    # Подготавливаем директорию для результатов
    results_dir = Path("results/models_comparison")
    results_dir.mkdir(parents=True, exist_ok=True)
    
    model_name_safe = model_config["name"].replace(" ", "_").lower()
    model_dir = results_dir / model_name_safe
    model_dir.mkdir(exist_ok=True)
    
    # Проверяем, есть ли частичные результаты
    partial_results_file = model_dir / "error_detection_results_partial.json"
    if partial_results_file.exists():
        print(f"⚠️  Обнаружены частичные результаты от предыдущего запуска")
        response = input("   Продолжить с места остановки? (y/n): ").strip().lower()
        if response == 'y':
            print(f"   Используем частичные результаты...")
            with open(partial_results_file, 'r', encoding='utf-8') as f:
                partial_results = json.load(f)
            print(f"   Найдено {len(partial_results)} завершенных тестов")
        else:
            print(f"   Начинаем заново...")
            partial_results_file.unlink(missing_ok=True)
    
    # Запускаем эксперимент
    print(f"\n🚀 Запуск эксперимента...")
    print(f"   Ожидаемое время: ~{len(test_cases) * 5} секунд (при ~5с на тест)")
    print(f"   Таймаут на запрос: 120 секунд\n")
    
    try:
        model_result = run_experiment_for_model(model_config, test_cases)
        
        # Сохраняем результаты
        results_file = model_dir / "error_detection_results.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(model_result["results"], f, ensure_ascii=False, indent=2)
        
        # Удаляем частичные результаты, если они есть
        partial_results_file.unlink(missing_ok=True)
        
        # Сохраняем метрики
        metrics_file = model_dir / "error_detection_metrics.json"
        with open(metrics_file, 'w', encoding='utf-8') as f:
            json.dump(model_result["performance"], f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 Результаты сохранены в {model_dir}")
        
        # Показываем метрики
        perf = model_result["performance"]["overall_metrics"]
        print(f"\n📊 МЕТРИКИ:")
        print(f"   Precision: {perf['precision']:.2f}")
        print(f"   Recall: {perf['recall']:.2f}")
        print(f"   F1-score: {perf['f1_score']:.2f}")
        print(f"   TP: {perf['true_positives']}, FP: {perf['false_positives']}, FN: {perf['false_negatives']}")
        
        # Проверяем, можно ли создать сравнительный отчет
        print(f"\n🔄 Проверка готовности для сравнительного отчета...")
        all_models_dirs = list(results_dir.glob("*/error_detection_metrics.json"))
        if len(all_models_dirs) >= 4:
            print(f"✅ Все 4 модели завершены, создаю сравнительный отчет...")
            create_comparison_report()
        else:
            print(f"ℹ️  Завершено {len(all_models_dirs)}/4 моделей")
        
    except KeyboardInterrupt:
        print(f"\n\n⚠️  Эксперимент прерван пользователем (Ctrl+C)")
        print(f"   Сохраняю частичные результаты...")
        
        # Пытаемся получить частичные результаты из run_experiment_for_model
        # Но так как функция не возвращает частичные результаты, 
        # просто сообщаем пользователю
        print(f"   ⚠️  Частичные результаты не могут быть автоматически сохранены")
        print(f"   Для продолжения запустите скрипт снова")
        return
        
    except Exception as e:
        print(f"\n❌ Ошибка при выполнении эксперимента: {e}")
        import traceback
        traceback.print_exc()
        print(f"\n💡 Совет: Проверьте логи выше для диагностики проблемы")
        print(f"   Если эксперимент завис на конкретном тесте, проверьте:")
        print(f"   - Доступность API (OpenRouter)")
        print(f"   - Баланс API ключа")
        print(f"   - Таймауты (должны быть 120 секунд)")
        return

def create_comparison_report():
    """Создание сравнительного отчета для всех моделей"""
    from voltage_divider_experiment_v4 import load_models_config, generate_comparison_table
    
    results_dir = Path("results/models_comparison")
    
    # Загружаем все результаты
    models_config = load_models_config()
    models_results = []
    
    for model_config in models_config:
        model_name_safe = model_config["name"].replace(" ", "_").lower()
        model_dir = results_dir / model_name_safe
        
        metrics_file = model_dir / "error_detection_metrics.json"
        results_file = model_dir / "error_detection_results.json"
        
        if metrics_file.exists() and results_file.exists():
            with open(metrics_file, 'r', encoding='utf-8') as f:
                performance = json.load(f)
            
            with open(results_file, 'r', encoding='utf-8') as f:
                results = json.load(f)
            
            models_results.append({
                "model_config": model_config,
                "results": results,
                "performance": performance
            })
    
    if len(models_results) < 2:
        print("⚠️  Недостаточно моделей для сравнения")
        return
    
    # Генерируем таблицу
    comparison_table = generate_comparison_table(models_results)
    print("\n" + comparison_table)
    
    # Сохраняем сравнительную таблицу
    comparison_file = results_dir / "comparison_table.txt"
    with open(comparison_file, 'w', encoding='utf-8') as f:
        f.write(comparison_table)
    
    # Сохраняем сравнительный отчет в JSON
    comparison_json = {
        "models": [
            {
                "model_config": mr["model_config"],
                "overall_metrics": mr["performance"]["overall_metrics"],
                "by_error_type": mr["performance"]["by_error_type"]
            }
            for mr in models_results
        ]
    }
    
    comparison_json_file = results_dir / "comparison_report.json"
    with open(comparison_json_file, 'w', encoding='utf-8') as f:
        json.dump(comparison_json, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 Сравнительная таблица сохранена в {comparison_file}")
    print(f"💾 Сравнительный отчет сохранен в {comparison_json_file}")
    
    # Находим лучшую модель
    if models_results:
        best_f1 = max(mr["performance"]["overall_metrics"]["f1_score"] for mr in models_results)
        best_model = next(mr for mr in models_results 
                        if mr["performance"]["overall_metrics"]["f1_score"] == best_f1)
        
        print(f"\n🏆 Лучшая модель по F1-score: {best_model['model_config']['name']} (F1: {best_f1:.2f})")

if __name__ == "__main__":
    main()

