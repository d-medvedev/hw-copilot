#!/usr/bin/env python3
"""
Скрипт для объединения результатов всех моделей в единый отчет
"""

import json
from pathlib import Path
from voltage_divider_experiment_v4 import load_models_config, generate_comparison_table

def merge_all_results():
    """Объединение результатов всех моделей"""
    
    print("🔄 ОБЪЕДИНЕНИЕ РЕЗУЛЬТАТОВ ВСЕХ МОДЕЛЕЙ")
    print("=" * 60)
    
    # Загружаем конфигурацию всех моделей
    try:
        models_config = load_models_config("models_config_extended.json")
        print(f"📋 Загружено моделей из конфигурации: {len(models_config)}")
    except FileNotFoundError:
        print("❌ Файл models_config_extended.json не найден!")
        return
    
    results_dir = Path("results/models_comparison")
    models_results = []
    
    # Загружаем результаты для каждой модели
    for model_config in models_config:
        model_name_safe = model_config["name"].replace(" ", "_").lower()
        model_dir = results_dir / model_name_safe
        
        metrics_file = model_dir / "error_detection_metrics.json"
        results_file = model_dir / "error_detection_results.json"
        
        if metrics_file.exists() and results_file.exists():
            try:
                with open(metrics_file, 'r', encoding='utf-8') as f:
                    performance = json.load(f)
                
                with open(results_file, 'r', encoding='utf-8') as f:
                    results = json.load(f)
                
                models_results.append({
                    "model_config": model_config,
                    "results": results,
                    "performance": performance
                })
                
                print(f"✅ {model_config['name']}")
            except Exception as e:
                print(f"⚠️  {model_config['name']}: ошибка загрузки - {e}")
        else:
            print(f"⚠️  {model_config['name']}: результаты не найдены")
    
    if not models_results:
        print("\n❌ Не найдено результатов ни для одной модели!")
        return
    
    print(f"\n📊 Успешно загружено результатов: {len(models_results)}/{len(models_config)}")
    
    # Генерируем сравнительную таблицу
    print(f"\n📋 Генерация сравнительной таблицы...")
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
    
    return len(models_results)

if __name__ == "__main__":
    merge_all_results()

