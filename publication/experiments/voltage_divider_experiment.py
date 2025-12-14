#!/usr/bin/env python3
"""
LLM-агент для анализа электронных схем
Эксперимент 1: Делители напряжения
"""

import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import json
import re
from typing import Dict, List, Tuple, Optional
from pathlib import Path

# Для работы с LLM
import openai
from dotenv import load_dotenv
import os

# Загружаем переменные окружения
load_dotenv()

class VoltageDivider:
    """Класс для работы с делителями напряжения"""
    
    def __init__(self, r1: float, r2: float, vin: float = 12.0):
        self.r1 = r1  # Верхний резистор (Ом)
        self.r2 = r2  # Нижний резистор (Ом) 
        self.vin = vin  # Входное напряжение (В)
    
    def calculate_vout(self) -> float:
        """Расчет выходного напряжения"""
        return self.vin * self.r2 / (self.r1 + self.r2)
    
    def calculate_current(self) -> float:
        """Расчет тока через делитель"""
        return self.vin / (self.r1 + self.r2)
    
    def calculate_power(self) -> Tuple[float, float, float]:
        """Расчет мощности: (P_r1, P_r2, P_total)"""
        current = self.calculate_current()
        p_r1 = current**2 * self.r1
        p_r2 = current**2 * self.r2
        return p_r1, p_r2, p_r1 + p_r2
    
    def to_netlist(self) -> str:
        """Генерация SPICE netlist"""
        return f"""* Voltage Divider
V1 VIN 0 {self.vin}
R1 VIN VOUT {self.r1}
R2 VOUT 0 {self.r2}
.end"""
    
    def to_description(self) -> str:
        """Текстовое описание схемы"""
        vout = self.calculate_vout()
        current = self.calculate_current()
        return f"""Делитель напряжения:
- Входное напряжение: {self.vin} В
- R1 (верхний): {self.r1} Ом
- R2 (нижний): {self.r2} Ом
- Выходное напряжение: {vout:.2f} В
- Ток: {current*1000:.1f} мА"""


