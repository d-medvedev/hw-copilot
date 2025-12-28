#!/usr/bin/env python3
"""
Скрипт для запуска эксперимента синтеза для одной модели
"""

import json
import sys
from pathlib import Path
from voltage_divider_synthesis_experiment import (
    load_models_config,
    run_synthesis_experiment_for_model,
    create_synthesis_test_cases,
    generate_synthesis_comparison_table
)

def main():
    """Запуск эксперимента синтеза для одной модели"""
    
    if len(sys.argv) < 2:
        print("Использование: python run_synthesis_single_model.py <model_name>")
        print("\nДоступные модели:")
        models = load_models_config("models_config_extended.json")
        for m in models:
            print(f"  - {m['name']}")
        return
    
    target_model_name = sys.argv[1]
    
    print(f"🔬 Запуск эксперимента синтеза для модели: {target_model_name}")
    print("=" * 60)
    
    # Загружаем конфигурацию
    models_config = load_models_config("models_config_extended.json")
    
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
    print(f"   Provider: {model_config.get('provider', 'openrouter')}")
    
    # Создаем тестовые случаи
    test_cases = create_synthesis_test_cases()
    print(f"\n📋 Тестовых случаев: {len(test_cases)}")
    print(f"   ⏱️  Ожидаемое время выполнения: ~{len(test_cases) * 10 // 60} минут")
    print(f"   💰 Примерная стоимость: ~{len(test_cases) * 0.02:.2f} USD (зависит от модели)")
    print(f"\n   💡 Совет: Если эксперимент зависнет, нажмите Ctrl+C для безопасного прерывания")
    
    # Подготавливаем директорию для результатов
    results_dir = Path("results/synthesis")
    results_dir.mkdir(parents=True, exist_ok=True)
    
    model_name_safe = model_config["name"].replace(" ", "_").lower()
    model_dir = results_dir / model_name_safe
    model_dir.mkdir(exist_ok=True)
    
    # Запускаем эксперимент
    print(f"\n🚀 Запуск эксперимента...")
    print(f"   Ожидаемое время: ~{len(test_cases) * 10} секунд (при ~10с на тест)")
    print(f"   Таймаут на запрос: 120 секунд\n")
    
    try:
        model_result = run_synthesis_experiment_for_model(model_config, test_cases)
        
        # Сохраняем результаты
        results_file = model_dir / "synthesis_results.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(model_result["results"], f, ensure_ascii=False, indent=2)
        
        # Сохраняем метрики
        metrics_file = model_dir / "synthesis_metrics.json"
        with open(metrics_file, 'w', encoding='utf-8') as f:
            json.dump(model_result["performance"], f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 Результаты сохранены в {model_dir}")
        
        # Показываем метрики
        perf = model_result["performance"]["overall_metrics"]
        print(f"\n📊 МЕТРИКИ:")
        print(f"   Success Rate: {perf['success_rate']:.2f}")
        print(f"   Calculation Accuracy: {perf['calculation_accuracy']:.2f}")
        print(f"   Requirements Compliance: {perf['requirements_compliance']:.2f}")
        print(f"   Error Rate: {perf['error_rate']:.2f}")
        print(f"   Total Errors: {perf['total_errors']}")
        
    except KeyboardInterrupt:
        print(f"\n\n⚠️  Эксперимент прерван пользователем (Ctrl+C)")
        print(f"   Для продолжения запустите скрипт снова")
        return
        
    except Exception as e:
        print(f"\n❌ Ошибка при выполнении эксперимента: {e}")
        import traceback
        traceback.print_exc()
        print(f"\n💡 Совет: Проверьте логи выше для диагностики проблемы")
        return

if __name__ == "__main__":
    main()




