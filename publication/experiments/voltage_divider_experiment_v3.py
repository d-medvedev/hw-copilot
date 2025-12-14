#!/usr/bin/env python3
"""
LLM-агент для анализа электронных схем v3.0
Эксперимент: Обнаружение ошибок в схемах по техническому заданию
"""

import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import json
import re
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path
from enum import Enum

# Для работы с LLM
import openai
from dotenv import load_dotenv
import os

# Загружаем переменные окружения
load_dotenv()

class ErrorType(Enum):
    """Типы ошибок в схемах"""
    LOGICAL = "логическая"           # Неправильная логика работы
    TOPOLOGICAL = "топологическая"   # Неправильные соединения
    FUNCTIONAL = "функциональная"    # Не выполняет требуемую функцию
    ELECTRICAL = "электрическая"     # Нарушение электрических правил
    COMPONENT_VALUE = "номинал"      # Неправильные номиналы компонентов
    MISSING_COMPONENT = "пропущенный_элемент"  # Отсутствующие компоненты

class TestCase:
    """Тестовый случай с ТЗ, схемой и известными ошибками"""
    
    def __init__(self, name: str, requirements: str, r1: float, r2: float, 
                 vin: float, expected_errors: List[Tuple[ErrorType, str]],
                 description: str = ""):
        self.name = name
        self.requirements = requirements
        self.r1 = r1
        self.r2 = r2
        self.vin = vin
        self.expected_errors = expected_errors  # (тип_ошибки, описание)
        self.description = description
    
    def get_divider(self):
        """Получить объект VoltageDivider"""
        return VoltageDivider(self.r1, self.r2, self.vin)
    
    def has_errors(self) -> bool:
        """Есть ли ошибки в схеме"""
        return len(self.expected_errors) > 0
    
    def get_error_types(self) -> List[ErrorType]:
        """Получить типы ошибок"""
        return [error[0] for error in self.expected_errors]

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

class CircuitAnalysisAgentV3:
    """LLM-агент для анализа схем с обнаружением ошибок по ТЗ"""
    
    def __init__(self, model_name: str = "gpt-4o-2024-08-06"):
        self.model_name = model_name
        self.client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        # Расширенная схема для обнаружения ошибок
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
                "requirements_compliance": {
                    "type": "object",
                    "properties": {
                        "meets_voltage_spec": {"type": "boolean"},
                        "meets_current_spec": {"type": "boolean"},
                        "meets_power_spec": {"type": "boolean"},
                        "meets_tolerance_spec": {"type": "boolean"},
                        "overall_compliance": {"type": "boolean"}
                    },
                    "required": ["meets_voltage_spec", "meets_current_spec", "meets_power_spec", "meets_tolerance_spec", "overall_compliance"],
                    "additionalProperties": False
                },
                "detected_errors": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "error_type": {
                                "type": "string",
                                "enum": ["логическая", "топологическая", "функциональная", "электрическая", "номинал", "пропущенный_элемент"]
                            },
                            "description": {"type": "string"},
                            "severity": {
                                "type": "string", 
                                "enum": ["критическая", "значительная", "незначительная"]
                            },
                            "suggested_fix": {"type": "string"}
                        },
                        "required": ["error_type", "description", "severity", "suggested_fix"],
                        "additionalProperties": False
                    }
                },
                "recommendations": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "overall_rating": {
                    "type": "string",
                    "enum": ["отлично", "хорошо", "удовлетворительно", "плохо", "неприемлемо"]
                }
            },
            "required": ["calculations", "requirements_compliance", "detected_errors", "recommendations", "overall_rating"],
            "additionalProperties": False
        }
    
    def analyze_circuit_vs_requirements(self, test_case: TestCase) -> Dict:
        """Анализ схемы на соответствие ТЗ и обнаружение ошибок"""
        
        divider = test_case.get_divider()
        
        prompt = f"""Ты - опытный инженер-электронщик. Проанализируй схему делителя напряжения на соответствие техническому заданию и найди все ошибки.

ТЕХНИЧЕСКОЕ ЗАДАНИЕ:
{test_case.requirements}

СХЕМА:
{divider.to_description()}

NETLIST:
{divider.to_netlist()}

ЗАДАЧА АНАЛИЗА:
1. Проверь соответствие схемы всем требованиям ТЗ
2. Найди и классифицируй все ошибки по типам:
   - Логические: неправильная логика работы
   - Топологические: неправильные соединения
   - Функциональные: не выполняет требуемую функцию
   - Электрические: нарушение электрических правил
   - Номиналы: неправильные значения компонентов
   - Пропущенные элементы: отсутствующие компоненты

3. Оцени критичность каждой ошибки
4. Предложи конкретные исправления

ВЫПОЛНИ АНАЛИЗ:
1. РАСЧЕТЫ: точные значения всех параметров
2. СООТВЕТСТВИЕ ТЗ: проверка каждого требования
3. ОБНАРУЖЕНИЕ ОШИБОК: поиск и классификация
4. РЕКОМЕНДАЦИИ: конкретные предложения по исправлению

Предоставь результаты в структурированном формате."""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "circuit_error_analysis",
                        "strict": True,
                        "schema": self.response_schema
                    }
                }
            )
            
            content = response.choices[0].message.content
            return json.loads(content)
                
        except Exception as e:
            return {"error": str(e)}

