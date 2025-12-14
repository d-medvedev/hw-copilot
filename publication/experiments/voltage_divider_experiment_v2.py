#!/usr/bin/env python3
"""
LLM-агент для анализа электронных схем v2.0
Эксперимент 1: Делители напряжения (с Structured Output)
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


class CircuitAnalysisAgentV2:
    """LLM-агент для анализа электронных схем с Structured Output"""
    
    def __init__(self, model_name: str = "gpt-4o-2024-08-06"):
        self.model_name = model_name
        self.client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        # Схема для structured output
        self.response_schema = {
            "type": "object",
            "properties": {
                "calculations": {
                    "type": "object",
                    "properties": {
                        "vout_calculated": {"type": "number"},
                        "current_ma": {"type": "number"},
                        "power_r1_mw": {"type": "number"},
                        "power_r2_mw": {"type": "number"}
                    },
                    "required": ["vout_calculated", "current_ma", "power_r1_mw", "power_r2_mw"],
                    "additionalProperties": False
                },
                "assessment": {
                    "type": "object",
                    "properties": {
                        "meets_requirements": {"type": "boolean"},
                        "practical_values": {"type": "boolean"},
                        "potential_issues": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    },
                    "required": ["meets_requirements", "practical_values", "potential_issues"],
                    "additionalProperties": False
                },
                "recommendations": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "overall_rating": {
                    "type": "string",
                    "enum": ["отлично", "хорошо", "удовлетворительно", "плохо"]
                }
            },
            "required": ["calculations", "assessment", "recommendations", "overall_rating"],
            "additionalProperties": False
        }
    
    def analyze_voltage_divider(self, divider: VoltageDivider, 
                               requirements: str = "") -> Dict:
        """Анализ делителя напряжения через LLM с Structured Output"""
        
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
   - Рассчитай ток через делитель (в мА)
   - Оцени мощность рассеивания на резисторах (в мВт)

2. ИНЖЕНЕРНАЯ ОЦЕНКА:
   - Соответствие требованиям
   - Практичность номиналов резисторов
   - Потенциальные проблемы

3. РЕКОМЕНДАЦИИ:
   - Предложения по улучшению
   - Альтернативные номиналы
   - Меры предосторожности

Предоставь результаты анализа в структурированном формате."""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,  # Низкая температура для точности
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "circuit_analysis",
                        "strict": True,
                        "schema": self.response_schema
                    }
                }
            )
            
            # Structured output гарантирует валидный JSON
            content = response.choices[0].message.content
            return json.loads(content)
                
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
    success_rate = len(successful_analyses) / len(results) * 100
    print(f"Надежность системы: {success_rate:.1f}%")
    
    if not successful_analyses:
        print("❌ Нет успешных анализов для сравнения")
        return
    
    # Сравнение расчетов
    voltage_errors = []
    current_errors = []
    power_errors = []
    rating_matches = 0
    
    print(f"\n📈 ДЕТАЛЬНОЕ СРАВНЕНИЕ:")
    for i, result in enumerate(successful_analyses):
        expert = result["expert"]["calculations"]
        llm = result["llm"]["calculations"]
        
        print(f"\n🔍 Делитель {result['divider_id']}:")
        print(f"  Напряжение: Эксперт={expert['vout_calculated']}В, LLM={llm['vout_calculated']}В")
        print(f"  Ток: Эксперт={expert['current_ma']}мА, LLM={llm['current_ma']}мА")
        print(f"  Оценка: Эксперт='{result['expert']['overall_rating']}', LLM='{result['llm']['overall_rating']}'")
        
        # Относительные ошибки
        if expert["vout_calculated"] != 0:
            v_error = abs(expert["vout_calculated"] - llm["vout_calculated"]) / expert["vout_calculated"]
            voltage_errors.append(v_error * 100)
        
        if expert["current_ma"] != 0:
            i_error = abs(expert["current_ma"] - llm["current_ma"]) / expert["current_ma"]
            current_errors.append(i_error * 100)
        
        # Средняя ошибка по мощности
        p1_error = abs(expert["power_r1_mw"] - llm["power_r1_mw"]) / expert["power_r1_mw"] if expert["power_r1_mw"] != 0 else 0
        p2_error = abs(expert["power_r2_mw"] - llm["power_r2_mw"]) / expert["power_r2_mw"] if expert["power_r2_mw"] != 0 else 0
        power_errors.append((p1_error + p2_error) / 2 * 100)
        
        # Совпадение оценок
        if result["expert"]["overall_rating"] == result["llm"]["overall_rating"]:
            rating_matches += 1
    
    print(f"\n📊 СТАТИСТИКА ТОЧНОСТИ:")
    if voltage_errors:
        print(f"Средняя ошибка напряжения: {np.mean(voltage_errors):.2f}%")
        print(f"Максимальная ошибка напряжения: {np.max(voltage_errors):.2f}%")
    
    if current_errors:
        print(f"Средняя ошибка тока: {np.mean(current_errors):.2f}%")
        print(f"Максимальная ошибка тока: {np.max(current_errors):.2f}%")
    
    if power_errors:
        print(f"Средняя ошибка мощности: {np.mean(power_errors):.2f}%")
    
    print(f"\n🎯 СОГЛАСИЕ В ОЦЕНКАХ:")
    agreement_rate = rating_matches / len(successful_analyses) * 100
    print(f"Совпадение итоговых оценок: {agreement_rate:.1f}%")
    
    return {
        "success_rate": success_rate,
        "voltage_errors": voltage_errors,
        "current_errors": current_errors,
        "power_errors": power_errors,
        "agreement_rate": agreement_rate
    }


def main():
    """Главная функция эксперимента v2.0"""
    
    print("🔬 LLM-агент для анализа электронных схем v2.0")
    print("🚀 С использованием Structured Output для надежности")
    print("=" * 60)
    
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
    
    # Создаем агента v2
    agent = CircuitAnalysisAgentV2()
    print("\n🤖 LLM-агент v2.0 создан (с Structured Output)")
    
    # Тестируем эталонный анализ
    print("\n🔬 Тест эталонного анализ:")
    test_expert = expert_analysis(test_dividers[0])
    print(json.dumps(test_expert, indent=2, ensure_ascii=False))
    
    # Проводим сравнительный анализ
    print("\n🚀 Запуск эксперимента v2.0...")
    results = []
    
    for i, divider in enumerate(test_dividers):
        print(f"\n🔄 Анализ делителя {i+1}/{len(test_dividers)}...")
        
        # Эталонный анализ
        expert_result = expert_analysis(divider)
        
        # LLM анализ v2
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
        
        if "error" in llm_result:
            print(f"❌ Ошибка в анализе делителя {i+1}: {llm_result['error']}")
        else:
            print(f"✅ Делитель {i+1} проанализирован успешно")
    
    print(f"\n🎉 Эксперимент v2.0 завершен! Проанализировано {len(results)} схем")
    
    # Анализируем результаты
    print("\n" + "="*60)
    metrics = analyze_experiment_results(results)
    
    # Сохраняем результаты
    output_file = Path("publication/experiments/voltage_divider_results_v2.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Результаты v2.0 сохранены в {output_file}")
    
    # Сравнение с v1
    if metrics:
        print(f"\n🆚 СРАВНЕНИЕ С v1.0:")
        print(f"v1.0 надежность: 20% (1/5)")
        print(f"v2.0 надежность: {metrics['success_rate']:.1f}%")
        print(f"Улучшение: {metrics['success_rate'] - 20:.1f} процентных пунктов")


if __name__ == "__main__":
    main()
