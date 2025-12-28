#!/usr/bin/env python3
"""
Скрипт для запуска экспериментов для всех моделей из конфигурации
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
    """Запуск экспериментов для всех моделей из конфигурации"""
    
    # Определяем файл конфигурации
    config_file = "models_config.json"
    if len(sys.argv) > 1:
        config_file = sys.argv[1]
    
    print(f"🔬 ЗАПУСК ЭКСПЕРИМЕНТОВ ДЛЯ ВСЕХ МОДЕЛЕЙ")
    print("=" * 60)
    print(f"📁 Файл конфигурации: {config_file}")
    
    # Загружаем конфигурацию
    try:
        models_config = load_models_config(config_file)
        if not models_config:
            print(f"\n❌ Файл {config_file} пуст или не содержит моделей!")
            return
        print(f"\n📋 Загружено моделей для тестирования: {len(models_config)}")
    except FileNotFoundError:
        print(f"\n❌ Файл {config_file} не найден!")
        return
    except Exception as e:
        print(f"\n❌ Ошибка при загрузке конфигурации: {e}")
        return
    
    # Показываем список моделей
    print("\n📋 Список моделей для тестирования:")
    for i, model in enumerate(models_config, 1):
        print(f"   {i}. {model['name']} ({model['group']}, {model['size']})")
    
    # Создаем тестовые случаи
    test_cases = create_test_cases()
    print(f"\n📋 Тестовых случаев: {len(test_cases)}")
    print(f"   ⏱️  Ожидаемое время: ~{len(test_cases) * len(models_config) * 5 // 60} минут")
    print(f"   💰 Примерная стоимость: ~{len(test_cases) * len(models_config) * 0.01:.2f} USD")
    
    response = input(f"\n⚠️  Запустить эксперимент для {len(models_config)} моделей? (y/n): ").strip().lower()
    if response != 'y':
        print("Отменено пользователем")
        return
    
    # Запускаем эксперимент для каждой модели
    results_dir = Path("results/models_comparison")
    results_dir.mkdir(parents=True, exist_ok=True)
    
    models_results = []
    
    for i, model_config in enumerate(models_config, 1):
        print(f"\n{'='*60}")
        print(f"Модель {i}/{len(models_config)}: {model_config['name']}")
        print(f"{'='*60}")
        
        try:
            model_result = run_experiment_for_model(model_config, test_cases)
            models_results.append(model_result)
            
            # Сохраняем результаты для каждой модели
            model_name_safe = model_config["name"].replace(" ", "_").lower()
            model_dir = results_dir / model_name_safe
            model_dir.mkdir(exist_ok=True)
            
            # Сохраняем полные результаты
            results_file = model_dir / "error_detection_results.json"
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(model_result["results"], f, ensure_ascii=False, indent=2)
            
            # Сохраняем метрики
            metrics_file = model_dir / "error_detection_metrics.json"
            with open(metrics_file, 'w', encoding='utf-8') as f:
                json.dump(model_result["performance"], f, ensure_ascii=False, indent=2)
            
            print(f"\n💾 Результаты {model_config['name']} сохранены в {model_dir}")
            
        except KeyboardInterrupt:
            print(f"\n\n⚠️  Эксперимент прерван пользователем (Ctrl+C)")
            print(f"   Завершено {i-1}/{len(models_config)} моделей")
            break
        except Exception as e:
            print(f"\n❌ Ошибка при тестировании {model_config['name']}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Генерируем сравнительный отчет
    if models_results:
        print(f"\n{'='*60}")
        print("📊 ГЕНЕРАЦИЯ СРАВНИТЕЛЬНОГО ОТЧЕТА")
        print(f"{'='*60}\n")
        
        comparison_table = generate_comparison_table(models_results)
        print(comparison_table)
        
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
    
    print(f"\n✅ Эксперимент завершен для {len(models_results)}/{len(models_config)} моделей")

if __name__ == "__main__":
    main()




