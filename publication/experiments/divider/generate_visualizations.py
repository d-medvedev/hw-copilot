#!/usr/bin/env python3
"""
Скрипт для генерации графических визуализаций результатов эксперимента
"""

import json
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
import numpy as np
from pathlib import Path
from typing import Dict, List

# Настройка стиля
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (12, 8)
plt.rcParams['font.size'] = 10
plt.rcParams['axes.labelsize'] = 12
plt.rcParams['axes.titlesize'] = 14
plt.rcParams['xtick.labelsize'] = 10
plt.rcParams['ytick.labelsize'] = 10
plt.rcParams['legend.fontsize'] = 9

# Цветовая палитра
COLORS = {
    'commercial': '#3498db',
    'opensource_large': '#2ecc71',
    'opensource_small': '#f39c12'
}

def load_comparison_data() -> List[Dict]:
    """Загрузка данных для сравнения"""
    report_file = Path("results/models_comparison/comparison_report.json")
    
    if not report_file.exists():
        print("❌ Файл comparison_report.json не найден!")
        return []
    
    with open(report_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return data.get("models", [])

def get_model_color(model_config: Dict) -> str:
    """Получение цвета для модели"""
    group = model_config.get("group", "unknown")
    size = model_config.get("size", "unknown")
    
    if group == "commercial":
        return COLORS['commercial']
    elif group == "opensource" and size == "large":
        return COLORS['opensource_large']
    elif group == "opensource" and size == "small":
        return COLORS['opensource_small']
    return '#95a5a6'

def plot_overall_metrics(models_data: List[Dict], output_dir: Path):
    """График 1: Общие метрики (Precision, Recall, F1)"""
    
    # Сортируем модели по F1-score
    sorted_models = sorted(models_data, 
                          key=lambda x: x['overall_metrics']['f1_score'], 
                          reverse=True)
    
    model_names = [m['model_config']['name'] for m in sorted_models]
    precision = [m['overall_metrics']['precision'] for m in sorted_models]
    recall = [m['overall_metrics']['recall'] for m in sorted_models]
    f1_scores = [m['overall_metrics']['f1_score'] for m in sorted_models]
    colors = [get_model_color(m['model_config']) for m in sorted_models]
    
    x = np.arange(len(model_names))
    width = 0.25
    
    fig, ax = plt.subplots(figsize=(14, 8))
    
    bars1 = ax.bar(x - width, precision, width, label='Precision', color='#3498db', alpha=0.8)
    bars2 = ax.bar(x, recall, width, label='Recall', color='#2ecc71', alpha=0.8)
    bars3 = ax.bar(x + width, f1_scores, width, label='F1-score', color='#e74c3c', alpha=0.8)
    
    # Добавляем значения на столбцы
    for bars in [bars1, bars2, bars3]:
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{height:.2f}',
                       ha='center', va='bottom', fontsize=8)
    
    ax.set_xlabel('Модели', fontweight='bold')
    ax.set_ylabel('Метрика', fontweight='bold')
    ax.set_title('Сравнение моделей по метрикам Precision, Recall и F1-score', 
                 fontweight='bold', pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels(model_names, rotation=45, ha='right')
    ax.set_ylim([0, 1.1])
    ax.legend(loc='upper left')
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_dir / '1_overall_metrics.png', dpi=300, bbox_inches='tight')
    plt.close()
    print("✅ График 1 сохранен: 1_overall_metrics.png")

