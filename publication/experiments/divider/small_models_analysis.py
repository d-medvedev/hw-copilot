#!/usr/bin/env python3
"""
Анализ производительности маленьких моделей
"""

import json
from pathlib import Path
from collections import defaultdict

def analyze_small_models():
    """Анализ маленьких моделей"""
    
    print("📊 АНАЛИЗ МАЛЕНЬКИХ МОДЕЛЕЙ")
    print("=" * 60)
    
    # Загружаем объединенный отчет
    report_file = Path("results/models_comparison/comparison_report.json")
    with open(report_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Фильтруем маленькие модели
    small_models = []
    for model_data in data['models']:
        config = model_data['model_config']
        if config.get('size') == 'small':
            small_models.append(model_data)
    
    print(f"\n📋 Найдено маленьких моделей: {len(small_models)}\n")
    
    # Сортируем по F1-score
    small_models.sort(key=lambda x: x['overall_metrics']['f1_score'], reverse=True)
    
    print("🏆 РЕЙТИНГ МАЛЕНЬКИХ МОДЕЛЕЙ:")
    print("-" * 60)
    for i, model in enumerate(small_models, 1):
        metrics = model['overall_metrics']
        config = model['model_config']
        print(f"{i}. {config['name']:20} ({config['group']:12})")
        print(f"   F1-score: {metrics['f1_score']:.2f} | Precision: {metrics['precision']:.2f} | Recall: {metrics['recall']:.2f}")
        print(f"   TP: {metrics['true_positives']}, FP: {metrics['false_positives']}, FN: {metrics['false_negatives']}")
        print()
    
    # Детальный анализ лучшей модели
    best_model = small_models[0]
    best_name = best_model['model_config']['name']
    
    print(f"\n{'='*60}")
    print(f"🔍 ДЕТАЛЬНЫЙ АНАЛИЗ ЛУЧШЕЙ МОДЕЛИ: {best_name}")
    print(f"{'='*60}\n")
    
    metrics = best_model['overall_metrics']
    print(f"📊 Общие метрики:")
    print(f"   Precision: {metrics['precision']:.2f}")
    print(f"   Recall: {metrics['recall']:.2f}")
    print(f"   F1-score: {metrics['f1_score']:.2f}")
    print(f"   True Positives: {metrics['true_positives']}")
    print(f"   False Positives: {metrics['false_positives']}")
    print(f"   False Negatives: {metrics['false_negatives']}")
    
    print(f"\n📋 Производительность по типам ошибок:")
    print("-" * 60)
    
    error_type_names = {
        "type_1_wrong_ratio": "Type 1: Неверное соотношение резисторов",
        "type_2_too_small": "Type 2: Слишком маленькие номиналы",
        "type_3_too_large": "Type 3: Слишком большие номиналы",
        "type_4_load_ignored": "Type 4: Игнорирование входного сопротивления нагрузки",
        "type_5_adc_mismatch": "Type 5: Подключение к АЦП без учета параметров",
        "type_6_power_exceed": "Type 6: Превышение допустимой мощности резисторов",
        "type_7_no_protection": "Type 7: Отсутствие защиты от перенапряжений",
        "type_8_tcr_ignored": "Type 8: Игнорирование температурного коэффициента"
    }
    
    by_type = best_model['by_error_type']
    for error_type, name in error_type_names.items():
        if error_type in by_type:
            type_metrics = by_type[error_type]
            f1 = type_metrics['f1_score']
            tp = type_metrics['true_positives']
            fp = type_metrics['false_positives']
            fn = type_metrics['false_negatives']
            
            status = "✅" if f1 >= 0.7 else "⚠️" if f1 >= 0.4 else "❌"
            print(f"{status} {name}")
            print(f"   F1: {f1:.2f} | TP: {tp}, FP: {fp}, FN: {fn}")
            
            if fn > 0:
                print(f"   ⚠️  Пропущено ошибок: {fn}")
            if fp > 0:
                print(f"   ⚠️  Ложных срабатываний: {fp}")
            print()
    
    # Анализ детальных результатов
    model_name_safe = best_model['model_config']['name'].replace(" ", "_").lower()
    results_file = Path(f"results/models_comparison/{model_name_safe}/error_detection_results.json")
    
    if results_file.exists():
        with open(results_file, 'r', encoding='utf-8') as f:
            detailed_results = json.load(f)
        
        # Анализ ошибок
        error_cases = []
        empty_responses = 0
        
        for result in detailed_results:
            if 'error' in result.get('llm', {}):
                if 'Empty response' in result['llm']['error']:
                    empty_responses += 1
                error_cases.append({
                    'case_id': result['case_id'],
                    'name': result['test_case_info']['name'],
                    'error': result['llm']['error'],
                    'expected_errors': result['test_case_info']['expected_error_types']
                })
        
        if error_cases or empty_responses > 0:
            print(f"\n⚠️  ПРОБЛЕМЫ С ОТВЕТАМИ:")
            print(f"   Пустых ответов: {empty_responses}/{len(detailed_results)}")
            
            if error_cases:
                print(f"\n   Случаи с ошибками:")
                for case in error_cases[:10]:  # Показываем первые 10
                    print(f"   - Case {case['case_id']}: {case['name']}")
                    print(f"     Ошибка: {case['error'][:80]}")
                    if case['expected_errors']:
                        print(f"     Ожидалось найти: {', '.join(case['expected_errors'])}")
        
        # Анализ пропущенных ошибок
        print(f"\n📉 АНАЛИЗ ПРОПУЩЕННЫХ ОШИБОК:")
        print("-" * 60)
        
        fn_by_type = defaultdict(int)
        for result in detailed_results:
            if result.get('detection'):
                fn_errors = result['detection'].get('false_negatives', [])
                for error_type in fn_errors:
                    fn_by_type[error_type] += 1
        
        if fn_by_type:
            for error_type, count in sorted(fn_by_type.items(), key=lambda x: x[1], reverse=True):
                type_name = error_type_names.get(error_type, error_type)
                print(f"   {type_name}: {count} пропущено")
        else:
            print("   ✅ Нет пропущенных ошибок (FN = 0)")
        
        # Анализ ложных срабатываний
        print(f"\n📈 АНАЛИЗ ЛОЖНЫХ СРАБАТЫВАНИЙ:")
        print("-" * 60)
        
        fp_by_type = defaultdict(int)
        for result in detailed_results:
            if result.get('detection'):
                fp_errors = result['detection'].get('false_positives', [])
                for error_type in fp_errors:
                    fp_by_type[error_type] += 1
        
        if fp_by_type:
            for error_type, count in sorted(fp_by_type.items(), key=lambda x: x[1], reverse=True):
                type_name = error_type_names.get(error_type, error_type)
                print(f"   {type_name}: {count} ложных срабатываний")
        else:
            print("   ✅ Нет ложных срабатываний (FP = 0)")

if __name__ == "__main__":
    analyze_small_models()