class CircuitAnalysisAgent:
    """LLM-агент для анализа электронных схем"""
    
    def __init__(self, model_name: str = "gpt-4o"):
        self.model_name = model_name
        self.client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    
    def analyze_voltage_divider(self, divider: VoltageDivider, 
                               requirements: str = "") -> Dict:
        """Анализ делителя напряжения через LLM"""
        
        prompt = f"""Ты - опытный инженер-электронщик. Проанализируй эту схему делителя напряжения:

СХЕМА:
{divider.to_description()}

NETLIST:
{divider.to_netlist()}

ТРЕБОВАНИЯ:
{requirements if requirements else "Общий анализ корректности схемы"}

Выполни полный инженерный анализ:

1. РАСЧЕТНАЯ ПРОВЕРКА:
   - Проверь расчет выходного напряжения
   - Рассчитай ток через делитель
   - Оцени мощность рассеивания на резисторах

2. ИНЖЕНЕРНАЯ ОЦЕНКА:
   - Соответствие требованиям
   - Практичность номиналов резисторов
   - Потенциальные проблемы

3. РЕКОМЕНДАЦИИ:
   - Предложения по улучшению
   - Альтернативные номиналы
   - Меры предосторожности

Ответь в структурированном формате JSON:
{{
  "calculations": {{
    "vout_calculated": число,
    "current_ma": число,
    "power_r1_mw": число,
    "power_r2_mw": число
  }},
  "assessment": {{
    "meets_requirements": true/false,
    "practical_values": true/false,
    "potential_issues": ["список проблем"]
  }},
  "recommendations": ["список рекомендаций"],
  "overall_rating": "отлично/хорошо/удовлетворительно/плохо"
}}"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1  # Низкая температура для точности
            )
            
            # Извлекаем JSON из ответа
            content = response.choices[0].message.content
            
            # Ищем JSON блок
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                return {"error": "Не удалось извлечь JSON", "raw_response": content}
                
        except Exception as e:
            return {"error": str(e)}


def expert_analysis(divider: VoltageDivider, requirements: str = "") -> Dict:
    """Эталонный экспертный анализ (золотой стандарт)"""
    
    # Точные расчеты
    vout = divider.calculate_vout()
    current = divider.calculate_current()
    p_r1, p_r2, p_total = divider.calculate_power()
    
    # Экспертная оценка
    practical_values = True
    issues = []
    recommendations = []
    
    # Проверка номиналов
    if divider.r1 < 1000 or divider.r2 < 1000:
        issues.append("Слишком малые сопротивления - высокий ток")
        practical_values = False
    
    if divider.r1 > 1e6 or divider.r2 > 1e6:
        issues.append("Слишком большие сопротивления - влияние помех")
        recommendations.append("Добавить буферный усилитель")
    
    # Проверка мощности
    if p_r1 > 0.25 or p_r2 > 0.25:  # 0.25Вт
        issues.append("Превышение мощности стандартных резисторов")
        recommendations.append("Использовать резисторы большей мощности")
    
    # Проверка тока
    if current > 0.01:  # 10мА
        issues.append("Высокий ток потребления")
        recommendations.append("Увеличить номиналы резисторов")
    
    # Общая оценка
    if len(issues) == 0:
        rating = "отлично"
    elif len(issues) <= 2:
        rating = "хорошо"
    elif len(issues) <= 3:
        rating = "удовлетворительно"
    else:
        rating = "плохо"
    
    return {
        "calculations": {
            "vout_calculated": round(vout, 3),
            "current_ma": round(current * 1000, 2),
            "power_r1_mw": round(p_r1 * 1000, 1),
            "power_r2_mw": round(p_r2 * 1000, 1)
        },
        "assessment": {
            "meets_requirements": len(issues) <= 1,
            "practical_values": practical_values,
            "potential_issues": issues
        },
        "recommendations": recommendations,
        "overall_rating": rating
    }


def analyze_experiment_results(results):
    """Анализ результатов сравнения LLM vs Эксперт"""
    
    successful_analyses = [r for r in results if "error" not in r["llm"]]
    
    print(f"📊 РЕЗУЛЬТАТЫ ЭКСПЕРИМЕНТА:")
    print(f"Успешных анализов LLM: {len(successful_analyses)}/{len(results)}")
    
    if not successful_analyses:
        print("❌ Нет успешных анализов для сравнения")
        return
    
    # Сравнение расчетов
    voltage_errors = []
    current_errors = []
    rating_matches = 0
    
    for result in successful_analyses:
        expert = result["expert"]["calculations"]
        llm = result["llm"]["calculations"]
        
        # Относительные ошибки
        if expert["vout_calculated"] != 0:
            v_error = abs(expert["vout_calculated"] - llm["vout_calculated"]) / expert["vout_calculated"]
            voltage_errors.append(v_error * 100)
        
        if expert["current_ma"] != 0:
            i_error = abs(expert["current_ma"] - llm["current_ma"]) / expert["current_ma"]
            current_errors.append(i_error * 100)
        
        # Совпадение оценок
        if result["expert"]["overall_rating"] == result["llm"]["overall_rating"]:
            rating_matches += 1
    
    print(f"\n📈 ТОЧНОСТЬ РАСЧЕТОВ:")
    if voltage_errors:
        print(f"Средняя ошибка напряжения: {np.mean(voltage_errors):.1f}%")
        print(f"Максимальная ошибка напряжения: {np.max(voltage_errors):.1f}%")
    
    if current_errors:
        print(f"Средняя ошибка тока: {np.mean(current_errors):.1f}%")
    
    print(f"\n🎯 СОГЛАСИЕ В ОЦЕНКАХ:")
    agreement_rate = rating_matches / len(successful_analyses) * 100
    print(f"Совпадение итоговых оценок: {agreement_rate:.1f}%")
    
    return {
        "voltage_errors": voltage_errors,
        "current_errors": current_errors,
        "agreement_rate": agreement_rate
    }


def main():
    """Главная функция эксперимента"""
    
    print("🔬 LLM-агент для анализа электронных схем")
    print("=" * 50)
    
    # Создаем набор тестовых делителей
    test_dividers = [
        VoltageDivider(10000, 10000, 12),  # 1:1, 6В
        VoltageDivider(20000, 10000, 12),  # 2:1, 4В  
        VoltageDivider(10000, 5000, 12),   # 2:1, 4В
        VoltageDivider(1000, 1000, 5),     # 1:1, 2.5В
        VoltageDivider(4700, 2200, 9),     # ~2:1, ~2.9В
    ]
    
    print(f"📊 Создано тестовых делителей: {len(test_dividers)}")
    for i, div in enumerate(test_dividers):
        print(f"\n{i+1}. {div.to_description()}")
    
    # Создаем агента
    agent = CircuitAnalysisAgent()
    print("\n🤖 LLM-агент создан")
    
    # Тестируем эталонный анализ
    print("\n🔬 Тест эталонного анализа:")
    test_expert = expert_analysis(test_dividers[0])
    print(json.dumps(test_expert, indent=2, ensure_ascii=False))
    
    # Проводим сравнительный анализ
    print("\n🚀 Запуск эксперимента...")
    results = []
    
    for i, divider in enumerate(test_dividers):
        print(f"\n🔄 Анализ делителя {i+1}/{len(test_dividers)}...")
        
        # Эталонный анализ
        expert_result = expert_analysis(divider)
        
        # LLM анализ
        llm_result = agent.analyze_voltage_divider(divider)
        
        # Сохраняем результаты
        results.append({
            "divider_id": i + 1,
            "circuit": {
                "r1": divider.r1,
                "r2": divider.r2, 
                "vin": divider.vin
            },
            "expert": expert_result,
            "llm": llm_result
        })
        
        print(f"✅ Делитель {i+1} проанализирован")
    
    print(f"\n🎉 Эксперимент завершен! Проанализировано {len(results)} схем")
    
    # Анализируем результаты
    print("\n" + "="*50)
    metrics = analyze_experiment_results(results)
    
    # Сохраняем результаты
    output_file = Path("publication/experiments/voltage_divider_results.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Результаты сохранены в {output_file}")


if __name__ == "__main__":
    main()