def create_test_cases() -> List[TestCase]:
    """Создание тестовых случаев с ТЗ и известными ошибками"""
    
    test_cases = [
        # Случай 1: Корректная схема
        TestCase(
            name="Корректный делитель 3.3В",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 12В ±5%
            - Выходное напряжение: 3.3В ±2%
            - Максимальный ток потребления: 1мА
            - Максимальная мощность резисторов: 0.25Вт
            - Температурный диапазон: -40°C...+85°C
            """,
            r1=26700, r2=10000, vin=12.0,
            expected_errors=[],  # Нет ошибок
            description="Правильно рассчитанный делитель"
        ),
        
        # Случай 2: Ошибка номинала - неправильное выходное напряжение
        TestCase(
            name="Ошибка номинала R2",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 12В ±5%
            - Выходное напряжение: 5.0В ±1%
            - Максимальный ток потребления: 2мА
            - Максимальная мощность резисторов: 0.25Вт
            """,
            r1=10000, r2=5000, vin=12.0,  # Даст 4В вместо 5В
            expected_errors=[
                (ErrorType.COMPONENT_VALUE, "R2 имеет неправильный номинал - выходное напряжение 4В вместо требуемых 5В"),
                (ErrorType.FUNCTIONAL, "Схема не выполняет требуемую функцию получения 5В")
            ],
            description="Неправильный номинал R2"
        ),
        
        # Случай 3: Электрическая ошибка - превышение мощности
        TestCase(
            name="Превышение мощности",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 12В
            - Выходное напряжение: 6В ±5%
            - Максимальная мощность резисторов: 0.125Вт (1/8Вт)
            - Надежность: промышленное применение
            """,
            r1=100, r2=100, vin=12.0,  # Мощность = 0.36Вт на каждом резисторе
            expected_errors=[
                (ErrorType.ELECTRICAL, "Превышение максимальной мощности резисторов: 0.36Вт > 0.125Вт"),
                (ErrorType.COMPONENT_VALUE, "Слишком малые номиналы резисторов для данного напряжения")
            ],
            description="Превышение допустимой мощности"
        ),
        
        # Случай 4: Функциональная ошибка - слишком высокий ток
        TestCase(
            name="Высокий ток потребления",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 9В (батарея)
            - Выходное напряжение: 4.5В ±3%
            - Максимальный ток потребления: 0.1мА (для экономии батареи)
            - Время работы от батареи: >1000 часов
            """,
            r1=1000, r2=1000, vin=9.0,  # Ток = 4.5мА >> 0.1мА
            expected_errors=[
                (ErrorType.FUNCTIONAL, "Ток потребления 4.5мА превышает требование 0.1мА в 45 раз"),
                (ErrorType.COMPONENT_VALUE, "Номиналы резисторов слишком малы для низкого энергопотребления")
            ],
            description="Неприемлемо высокий ток для батарейного питания"
        ),
        
        # Случай 5: Логическая ошибка - неправильное соотношение
        TestCase(
            name="Неправильное соотношение делителя",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 15В
            - Выходное напряжение: 10В ±1%
            - Соотношение делителя: 2:3 (R1:R2)
            - Точность: высокая (резисторы 1%)
            """,
            r1=20000, r2=10000, vin=15.0,  # Соотношение 2:1, даст 5В вместо 10В
            expected_errors=[
                (ErrorType.LOGICAL, "Неправильное соотношение резисторов: 2:1 вместо требуемого 2:3"),
                (ErrorType.FUNCTIONAL, "Выходное напряжение 5В не соответствует требуемым 10В"),
                (ErrorType.COMPONENT_VALUE, "Номиналы не обеспечивают требуемое соотношение")
            ],
            description="Неправильное понимание соотношения делителя"
        )
    ]
    
    return test_cases

def expert_error_analysis(test_case: TestCase) -> Dict:
    """Экспертный анализ ошибок (эталон для сравнения)"""
    
    divider = test_case.get_divider()
    
    # Расчеты
    vout = divider.calculate_vout()
    current = divider.calculate_current()
    p_r1, p_r2, p_total = divider.calculate_power()
    
    # Анализ соответствия ТЗ (упрощенный)
    compliance = {
        "meets_voltage_spec": True,  # Упрощено - в реальности нужен парсинг ТЗ
        "meets_current_spec": True,
        "meets_power_spec": True,
        "meets_tolerance_spec": True,
        "overall_compliance": len(test_case.expected_errors) == 0
    }
    
    # Преобразование известных ошибок в формат анализа
    detected_errors = []
    for error_type, description in test_case.expected_errors:
        detected_errors.append({
            "error_type": error_type.value,
            "description": description,
            "severity": "критическая" if error_type in [ErrorType.ELECTRICAL, ErrorType.FUNCTIONAL] else "значительная",
            "suggested_fix": f"Исправить {error_type.value} ошибку"
        })
    
    # Общая оценка
    if len(test_case.expected_errors) == 0:
        rating = "отлично"
    elif len(test_case.expected_errors) <= 2:
        rating = "удовлетворительно"
    else:
        rating = "неприемлемо"
    
    return {
        "calculations": {
            "vout_calculated": round(vout, 3),
            "current_ma": round(current * 1000, 2),
            "power_r1_mw": round(p_r1 * 1000, 1),
            "power_r2_mw": round(p_r2 * 1000, 1)
        },
        "requirements_compliance": compliance,
        "detected_errors": detected_errors,
        "recommendations": ["Исправить обнаруженные ошибки"],
        "overall_rating": rating
    }

def analyze_error_detection_performance(results: List[Dict]) -> Dict:
    """Анализ качества обнаружения ошибок"""
    
    successful_analyses = [r for r in results if "error" not in r["llm"]]
    
    print(f"📊 РЕЗУЛЬТАТЫ АНАЛИЗА ОБНАРУЖЕНИЯ ОШИБОК:")
    print(f"Успешных анализов: {len(successful_analyses)}/{len(results)}")
    
    if not successful_analyses:
        return {"error": "Нет успешных анализов"}
    
    # Метрики обнаружения ошибок
    total_expected_errors = 0
    total_detected_errors = 0
    correct_detections = 0
    false_positives = 0
    
    print(f"\n🔍 ДЕТАЛЬНЫЙ АНАЛИЗ ПО СЛУЧАЯМ:")
    
    for result in successful_analyses:
        test_case = result["test_case"]
        expert = result["expert"]
        llm = result["llm"]
        
        expected_errors = len(expert["detected_errors"])
        detected_errors = len(llm["detected_errors"])
        
        total_expected_errors += expected_errors
        total_detected_errors += detected_errors
        
        print(f"\n📋 {test_case.name}:")
        print(f"  Ожидалось ошибок: {expected_errors}")
        print(f"  Обнаружено LLM: {detected_errors}")
        print(f"  Соответствие ТЗ: Эксперт={expert['requirements_compliance']['overall_compliance']}, LLM={llm['requirements_compliance']['overall_compliance']}")
        
        # Анализ типов ошибок
        expected_types = {err["error_type"] for err in expert["detected_errors"]}
        detected_types = {err["error_type"] for err in llm["detected_errors"]}
        
        correct_types = expected_types.intersection(detected_types)
        missed_types = expected_types - detected_types
        extra_types = detected_types - expected_types
        
        correct_detections += len(correct_types)
        false_positives += len(extra_types)
        
        if correct_types:
            print(f"  ✅ Правильно обнаружены: {', '.join(correct_types)}")
        if missed_types:
            print(f"  ❌ Пропущены: {', '.join(missed_types)}")
        if extra_types:
            print(f"  ⚠️ Ложные срабатывания: {', '.join(extra_types)}")
    
    # Общие метрики
    precision = correct_detections / total_detected_errors if total_detected_errors > 0 else 0
    recall = correct_detections / total_expected_errors if total_expected_errors > 0 else 0
    f1_score = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    
    print(f"\n📈 МЕТРИКИ ОБНАРУЖЕНИЯ ОШИБОК:")
    print(f"Precision (точность): {precision:.2f}")
    print(f"Recall (полнота): {recall:.2f}")
    print(f"F1-score: {f1_score:.2f}")
    print(f"Ложные срабатывания: {false_positives}")
    
    return {
        "precision": precision,
        "recall": recall,
        "f1_score": f1_score,
        "false_positives": false_positives,
        "total_expected": total_expected_errors,
        "total_detected": total_detected_errors
    }

def main():
    """Главная функция эксперимента v3.0 - обнаружение ошибок"""
    
    print("🔬 LLM-агент для анализа схем v3.0")
    print("🎯 Обнаружение ошибок по техническому заданию")
    print("=" * 60)
    
    # Создаем тестовые случаи
    test_cases = create_test_cases()
    
    print(f"📋 Создано тестовых случаев: {len(test_cases)}")
    for i, case in enumerate(test_cases):
        error_count = len(case.expected_errors)
        status = "✅ Корректная" if error_count == 0 else f"❌ {error_count} ошибок"
        print(f"\n{i+1}. {case.name} - {status}")
        print(f"   {case.description}")
    
    # Создаем агента v3
    agent = CircuitAnalysisAgentV3()
    print(f"\n🤖 LLM-агент v3.0 создан (обнаружение ошибок)")
    
    # Проводим анализ
    print(f"\n🚀 Запуск эксперимента v3.0...")
    results = []
    
    for i, test_case in enumerate(test_cases):
        print(f"\n🔄 Анализ случая {i+1}/{len(test_cases)}: {test_case.name}")
        
        # Экспертный анализ
        expert_result = expert_error_analysis(test_case)
        
        # LLM анализ
        llm_result = agent.analyze_circuit_vs_requirements(test_case)
        
        # Сохраняем результаты
        results.append({
            "case_id": i + 1,
            "test_case": test_case,
            "expert": expert_result,
            "llm": llm_result
        })
        
        if "error" in llm_result:
            print(f"❌ Ошибка в анализе: {llm_result['error']}")
        else:
            detected = len(llm_result["detected_errors"])
            expected = len(test_case.expected_errors)
            print(f"✅ Анализ завершен: обнаружено {detected} из {expected} ожидаемых ошибок")
    
    print(f"\n🎉 Эксперимент v3.0 завершен!")
    
    # Анализируем результаты
    print(f"\n" + "="*60)
    metrics = analyze_error_detection_performance(results)
    
    # Сохраняем результаты
    output_file = Path("publication/experiments/error_detection_results_v3.json")
    
    # Подготавливаем данные для сохранения (убираем объекты TestCase)
    results_for_save = []
    for result in results:
        result_copy = result.copy()
        test_case = result_copy.pop("test_case")
        result_copy["test_case_info"] = {
            "name": test_case.name,
            "description": test_case.description,
            "requirements": test_case.requirements,
            "circuit": {"r1": test_case.r1, "r2": test_case.r2, "vin": test_case.vin},
            "expected_error_count": len(test_case.expected_errors)
        }
        results_for_save.append(result_copy)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results_for_save, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Результаты v3.0 сохранены в {output_file}")
    
    if metrics and "error" not in metrics:
        print(f"\n🏆 ИТОГОВЫЕ МЕТРИКИ:")
        print(f"F1-score обнаружения ошибок: {metrics['f1_score']:.2f}")
        print(f"Точность (Precision): {metrics['precision']:.2f}")
        print(f"Полнота (Recall): {metrics['recall']:.2f}")

if __name__ == "__main__":
    main()