def plot_heatmap(models_data: List[Dict], output_dir: Path):
    """График 2: Тепловая карта F1-score по типам ошибок"""
    
    # Сортируем модели по общему F1-score
    sorted_models = sorted(models_data, 
                          key=lambda x: x['overall_metrics']['f1_score'], 
                          reverse=True)
    
    model_names = [m['model_config']['name'] for m in sorted_models]
    error_types = [
        "Type 1\n(Wrong Ratio)",
        "Type 2\n(Too Small)",
        "Type 3\n(Too Large)",
        "Type 4\n(Load Ignored)",
        "Type 5\n(ADC Mismatch)",
        "Type 6\n(Power Exceed)",
        "Type 7\n(No Protection)",
        "Type 8\n(TCR Ignored)"
    ]
    
    # Создаем матрицу F1-scores
    error_type_keys = [
        "type_1_wrong_ratio",
        "type_2_too_small",
        "type_3_too_large",
        "type_4_load_ignored",
        "type_5_adc_mismatch",
        "type_6_power_exceed",
        "type_7_no_protection",
        "type_8_tcr_ignored"
    ]
    
    f1_matrix = []
    for model in sorted_models:
        row = []
        by_type = model['by_error_type']
        for error_type in error_type_keys:
            f1 = by_type.get(error_type, {}).get('f1_score', 0.0)
            row.append(f1)
        f1_matrix.append(row)
    
    fig, ax = plt.subplots(figsize=(12, 10))
    
    im = ax.imshow(f1_matrix, cmap='RdYlGn', aspect='auto', vmin=0, vmax=1)
    
    # Устанавливаем метки
    ax.set_xticks(np.arange(len(error_types)))
    ax.set_yticks(np.arange(len(model_names)))
    ax.set_xticklabels(error_types)
    ax.set_yticklabels(model_names)
    
    # Поворачиваем метки
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")
    
    # Добавляем текстовые аннотации
    for i in range(len(model_names)):
        for j in range(len(error_types)):
            text = ax.text(j, i, f'{f1_matrix[i][j]:.2f}',
                          ha="center", va="center", color="black", fontsize=8)
    
    ax.set_title("F1-score по типам ошибок для каждой модели", 
                 fontweight='bold', pad=20)
    
    # Добавляем colorbar
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label('F1-score', rotation=270, labelpad=20)
    
    plt.tight_layout()
    plt.savefig(output_dir / '2_heatmap_f1_by_error_type.png', dpi=300, bbox_inches='tight')
    plt.close()
    print("✅ График 2 сохранен: 2_heatmap_f1_by_error_type.png")

def plot_precision_recall_scatter(models_data: List[Dict], output_dir: Path):
    """График 3: Scatter Plot Precision vs Recall"""
    
    fig, ax = plt.subplots(figsize=(10, 10))
    
    for model in models_data:
        precision = model['overall_metrics']['precision']
        recall = model['overall_metrics']['recall']
        f1 = model['overall_metrics']['f1_score']
        name = model['model_config']['name']
        color = get_model_color(model['model_config'])
        
        # Размер точки пропорционален F1-score
        size = 300 + f1 * 500
        
        ax.scatter(recall, precision, s=size, c=color, alpha=0.6, 
                  edgecolors='black', linewidth=1.5)
        
        # Добавляем подписи для топ-5 моделей
        if f1 > 0.75:
            ax.annotate(name, (recall, precision), 
                       xytext=(5, 5), textcoords='offset points',
                       fontsize=8, fontweight='bold')
    
    # Идеальная точка
    ax.scatter(1.0, 1.0, s=200, c='red', marker='*', 
              edgecolors='black', linewidth=2, zorder=5,
              label='Идеальная точка (P=1.0, R=1.0)')
    
    ax.set_xlabel('Recall (Полнота)', fontweight='bold')
    ax.set_ylabel('Precision (Точность)', fontweight='bold')
    ax.set_title('Precision vs Recall для всех моделей\n(Размер точки = F1-score)', 
                 fontweight='bold', pad=20)
    ax.set_xlim([-0.05, 1.05])
    ax.set_ylim([-0.05, 1.05])
    ax.grid(True, alpha=0.3)
    
    # Легенда для групп
    commercial_patch = mpatches.Patch(color=COLORS['commercial'], label='Commercial')
    opensource_large_patch = mpatches.Patch(color=COLORS['opensource_large'], label='Open-source Large')
    opensource_small_patch = mpatches.Patch(color=COLORS['opensource_small'], label='Open-source Small')
    ax.legend(handles=[commercial_patch, opensource_large_patch, opensource_small_patch],
             loc='lower left')
    
    plt.tight_layout()
    plt.savefig(output_dir / '3_precision_recall_scatter.png', dpi=300, bbox_inches='tight')
    plt.close()
    print("✅ График 3 сохранен: 3_precision_recall_scatter.png")

def plot_grouped_comparison(models_data: List[Dict], output_dir: Path):
    """График 4: Сравнение по группам моделей"""
    
    # Группируем модели
    groups = {
        'Commercial Large': [],
        'Open-source Large': [],
        'Open-source Small': []
    }
    
    for model in models_data:
        config = model['model_config']
        group = config.get('group', '')
        size = config.get('size', '')
        
        if group == 'commercial' and size == 'large':
            groups['Commercial Large'].append(model)
        elif group == 'opensource' and size == 'large':
            groups['Open-source Large'].append(model)
        elif group == 'opensource' and size == 'small':
            groups['Open-source Small'].append(model)
    
    # Вычисляем средние значения
    group_means = {}
    for group_name, models in groups.items():
        if models:
            precisions = [m['overall_metrics']['precision'] for m in models]
            recalls = [m['overall_metrics']['recall'] for m in models]
            f1s = [m['overall_metrics']['f1_score'] for m in models]
            
            group_means[group_name] = {
                'precision': np.mean(precisions),
                'recall': np.mean(recalls),
                'f1': np.mean(f1s),
                'std_precision': np.std(precisions),
                'std_recall': np.std(recalls),
                'std_f1': np.std(f1s)
            }
    
    group_names = list(group_means.keys())
    precision_means = [group_means[g]['precision'] for g in group_names]
    recall_means = [group_means[g]['recall'] for g in group_names]
    f1_means = [group_means[g]['f1'] for g in group_names]
    
    precision_stds = [group_means[g]['std_precision'] for g in group_names]
    recall_stds = [group_means[g]['std_recall'] for g in group_names]
    f1_stds = [group_means[g]['std_f1'] for g in group_names]
    
    x = np.arange(len(group_names))
    width = 0.25
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    bars1 = ax.bar(x - width, precision_means, width, yerr=precision_stds,
                   label='Precision', color='#3498db', alpha=0.8, capsize=5)
    bars2 = ax.bar(x, recall_means, width, yerr=recall_stds,
                   label='Recall', color='#2ecc71', alpha=0.8, capsize=5)
    bars3 = ax.bar(x + width, f1_means, width, yerr=f1_stds,
                   label='F1-score', color='#e74c3c', alpha=0.8, capsize=5)
    
    # Добавляем значения
    for bars, values, stds in [(bars1, precision_means, precision_stds),
                               (bars2, recall_means, recall_stds),
                               (bars3, f1_means, f1_stds)]:
        for bar, val, std in zip(bars, values, stds):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + std + 0.02,
                   f'{val:.2f}',
                   ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    ax.set_xlabel('Группы моделей', fontweight='bold')
    ax.set_ylabel('Средняя метрика', fontweight='bold')
    ax.set_title('Сравнение средних метрик по группам моделей', 
                 fontweight='bold', pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels(group_names)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    ax.set_ylim([0, 1.1])
    
    plt.tight_layout()
    plt.savefig(output_dir / '4_grouped_comparison.png', dpi=300, bbox_inches='tight')
    plt.close()
    print("✅ График 4 сохранен: 4_grouped_comparison.png")

def main():
    """Основная функция"""
    
    print("📊 ГЕНЕРАЦИЯ ГРАФИЧЕСКИХ ВИЗУАЛИЗАЦИЙ")
    print("=" * 60)
    
    # Загружаем данные
    models_data = load_comparison_data()
    
    if not models_data:
        print("❌ Нет данных для визуализации")
        return
    
    print(f"📋 Загружено данных для {len(models_data)} моделей\n")
    
    # Создаем директорию для графиков
    output_dir = Path("results/visualizations")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Генерируем графики
    print("🎨 Генерация графиков...\n")
    
    try:
        plot_overall_metrics(models_data, output_dir)
        plot_heatmap(models_data, output_dir)
        plot_precision_recall_scatter(models_data, output_dir)
        plot_grouped_comparison(models_data, output_dir)
        
        print(f"\n✅ Все графики сохранены в {output_dir}")
        print(f"📁 Файлы:")
        for f in sorted(output_dir.glob("*.png")):
            print(f"   - {f.name}")
            
    except Exception as e:
        print(f"\n❌ Ошибка при генерации графиков: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

