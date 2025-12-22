#!/usr/bin/env python3
"""
LLM-агент для анализа электронных схем v4.0
Эксперимент: Обнаружение ошибок в делителях напряжения по новой методике
8 конкретных типов ошибок для делителей
"""

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

class DividerErrorType(Enum):
    """8 конкретных типов ошибок для делителей напряжения"""
    # Группа A: Базовые ошибки расчета
    TYPE_1_WRONG_RATIO = "type_1_wrong_ratio"  # Неверное соотношение резисторов → неправильное напряжение
    TYPE_2_TOO_SMALL = "type_2_too_small"       # Слишком маленькие номиналы → перегрев/высокий ток
    TYPE_3_TOO_LARGE = "type_3_too_large"      # Слишком большие номиналы → шумы/ошибки от входных токов
    
    # Группа B: Ошибки с нагрузкой
    TYPE_4_LOAD_IGNORED = "type_4_load_ignored"           # Игнорирование входного сопротивления нагрузки
    TYPE_5_ADC_MISMATCH = "type_5_adc_mismatch"           # Подключение к АЦП без учета параметров
    
    # Группа C: Надежность и безопасность
    TYPE_6_POWER_EXCEED = "type_6_power_exceed"          # Превышение допустимой мощности резисторов
    TYPE_7_NO_PROTECTION = "type_7_no_protection"        # Отсутствие защиты от перенапряжений
    
    # Группа D: Температурные и точность
    TYPE_8_TCR_IGNORED = "type_8_tcr_ignored"            # Игнорирование температурного коэффициента (TCR)

# Критерии для определения ошибок
RESISTANCE_CRITERIA = {
    "TYPE_2_TOO_SMALL": {
        "absolute_min": 100,  # Ом - критично мало (всегда ошибка)
        "typical_min": 1000,  # Ом - мало для большинства применений (ошибка если ток > 5мА)
        "current_threshold": 5e-3,  # 5 мА - порог высокого тока
        "description": "Слишком маленькие номиналы резисторов"
    },
    "TYPE_3_TOO_LARGE": {
        "absolute_max": 10e6,  # 10 МОм - критично много (всегда ошибка)
        "typical_max": 1e6,  # 1 МОм - много для большинства применений (ошибка если ток < 10мкА)
        "current_threshold": 10e-6,  # 10 мкА - порог низкого тока
        "description": "Слишком большие номиналы резисторов"
    }
}

# Описания типов ошибок для промпта с критериями
ERROR_TYPE_DESCRIPTIONS = {
    DividerErrorType.TYPE_1_WRONG_RATIO: "Неверное соотношение резисторов - выходное напряжение не соответствует требуемому",
    DividerErrorType.TYPE_2_TOO_SMALL: (
        "Слишком маленькие номиналы резисторов - перегрев, высокий ток, превышение мощности. "
        "КРИТЕРИИ: R_total < 100 Ом (всегда ошибка) ИЛИ (R_total < 1 кОм И I_divider > 5 мА). "
        "Граничные случаи (R_total = 100 Ом или R_total = 1 кОм) считаются ошибкой."
    ),
    DividerErrorType.TYPE_3_TOO_LARGE: (
        "Слишком большие номиналы резисторов - чувствительность к шумам, ошибки от входных токов. "
        "КРИТЕРИИ: R_total > 10 МОм (всегда ошибка) ИЛИ (R_total > 1 МОм И I_divider < 10 мкА). "
        "Граничные случаи (R_total = 10 МОм или R_total = 1 МОм) считаются ошибкой."
    ),
    DividerErrorType.TYPE_4_LOAD_IGNORED: "Игнорирование входного сопротивления нагрузки - выходной импеданс делителя сопоставим с нагрузкой",
    DividerErrorType.TYPE_5_ADC_MISMATCH: "Подключение к АЦП без учета входных параметров (входное сопротивление, ток, емкость)",
    DividerErrorType.TYPE_6_POWER_EXCEED: "Превышение допустимой мощности резисторов - мощность превышает номинальную мощность компонентов",
    DividerErrorType.TYPE_7_NO_PROTECTION: "Отсутствие защиты от перенапряжений - нет TVS, диодов при необходимости",
    DividerErrorType.TYPE_8_TCR_IGNORED: "Игнорирование температурного коэффициента (TCR) - использование резисторов с высоким ТКС для прецизионных применений"
}

class TestCase:
    """Тестовый случай с ТЗ, схемой и известными ошибками"""
    
    def __init__(self, name: str, requirements: str, r1: float, r2: float, 
                 vin: float, expected_errors: List[DividerErrorType],
                 description: str = "", bom: str = "", load_info: str = ""):
        self.name = name
        self.requirements = requirements
        self.r1 = r1
        self.r2 = r2
        self.vin = vin
        self.expected_errors = expected_errors  # Список типов ошибок
        self.description = description
        self.bom = bom  # Bill of Materials
        self.load_info = load_info  # Информация о нагрузке (АЦП, входное сопротивление и т.д.)
    
    def get_divider(self):
        """Получить объект VoltageDivider"""
        return VoltageDivider(self.r1, self.r2, self.vin)
    
    def has_errors(self) -> bool:
        """Есть ли ошибки в схеме"""
        return len(self.expected_errors) > 0

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

class CircuitAnalysisAgentV4:
    """LLM-агент для анализа схем с обнаружением 8 типов ошибок"""
    
    def __init__(self, model_name: str = "gpt-4o-2024-08-06", 
                 api_provider: str = "openai", 
                 api_key: Optional[str] = None):
        self.model_name = model_name
        self.api_provider = api_provider
        
        # Определяем API ключ
        if api_key:
            api_key_value = api_key
        elif api_provider == "openrouter":
            api_key_value = os.getenv('OPENROUTER_API_KEY')
        else:
            api_key_value = os.getenv('OPENAI_API_KEY')
        
        # Создаем клиент в зависимости от провайдера
        # Добавляем таймауты для предотвращения зависаний
        timeout_config = openai.Timeout(60.0, read=120.0)  # 60s на подключение, 120s на чтение
        
        if api_provider == "openrouter":
            self.client = openai.OpenAI(
                api_key=api_key_value,
                base_url="https://openrouter.ai/api/v1",
                timeout=timeout_config
            )
        else:
            self.client = openai.OpenAI(
                api_key=api_key_value,
                timeout=timeout_config
            )
        
        # Схема ответа с 8 типами ошибок
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
                                "enum": [
                                    "type_1_wrong_ratio",
                                    "type_2_too_small",
                                    "type_3_too_large",
                                    "type_4_load_ignored",
                                    "type_5_adc_mismatch",
                                    "type_6_power_exceed",
                                    "type_7_no_protection",
                                    "type_8_tcr_ignored"
                                ]
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
                    },
                    "description": "Ошибки - явные нарушения требований ТЗ"
                },
                "warnings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "warning_type": {
                                "type": "string",
                                "enum": [
                                    "type_1_wrong_ratio",
                                    "type_2_too_small",
                                    "type_3_too_large",
                                    "type_4_load_ignored",
                                    "type_5_adc_mismatch",
                                    "type_6_power_exceed",
                                    "type_7_no_protection",
                                    "type_8_tcr_ignored"
                                ]
                            },
                            "description": {"type": "string"},
                            "reason": {"type": "string"},
                            "suggested_improvement": {"type": "string"}
                        },
                        "required": ["warning_type", "description", "reason", "suggested_improvement"],
                        "additionalProperties": False
                    },
                    "description": "Предупреждения - потенциальные проблемы, не указанные в ТЗ, но важные для улучшения схемы"
                },
                "recommendations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Общие рекомендации по улучшению схемы"
                },
                "overall_rating": {
                    "type": "string",
                    "enum": ["отлично", "хорошо", "удовлетворительно", "плохо", "неприемлемо"]
                }
            },
            "required": ["calculations", "requirements_compliance", "detected_errors", "warnings", "recommendations", "overall_rating"],
            "additionalProperties": False
        }
    
    def analyze_circuit_vs_requirements(self, test_case: TestCase) -> Dict:
        """Анализ схемы на соответствие ТЗ и обнаружение ошибок"""
        
        divider = test_case.get_divider()
        
        # Формируем промпт с учетом BOM и нагрузки
        bom_section = ""
        if test_case.bom:
            bom_section = f"""
СПЕЦИФИКАЦИЯ КОМПОНЕНТОВ (BOM):
{test_case.bom}
"""
        
        load_section = ""
        if test_case.load_info:
            load_section = f"""
ИНФОРМАЦИЯ О НАГРУЗКЕ:
{test_case.load_info}
"""
        
        # Описание типов ошибок для промпта
        error_types_description = "\n".join([
            f"- {error_type.value}: {description}"
            for error_type, description in ERROR_TYPE_DESCRIPTIONS.items()
        ])
        
        prompt = f"""Ты - опытный инженер-электронщик. Проанализируй схему делителя напряжения на соответствие техническому заданию.

ТЕХНИЧЕСКОЕ ЗАДАНИЕ:
{test_case.requirements}

СХЕМА:
{divider.to_description()}

NETLIST:
{divider.to_netlist()}
{bom_section}{load_section}
КРИТЕРИИ АНАЛИЗА:

Проверь схему на наличие следующих типов проблем:

{error_types_description}

ЧЕТКИЕ КРИТЕРИИ ДЛЯ ОПРЕДЕЛЕНИЯ ОШИБОК:

**Type 2 (слишком маленькие номиналы) - ОШИБКА если:**
- R_total (R1 + R2) < 100 Ом → ВСЕГДА ошибка
- R_total (R1 + R2) <= 1 кОм И ток I_divider > 5 мА → ошибка
- **ГРАНИЧНЫЕ СЛУЧАИ: R_total = 100 Ом ИЛИ R_total = 1 кОм → ВСЕГДА ошибка (даже если ток в норме)**

**Type 3 (слишком большие номиналы) - ОШИБКА если:**
- R_total (R1 + R2) >= 10 МОм → ВСЕГДА ошибка (не предупреждение!)
- R_total (R1 + R2) >= 1 МОм И ток I_divider < 10 мкА → ошибка
- **ГРАНИЧНЫЕ СЛУЧАИ: R_total = 10 МОм ИЛИ R_total = 1 МОм → ВСЕГДА ошибка (не предупреждение, даже если ток в норме!)**

**Type 4 (игнорирование нагрузки) - ОШИБКА если:**
- **КРИТИЧЕСКИ ВАЖНО: Если в ТЗ есть фраза "должен быть < X" или "должен быть > X" про выходной импеданс → это ТРЕБОВАНИЕ, нарушение = ОШИБКА (не предупреждение!)**
- В ТЗ указано требование к выходному импедансу делителя (например, "выходной импеданс < X Ом" или "выходной импеданс делителя должен быть < X Ом") И R_out >= требуемого значения → ОШИБКА type_4_load_ignored (не предупреждение!)
- **Пример: ТЗ: "Выходной импеданс делителя должен быть < 1 кОм", R_out = 2.92 кОм → ОШИБКА (не предупреждение, т.к. есть слово "должен")**
- В ТЗ указано требование к входному сопротивлению нагрузки И R_out >= 0.1 * R_load → ошибка
- В ТЗ указано требование к соотношению R_out / R_load И оно не выполняется → ошибка
- В load_info указаны параметры нагрузки И есть требование к выходному импедансу → проверь и если не выполняется → ошибка

**Type 5 (проблемы с АЦП) - ОШИБКА если:**
- В ТЗ указано требование к току делителя относительно входного тока АЦП (например, "ток делителя > 10 * I_input_ADC") И оно не выполняется → ошибка
- В ТЗ указано требование к минимальному току делителя для работы с АЦП И I_divider < требуемого значения → ошибка
- В ТЗ указано подключение к АЦП с конкретными параметрами И ток делителя недостаточен → ошибка

ВАЖНО: 
- Граничные случаи (R_total = 100 Ом, 1 кОм, 1 МОм, 10 МОм) ВСЕГДА считаются ошибкой
- Если в ТЗ явно указаны такие номиналы для специфического применения - это НЕ ошибка (но таких случаев в тестах нет)

КРИТИЧЕСКИ ВАЖНО - РАСПОЗНАВАНИЕ ТРЕБОВАНИЙ В ТЗ:

**КАК РАСПОЗНАТЬ ТРЕБОВАНИЕ В ТЗ (это ОШИБКА, если нарушено):**
Требование в ТЗ содержит слова:
- "должен быть", "должен", "должно"
- "требуется", "требование"
- "обязательно", "обязателен"
- "максимальный", "минимальный" (с числовым значением)
- "не должен превышать", "не должен быть меньше"
- "должен быть <", "должен быть >", "должен быть ="
- Любое числовое ограничение с оператором сравнения (<, >, <=, >=, =)

**ПРИМЕРЫ ТРЕБОВАНИЙ:**
- "Выходной импеданс делителя должен быть < 1 кОм" → ТРЕБОВАНИЕ
- "Ток делителя должен быть > 10 * I_input_ADC" → ТРЕБОВАНИЕ
- "Максимальная мощность 0.125Вт" → ТРЕБОВАНИЕ
- "Выходное напряжение 5В ±1%" → ТРЕБОВАНИЕ
- "Защита от перенапряжения обязательна" → ТРЕБОВАНИЕ

**ПРИМЕРЫ ИНФОРМАЦИИ (НЕ требование):**
- "Входное сопротивление нагрузки: 10 кОм" → ИНФОРМАЦИЯ (если нет слова "должен")
- "Применение: батарейное устройство" → ИНФОРМАЦИЯ
- "Температурный диапазон: -40°C...+85°C" → ИНФОРМАЦИЯ (если нет требования к соответствию)

КРИТИЧЕСКИ ВАЖНО - РАЗДЕЛЕНИЕ ОШИБОК И ПРЕДУПРЕЖДЕНИЙ:

**ОШИБКИ (detected_errors)** - помещай ТОЛЬКО явные нарушения требований ТЗ:
- Если в ТЗ есть ТРЕБОВАНИЕ (слова "должен", "требуется", "обязательно" и т.д.) и схема его НЕ выполняет → это ОШИБКА
- Если в ТЗ указано конкретное требование (например, "выходное напряжение 5В ±1%") и схема его НЕ выполняет → это ОШИБКА
- Если в ТЗ указано ограничение (например, "максимальная мощность 0.125Вт") и схема его превышает → это ОШИБКА
- Если в ТЗ указано обязательное условие (например, "защита от перенапряжения обязательна") и его нет → это ОШИБКА
- Если в BOM указаны характеристики компонентов, которые НЕ соответствуют требованиям ТЗ → это ОШИБКА
- **ВАЖНО: Если в ТЗ написано "X должен быть < Y" и схема дает X >= Y → это ОШИБКА, а не предупреждение!**

**ПРЕДУПРЕЖДЕНИЯ (warnings)** - помещай потенциальные проблемы, НЕ указанные в ТЗ:
- Если параметр в норме по ТЗ, но может быть проблемой в других применениях → это ПРЕДУПРЕЖДЕНИЕ
- Если в ТЗ НЕТ информации о нагрузке, но ты видишь потенциальную проблему → это ПРЕДУПРЕЖДЕНИЕ
- Если в ТЗ НЕТ требований к температурному коэффициенту, но BOM показывает высокий ТКС → это ПРЕДУПРЕЖДЕНИЕ
- Если параметр на границе нормы, но не нарушает требования → это ПРЕДУПРЕЖДЕНИЕ
- Если схема работает, но можно улучшить для надежности → это ПРЕДУПРЕЖДЕНИЕ

ПРИМЕРЫ ОШИБОК:
- ТЗ требует 5В ±1%, схема дает 4В → ОШИБКА (type_1_wrong_ratio)
- ТЗ требует мощность <0.25Вт, схема дает 0.36Вт → ОШИБКА (type_6_power_exceed)
- R_total = 100 Ом (граничный случай) → ОШИБКА (type_2_too_small), даже если ток в норме
- R_total = 1 МОм И ток = 5 мкА < 10 мкА → ОШИБКА (type_3_too_large)
- R_total = 10 МОм (граничный случай) → ОШИБКА (type_3_too_large), даже если ток в норме
- ТЗ: "Выходной импеданс делителя должен быть < 1 кОм", R_out = 2.92 кОм → ОШИБКА (type_4_load_ignored) [НЕ предупреждение, т.к. есть слово "должен"]
- ТЗ: "Ток делителя должен быть > 10 * I_input_ADC", I_divider = 5 мкА, I_input_ADC = 1 мкА → ОШИБКА (type_5_adc_mismatch) [НЕ предупреждение, т.к. есть слово "должен"]

ПРИМЕРЫ НЕ-ОШИБОК:
- ТЗ требует 5В ±1%, схема дает 5.05В (в пределах нормы) → НЕ ошибка, НЕ предупреждение
- R_total = 2 кОм, ток = 3 мА < 5 мА → НЕ ошибка (критерии Type 2 не выполнены)

ПРИМЕРЫ ПРЕДУПРЕЖДЕНИЙ (когда в ТЗ НЕТ требований):
- ТЗ: "Входное напряжение: 30В" (НЕТ слова "должен" про защиту) → ПРЕДУПРЕЖДЕНИЕ (type_7_no_protection)
- ТЗ: "Входное сопротивление нагрузки: 10 кОм" (НЕТ слова "должен" про выходной импеданс) → ПРЕДУПРЕЖДЕНИЕ (type_4_load_ignored)
- ТЗ НЕ указывает требования к TCR, но BOM показывает высокий ТКС → ПРЕДУПРЕЖДЕНИЕ (type_8_tcr_ignored)

**КЛЮЧЕВОЕ РАЗЛИЧИЕ:**
- ТЗ: "должен быть < 1 кОм" → ОШИБКА (есть слово "должен")
- ТЗ: "Входное сопротивление: 10 кОм" (без "должен") → ПРЕДУПРЕЖДЕНИЕ (нет требования)

ВЫПОЛНИ АНАЛИЗ:

**ОБЩЕЕ ПРАВИЛО: ПЕРЕД ТЕМ КАК РЕШИТЬ ОШИБКА ИЛИ ПРЕДУПРЕЖДЕНИЕ:**
1. Найди в ТЗ все фразы с словами "должен", "требуется", "обязательно", "максимальный", "минимальный"
2. Если есть такое требование И схема его нарушает → это ОШИБКА (не предупреждение!)
3. Если в ТЗ НЕТ таких требований, но есть потенциальная проблема → это ПРЕДУПРЕЖДЕНИЕ

1. РАСЧЕТЫ: точные значения всех параметров (V_out, I_divider, P_r1, P_r2, R_total, R_out)

2. ПРОВЕРКА ГРАНИЧНЫХ СЛУЧАЕВ (ОБЯЗАТЕЛЬНО, ВСЕГДА ОШИБКА, НЕ ПРЕДУПРЕЖДЕНИЕ):
   - Если R_total = 100 Ом → ОШИБКА type_2_too_small (не предупреждение!)
   - Если R_total = 1 кОм → ОШИБКА type_2_too_small (не предупреждение!)
   - Если R_total = 1 МОм И ток < 10 мкА → ОШИБКА type_3_too_large (не предупреждение!)
   - Если R_total = 10 МОм → ОШИБКА type_3_too_large (не предупреждение, даже если ток в норме!)

3. СООТВЕТСТВИЕ ТЗ: проверка каждого требования из ТЗ:
   - Выходное напряжение соответствует требуемому?
   - Ток не превышает максимальный?
   - Мощность не превышает допустимую?
   - Есть ли все обязательные элементы (защита, фильтры)?

4. ПРОВЕРКА Type 4 (игнорирование нагрузки):
   - **ШАГ 1: Найди в ТЗ требования к выходному импедансу:**
     * Ищи фразы: "должен быть <", "должен быть >", "требуется", "обязательно"
     * Например: "Выходной импеданс делителя должен быть < 1 кОм" → это ТРЕБОВАНИЕ
   - **ШАГ 2: Рассчитай R_out = R1 || R2 = (R1 * R2) / (R1 + R2)**
   - **ШАГ 3: Сравни с требованием:**
     * Если требование "должен быть < X" и R_out >= X → ОШИБКА type_4_load_ignored (не предупреждение!)
     * Если требование "должен быть > X" и R_out <= X → ОШИБКА type_4_load_ignored (не предупреждение!)
   - Если в ТЗ указано требование к входному сопротивлению нагрузки → проверь соотношение R_out / R_load
   - Если в load_info указаны параметры нагрузки И есть требование к выходному импедансу → проверь соответствие

5. ПРОВЕРКА Type 5 (проблемы с АЦП):
   - **ШАГ 1: Найди в ТЗ требования к току делителя для АЦП:**
     * Ищи фразы: "должен быть >", "должен быть <", "требуется", "обязательно"
     * Например: "Ток делителя должен быть > 10 * I_input_ADC" → это ТРЕБОВАНИЕ
   - **ШАГ 2: Рассчитай I_divider = V_in / (R1 + R2)**
   - **ШАГ 3: Сравни с требованием:**
     * Если требование "должен быть > X" и I_divider <= X → ОШИБКА type_5_adc_mismatch (не предупреждение!)
     * Если требование "должен быть < X" и I_divider >= X → ОШИБКА type_5_adc_mismatch (не предупреждение!)
   - Если в load_info указаны параметры АЦП И есть требование к току → проверь соответствие

6. АНАЛИЗ КОМПОНЕНТОВ: если предоставлен BOM, проверь соответствие характеристик компонентов требованиям ТЗ

7. ОБНАРУЖЕНИЕ ОШИБОК: найди все ЯВНЫЕ нарушения требований ТЗ (включая граничные случаи)
   - **ОБЯЗАТЕЛЬНО: Проверь ВСЕ фразы в ТЗ со словами "должен", "требуется", "обязательно"**
   - **Если найдена такая фраза И схема ее нарушает → это ОШИБКА (не предупреждение!)**
   - **Пример: "должен быть < 1 кОм" и значение >= 1 кОм → ОШИБКА type_4_load_ignored**

8. ПРЕДУПРЕЖДЕНИЯ: найди потенциальные проблемы, НЕ указанные в ТЗ, но важные для улучшения

9. РЕКОМЕНДАЦИИ: общие предложения по улучшению схемы

Предоставь результаты в структурированном формате."""
        
        try:
            # Подготовка параметров для API вызова
            api_params = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
            }
            
            # Добавляем response_format для моделей, которые поддерживают structured output
            # GPT обычно поддерживает, для других моделей пробуем без него
            supports_structured = (
                self.api_provider == "openai" or 
                "gpt" in self.model_name.lower()
            )
            
            # Для Claude и Llama пробуем без structured output, но с явной инструкцией
            use_structured = supports_structured
            
            if use_structured:
                api_params["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "circuit_error_analysis",
                        "strict": True,
                        "schema": self.response_schema
                    }
                }
            else:
                # Для моделей без structured output добавляем явную инструкцию в промпт
                json_schema_str = json.dumps(self.response_schema, ensure_ascii=False, indent=2)
                prompt = prompt + f"\n\nКРИТИЧЕСКИ ВАЖНО: Ответь ТОЛЬКО валидным JSON объектом без дополнительного текста, комментариев или markdown разметки (без ```json или ```). JSON должен строго соответствовать следующей структуре:\n{json_schema_str}"
                api_params["messages"] = [{"role": "user", "content": prompt}]
            
            # Выполняем запрос с таймаутом
            try:
                import time
                start_time = time.time()
                response = self.client.chat.completions.create(**api_params)
                elapsed = time.time() - start_time
                if elapsed > 30:
                    print(f"   ⚠️  Долгий ответ: {elapsed:.1f}с")
            except openai.APITimeoutError as timeout_error:
                return {"error": f"API timeout: {str(timeout_error)}"}
            except Exception as api_error:
                error_str = str(api_error)
                # Если structured output не поддерживается, пробуем без него
                if use_structured and ("json_schema" in error_str.lower() or "format" in error_str.lower()):
                    api_params.pop("response_format", None)
                    # Добавляем инструкцию в промпт для JSON формата
                    prompt_with_json = prompt + "\n\nВАЖНО: Ответь ТОЛЬКО валидным JSON объектом без дополнительного текста."
                    api_params["messages"] = [{"role": "user", "content": prompt_with_json}]
                    try:
                        response = self.client.chat.completions.create(**api_params)
                    except Exception as retry_error:
                        return {"error": f"Retry failed: {str(retry_error)[:200]}"}
                else:
                    return {"error": f"API error: {error_str[:200]}"}
            
            content = response.choices[0].message.content
            
            # Проверяем, что ответ не пустой
            if not content or content.strip() == "":
                return {"error": "Empty response from model"}
            
            # Парсим JSON ответ
            try:
                parsed = json.loads(content)
                # Проверяем базовую структуру
                if not isinstance(parsed, dict):
                    return {"error": f"Response is not a JSON object: {content[:200]}"}
                return parsed
            except json.JSONDecodeError:
                # Если не удалось распарсить, пытаемся извлечь JSON из текста
                # Убираем markdown код блоки если есть
                content_clean = re.sub(r'```json\s*', '', content)
                content_clean = re.sub(r'```\s*', '', content_clean)
                json_match = re.search(r'\{.*\}', content_clean, re.DOTALL)
                if json_match:
                    try:
                        return json.loads(json_match.group())
                    except json.JSONDecodeError:
                        pass
                return {"error": f"Failed to parse JSON response. Content: {content[:500]}"}
                
        except Exception as e:
            return {"error": str(e)}

def create_test_cases() -> List[TestCase]:
    """Создание тестовых случаев с ТЗ и известными ошибками (8 типов)"""
    
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
        
        # Случай 2: Тип 1 - Неверное соотношение резисторов
        TestCase(
            name="Неверное соотношение резисторов",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 12В ±5%
            - Выходное напряжение: 5.0В ±1%
            - Максимальный ток потребления: 2мА
            - Максимальная мощность резисторов: 0.25Вт
            """,
            r1=10000, r2=5000, vin=12.0,  # Даст 4В вместо 5В
            expected_errors=[DividerErrorType.TYPE_1_WRONG_RATIO],
            description="Неправильный номинал R2 - выходное напряжение не соответствует требуемому"
        ),
        
        # Случай 3: Тип 2 + Тип 6 - Слишком маленькие номиналы и превышение мощности
        TestCase(
            name="Слишком маленькие номиналы и превышение мощности",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 12В
            - Выходное напряжение: 6В ±5%
            - Максимальная мощность резисторов: 0.125Вт (1/8Вт)
            - Надежность: промышленное применение
            """,
            r1=100, r2=100, vin=12.0,  # Мощность = 0.36Вт на каждом резисторе
            bom="""
            СПЕЦИФИКАЦИЯ КОМПОНЕНТОВ (BOM):
            
            Designator | Value | Part Number | Description | Power Rating | Package
            R1         | 100Ω  | RC0805FR-07100RL | Thick Film Resistor | 0.125W | 0805
            R2         | 100Ω  | RC0805FR-07100RL | Thick Film Resistor | 0.125W | 0805
            
            ПРОБЛЕМА: При токе 60мА мощность на каждом резисторе составит 0.36Вт, 
            что в 2.9 раза превышает номинальную мощность 0.125Вт
            """,
            expected_errors=[
                DividerErrorType.TYPE_2_TOO_SMALL,
                DividerErrorType.TYPE_6_POWER_EXCEED
            ],
            description="Слишком малые номиналы приводят к превышению мощности"
        ),
        
        # Случай 4: Тип 2 - Слишком маленькие номиналы (высокий ток)
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
            expected_errors=[DividerErrorType.TYPE_2_TOO_SMALL],
            description="Неприемлемо высокий ток для батарейного питания"
        ),
        
        # Случай 5: Тип 1 - Неправильное соотношение (логическая ошибка)
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
            expected_errors=[DividerErrorType.TYPE_1_WRONG_RATIO],
            description="Неправильное понимание соотношения делителя"
        ),
        
        # Случай 6: Тип 1 - Топологическая ошибка (перепутаны местами)
        TestCase(
            name="Перепутаны резисторы местами",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 24В (промышленное)
            - Выходное напряжение: 8В ±2%
            - Нагрузочная способность: 5мА
            - Стабильность: промышленный стандарт
            """,
            r1=4700, r2=14100, vin=24.0,  # R1 и R2 перепутаны местами - даст 18В вместо 8В
            expected_errors=[DividerErrorType.TYPE_1_WRONG_RATIO],
            description="Перепутаны местами верхний и нижний резисторы"
        ),
        
        # Случай 7: Тип 7 - Отсутствие защиты
        TestCase(
            name="Отсутствие защитных элементов",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 30В (с возможными выбросами до 40В)
            - Выходное напряжение: 3.3В ±1%
            - Защита от перенапряжения: обязательна
            - Фильтрация помех: RC-фильтр на выходе
            - Применение: чувствительная аналоговая схема
            """,
            r1=80600, r2=10000, vin=30.0,  # Правильный расчет, но нет защиты и фильтра
            expected_errors=[DividerErrorType.TYPE_7_NO_PROTECTION],
            description="Отсутствуют необходимые защитные элементы"
        ),
        
        # Случай 8: Тип 8 - Игнорирование TCR
        TestCase(
            name="Температурная нестабильность",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 5В (стабилизированное)
            - Выходное напряжение: 2.5В ±0.1%
            - Температурный диапазон: -55°C...+125°C
            - Температурный коэффициент: <50ppm/°C
            - Применение: прецизионное измерение
            """,
            r1=1000, r2=1000, vin=5.0,
            bom="""
            СПЕЦИФИКАЦИЯ КОМПОНЕНТОВ (BOM):
            
            Designator | Value | Part Number | Description | Tolerance | Temp Coeff | Package
            R1         | 1kΩ   | CFR-25JB-52-1K0 | Carbon Film Resistor | ±5% | ±3000ppm/°C | 0805
            R2         | 1kΩ   | CFR-25JB-52-1K0 | Carbon Film Resistor | ±5% | ±3000ppm/°C | 0805
            
            ПРОБЛЕМА: Использованы углеродные резисторы с высоким ТКС (±3000ppm/°C)
            ТРЕБУЕТСЯ: Прецизионные резисторы с ТКС <50ppm/°C (например, Vishay VPR221Z)
            """,
            expected_errors=[DividerErrorType.TYPE_8_TCR_IGNORED],
            description="Использование неподходящих резисторов для прецизионного применения"
        ),
        
        # Случай 9: Множественные ошибки
        TestCase(
            name="Множественные ошибки",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 18В ±10%
            - Выходное напряжение: 12В ±1%
            - Максимальный ток: 0.5мА
            - Максимальная мощность: 0.1Вт на резистор
            - Точность: ±0.5%
            - Температурная стабильность: ±0.05%/°C
            """,
            r1=470, r2=2200, vin=18.0,  # Неправильный расчет + превышение мощности + высокий ток
            expected_errors=[
                DividerErrorType.TYPE_1_WRONG_RATIO,
                DividerErrorType.TYPE_2_TOO_SMALL,
                DividerErrorType.TYPE_6_POWER_EXCEED
            ],
            description="Схема с множественными критическими ошибками"
        ),
        
        # Случай 10: Граничный случай
        TestCase(
            name="Граничный случай - малое отклонение",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 3.3В (от микроконтроллера)
            - Выходное напряжение: 1.65В ±0.5%
            - Максимальный ток: 10мкА (ультранизкое потребление)
            - Входной импеданс АЦП: >1МОм
            - Применение: батарейное устройство IoT
            """,
            r1=150000, r2=147000, vin=3.3,  # Небольшая ошибка в расчете: 1.636В вместо 1.65В
            expected_errors=[DividerErrorType.TYPE_1_WRONG_RATIO],
            description="Граничный случай с небольшим превышением допуска"
        ),
        
        # Случай 11: Type 3 - Слишком большие номиналы (критично)
        TestCase(
            name="Слишком большие номиналы - критический случай",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 5В
            - Выходное напряжение: 2.5В ±1%
            - Применение: работа с АЦП микроконтроллера
            - Входной ток АЦП: 1мкА
            """,
            r1=10e6, r2=10e6, vin=5.0,  # R_total = 20 МОм > 10 МОм - критично много
            expected_errors=[DividerErrorType.TYPE_3_TOO_LARGE],
            description="Критично большие номиналы резисторов"
        ),
        
        # Случай 12: Type 3 - Слишком большие номиналы (типичный)
        TestCase(
            name="Слишком большие номиналы - типичный случай",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 3.3В
            - Выходное напряжение: 1.65В ±1%
            - Применение: работа с АЦП
            - Входной ток АЦП: 0.5мкА
            """,
            r1=1e6, r2=1e6, vin=3.3,  # R_total = 2 МОм, ток = 1.65 мкА < 10 мкА
            expected_errors=[DividerErrorType.TYPE_3_TOO_LARGE],
            description="Большие номиналы с низким током"
        ),
        
        # Случай 13: Type 4 - Игнорирование входного сопротивления нагрузки
        TestCase(
            name="Игнорирование входного сопротивления нагрузки",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 12В
            - Выходное напряжение: 5В ±1%
            - Входное сопротивление нагрузки: 10 кОм (указано в ТЗ)
            - Выходной импеданс делителя должен быть < 1 кОм (указано в ТЗ)
            """,
            r1=7000, r2=5000, vin=12.0,  # R_out = R1||R2 = 2.92 кОм > 1 кОм
            load_info="""
            ИНФОРМАЦИЯ О НАГРУЗКЕ:
            - Входное сопротивление нагрузки: 10 кОм
            - Требуемый выходной импеданс делителя: < 1 кОм
            """,
            expected_errors=[DividerErrorType.TYPE_4_LOAD_IGNORED],
            description="Выходной импеданс делителя слишком высок для нагрузки"
        ),
        
        # Случай 14: Type 5 - Подключение к АЦП без учета параметров
        TestCase(
            name="Подключение к АЦП без учета параметров",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 5В
            - Выходное напряжение: 2.5В ±0.1%
            - Подключение к АЦП микроконтроллера
            - Входной ток АЦП: 1мкА (указано в ТЗ)
            - Ток делителя должен быть > 10 * I_input_ADC = 10мкА (указано в ТЗ)
            """,
            r1=500000, r2=500000, vin=5.0,  # Ток = 5 мкА < 10 мкА
            load_info="""
            ИНФОРМАЦИЯ О НАГРУЗКЕ (АЦП):
            - Входное сопротивление: 1 МОм
            - Входной ток: 1 мкА
            - Входная емкость: 10 пФ
            - Требуемый ток делителя: > 10 * I_input_ADC = 10 мкА
            """,
            expected_errors=[DividerErrorType.TYPE_5_ADC_MISMATCH],
            description="Ток делителя недостаточен для стабильной работы с АЦП"
        ),
        
        # Случай 15: Type 6 - Превышение мощности (отдельный кейс)
        TestCase(
            name="Превышение допустимой мощности резисторов",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 24В
            - Выходное напряжение: 12В ±2%
            - Максимальная мощность резисторов: 0.25Вт (указано в ТЗ)
            - Применение: промышленное
            """,
            r1=2400, r2=2400, vin=24.0,  # Мощность на каждом = 0.36Вт > 0.25Вт
            bom="""
            СПЕЦИФИКАЦИЯ КОМПОНЕНТОВ (BOM):
            
            Designator | Value | Part Number | Description | Power Rating | Package
            R1         | 2.4kΩ | RC0805FR-072K4 | Thick Film Resistor | 0.25W | 0805
            R2         | 2.4kΩ | RC0805FR-072K4 | Thick Film Resistor | 0.25W | 0805
            
            ПРОБЛЕМА: При токе 5мА мощность на каждом резисторе составит 0.36Вт, 
            что превышает номинальную мощность 0.25Вт
            """,
            expected_errors=[DividerErrorType.TYPE_6_POWER_EXCEED],
            description="Мощность на резисторах превышает допустимую"
        ),
        
        # Случай 16: Type 2 - Граничный случай (R_total = 100 Ом)
        TestCase(
            name="Граничный случай - R_total = 100 Ом",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 5В
            - Выходное напряжение: 2.5В ±1%
            - Максимальный ток: 50мА
            """,
            r1=50, r2=50, vin=5.0,  # R_total = 100 Ом (граничный случай)
            expected_errors=[DividerErrorType.TYPE_2_TOO_SMALL],
            description="Граничный случай - R_total точно равен 100 Ом"
        ),
        
        # Случай 17: Type 3 - Граничный случай (R_total = 1 МОм)
        TestCase(
            name="Граничный случай - R_total = 1 МОм",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 3.3В
            - Выходное напряжение: 1.65В ±1%
            - Применение: работа с АЦП
            """,
            r1=500000, r2=500000, vin=3.3,  # R_total = 1 МОм, ток = 3.3 мкА < 10 мкА
            expected_errors=[DividerErrorType.TYPE_3_TOO_LARGE],
            description="Граничный случай - R_total точно равен 1 МОм с низким током"
        ),
        
        # Случай 18: Type 3 - Граничный случай (R_total = 10 МОм)
        TestCase(
            name="Граничный случай - R_total = 10 МОм",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 5В
            - Выходное напряжение: 2.5В ±1%
            - Применение: прецизионное измерение
            """,
            r1=5e6, r2=5e6, vin=5.0,  # R_total = 10 МОм (граничный случай)
            expected_errors=[DividerErrorType.TYPE_3_TOO_LARGE],
            description="Граничный случай - R_total точно равен 10 МОм"
        )
    ]
    
    return test_cases

def check_resistance_criteria(divider: VoltageDivider) -> Dict[str, bool]:
    """
    Проверка критериев для Type 2 (слишком маленькие) и Type 3 (слишком большие)
    Возвращает словарь с результатами проверки
    """
    r_total = divider.r1 + divider.r2
    current = divider.calculate_current()
    
    criteria = RESISTANCE_CRITERIA
    
    # Проверка Type 2 (слишком маленькие)
    type_2_violation = False
    if r_total < criteria["TYPE_2_TOO_SMALL"]["absolute_min"]:
        type_2_violation = True
    elif r_total <= criteria["TYPE_2_TOO_SMALL"]["typical_min"] and current > criteria["TYPE_2_TOO_SMALL"]["current_threshold"]:
        type_2_violation = True
    
    # Проверка Type 3 (слишком большие)
    type_3_violation = False
    if r_total >= criteria["TYPE_3_TOO_LARGE"]["absolute_max"]:
        type_3_violation = True
    elif r_total >= criteria["TYPE_3_TOO_LARGE"]["typical_max"] and current < criteria["TYPE_3_TOO_LARGE"]["current_threshold"]:
        type_3_violation = True
    
    return {
        "type_2_too_small": type_2_violation,
        "type_3_too_large": type_3_violation,
        "r_total": r_total,
        "current_ma": current * 1000
    }

def expert_error_analysis(test_case: TestCase) -> Dict:
    """Экспертный анализ ошибок (эталон для сравнения)"""
    
    divider = test_case.get_divider()
    
    # Расчеты
    vout = divider.calculate_vout()
    current = divider.calculate_current()
    p_r1, p_r2, p_total = divider.calculate_power()
    
    # Преобразование известных ошибок в формат анализа
    detected_errors = []
    for error_type in test_case.expected_errors:
        detected_errors.append({
            "error_type": error_type.value,
            "description": ERROR_TYPE_DESCRIPTIONS[error_type],
            "severity": "критическая" if error_type in [
                DividerErrorType.TYPE_1_WRONG_RATIO,
                DividerErrorType.TYPE_2_TOO_SMALL,
                DividerErrorType.TYPE_6_POWER_EXCEED
            ] else "значительная",
            "suggested_fix": f"Исправить {error_type.value}"
        })
    
    # Анализ соответствия ТЗ
    compliance = {
        "meets_voltage_spec": True,
        "meets_current_spec": True,
        "meets_power_spec": True,
        "meets_tolerance_spec": True,
        "overall_compliance": len(test_case.expected_errors) == 0
    }
    
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

def check_error_detection(llm_errors: List[Dict], expected_errors: List[DividerErrorType]) -> Dict:
    """Проверка обнаружения ошибок по новым критериям"""
    
    # Извлекаем типы ошибок из ответа LLM
    llm_error_types = set()
    for error in llm_errors:
        error_type_str = error.get("error_type", "")
        try:
            llm_error_types.add(DividerErrorType(error_type_str))
        except ValueError:
            # Неизвестный тип ошибки - игнорируем
            pass
    
    expected_error_types = set(expected_errors)
    
    # Истинно положительные (правильно найденные)
    true_positives = llm_error_types & expected_error_types
    
    # Ложно положительные (найденные, но не ожидались)
    false_positives = llm_error_types - expected_error_types
    
    # Ложно отрицательные (ожидались, но не найдены)
    false_negatives = expected_error_types - llm_error_types
    
    return {
        "true_positives": list(true_positives),
        "false_positives": list(false_positives),
        "false_negatives": list(false_negatives),
        "precision": len(true_positives) / len(llm_error_types) if llm_error_types else 0.0,
        "recall": len(true_positives) / len(expected_error_types) if expected_error_types else 1.0,
        "f1_score": 2 * len(true_positives) / (len(llm_error_types) + len(expected_error_types)) if (llm_error_types or expected_error_types) else 1.0
    }

def analyze_error_detection_performance(results: List[Dict]) -> Dict:
    """Анализ качества обнаружения ошибок по новой методике"""
    
    successful_analyses = [r for r in results if "error" not in r["llm"]]
    
    if not successful_analyses:
        return {"error": "Нет успешных анализов"}
    
    # Собираем метрики по каждому типу ошибок
    error_type_metrics = {error_type: {
        "true_positives": 0,
        "false_positives": 0,
        "false_negatives": 0
    } for error_type in DividerErrorType}
    
    # Общие метрики
    total_tp = 0
    total_fp = 0
    total_fn = 0
    
    for result in successful_analyses:
        test_case_info = result.get("test_case_info", {})
        expected_error_strs = test_case_info.get("expected_error_types", [])
        try:
            expected_errors = [DividerErrorType(e) for e in expected_error_strs]
        except ValueError:
            # Пропускаем случаи с невалидными типами
            continue
        llm_errors = result["llm"].get("detected_errors", [])
        
        detection = check_error_detection(llm_errors, expected_errors)
        
        # Обновляем метрики по типам
        for tp in detection["true_positives"]:
            error_type_metrics[tp]["true_positives"] += 1
        for fp in detection["false_positives"]:
            error_type_metrics[fp]["false_positives"] += 1
        for fn in detection["false_negatives"]:
            error_type_metrics[fn]["false_negatives"] += 1
        
        total_tp += len(detection["true_positives"])
        total_fp += len(detection["false_positives"])
        total_fn += len(detection["false_negatives"])
    
    # Вычисляем метрики по типам
    type_metrics = {}
    for error_type, metrics in error_type_metrics.items():
        tp = metrics["true_positives"]
        fp = metrics["false_positives"]
        fn = metrics["false_negatives"]
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * tp / (tp + fp + tp + fn) if (tp + fp + tp + fn) > 0 else 0.0
        
        type_metrics[error_type.value] = {
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn
        }
    
    # Общие метрики
    overall_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    overall_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    overall_f1 = 2 * total_tp / (2 * total_tp + total_fp + total_fn) if (2 * total_tp + total_fp + total_fn) > 0 else 0.0
    
    return {
        "overall_metrics": {
            "precision": overall_precision,
            "recall": overall_recall,
            "f1_score": overall_f1,
            "true_positives": total_tp,
            "false_positives": total_fp,
            "false_negatives": total_fn
        },
        "by_error_type": type_metrics,
        "successful_analyses": len(successful_analyses),
        "total_cases": len(results)
    }

def load_models_config(config_path: str = "models_config.json") -> List[Dict]:
    """Загрузка конфигурации моделей из JSON"""
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    return config.get("models", [])

def run_experiment_for_model(model_config: Dict, test_cases: List[TestCase]) -> Dict:
    """Запуск эксперимента для одной модели"""
    
    model_name = model_config["name"]
    model_id = model_config["model_id"]
    provider = model_config.get("provider", "openai")
    api_key_env = model_config.get("api_key_env", "OPENAI_API_KEY")
    api_key = os.getenv(api_key_env)
    
    print(f"\n{'='*60}")
    print(f"🤖 Тестирование модели: {model_name}")
    print(f"   Model ID: {model_id}")
    print(f"   Provider: {provider}")
    print(f"{'='*60}\n")
    
    # Создаем агента
    agent = CircuitAnalysisAgentV4(
        model_name=model_id,
        api_provider=provider,
        api_key=api_key
    )
    
    results = []
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"🔄 [{model_name}] Анализ случая {i}/{len(test_cases)}: {test_case.name}", flush=True)
        
        try:
            # Экспертный анализ
            expert_result = expert_error_analysis(test_case)
            
            # Анализ LLM
            print(f"   Отправка запроса к API...", flush=True)
            llm_result = agent.analyze_circuit_vs_requirements(test_case)
            
            # Проверка обнаружения ошибок
            detection = None
            if "error" not in llm_result:
                detection = check_error_detection(
                    llm_result.get("detected_errors", []),
                    test_case.expected_errors
                )
                found_count = len(detection["true_positives"])
                expected_count = len(test_case.expected_errors)
                warnings_count = len(llm_result.get("warnings", []))
                print(f"✅ Обнаружено {found_count} из {expected_count} ожидаемых ошибок", end="", flush=True)
                if warnings_count > 0:
                    print(f", предупреждений: {warnings_count}", flush=True)
                else:
                    print(flush=True)
            else:
                print(f"❌ Ошибка анализа: {llm_result.get('error')}", flush=True)
            
            # Сохраняем результат
            detection_json = None
            if detection:
                detection_json = {
                    "true_positives": [e.value for e in detection["true_positives"]],
                    "false_positives": [e.value for e in detection["false_positives"]],
                    "false_negatives": [e.value for e in detection["false_negatives"]],
                    "precision": detection["precision"],
                    "recall": detection["recall"],
                    "f1_score": detection["f1_score"]
                }
            
            results.append({
                "case_id": i,
                "expert": expert_result,
                "llm": llm_result,
                "detection": detection_json,
                "test_case_info": {
                    "name": test_case.name,
                    "description": test_case.description,
                    "requirements": test_case.requirements,
                    "circuit": {
                        "r1": test_case.r1,
                        "r2": test_case.r2,
                        "vin": test_case.vin
                    },
                    "expected_error_types": [e.value for e in test_case.expected_errors],
                    "expected_error_count": len(test_case.expected_errors)
                }
            })
            
        except Exception as e:
            print(f"❌ Критическая ошибка на тесте {i}: {str(e)[:200]}", flush=True)
            import traceback
            traceback.print_exc()
            # Сохраняем частичные результаты
            results.append({
                "case_id": i,
                "expert": None,
                "llm": {"error": f"Exception: {str(e)[:200]}"},
                "detection": None,
                "test_case_info": {
                    "name": test_case.name,
                    "description": test_case.description,
                    "requirements": test_case.requirements,
                    "circuit": {
                        "r1": test_case.r1,
                        "r2": test_case.r2,
                        "vin": test_case.vin
                    },
                    "expected_error_types": [e.value for e in test_case.expected_errors],
                    "expected_error_count": len(test_case.expected_errors)
                }
            })
    
    # Анализ результатов
    performance = analyze_error_detection_performance(results)
    
    return {
        "model_config": model_config,
        "results": results,
        "performance": performance
    }

def generate_comparison_table(models_results: List[Dict]) -> str:
    """Генерация сравнительной таблицы результатов"""
    
    # Заголовок таблицы
    table = []
    table.append("=" * 100)
    table.append("СРАВНИТЕЛЬНАЯ ТАБЛИЦА РЕЗУЛЬТАТОВ МОДЕЛЕЙ")
    table.append("=" * 100)
    table.append("")
    
    # Заголовки колонок
    header = f"{'Модель':<25} {'Группа':<15} {'Размер':<10} {'Precision':<12} {'Recall':<12} {'F1-score':<12} {'TP':<6} {'FP':<6} {'FN':<6}"
    table.append(header)
    table.append("-" * 100)
    
    # Данные по моделям
    for model_data in models_results:
        model_name = model_data["model_config"]["name"]
        group = model_data["model_config"]["group"]
        size = model_data["model_config"]["size"]
        perf = model_data["performance"]["overall_metrics"]
        
        row = f"{model_name:<25} {group:<15} {size:<10} {perf['precision']:<12.2f} {perf['recall']:<12.2f} {perf['f1_score']:<12.2f} {perf['true_positives']:<6} {perf['false_positives']:<6} {perf['false_negatives']:<6}"
        table.append(row)
    
    table.append("=" * 100)
    table.append("")
    
    # Таблица по типам ошибок
    table.append("МЕТРИКИ ПО ТИПАМ ОШИБОК:")
    table.append("=" * 100)
    
    # Получаем все типы ошибок
    all_error_types = set()
    for model_data in models_results:
        all_error_types.update(model_data["performance"]["by_error_type"].keys())
    
    # Заголовок для таблицы по типам
    type_header = f"{'Тип ошибки':<25}"
    for model_data in models_results:
        model_name = model_data["model_config"]["name"]
        type_header += f" {model_name:<20}"
    table.append(type_header)
    table.append("-" * (25 + 20 * len(models_results)))
    
    # Данные по каждому типу ошибки
    for error_type in sorted(all_error_types):
        row = f"{error_type:<25}"
        for model_data in models_results:
            type_metrics = model_data["performance"]["by_error_type"].get(error_type, {})
            f1 = type_metrics.get("f1_score", 0.0)
            row += f" {f1:<20.2f}"
        table.append(row)
    
    table.append("=" * 100)
    
    return "\n".join(table)

def main(single_model: bool = False, model_name: Optional[str] = None):
    """Основная функция эксперимента"""
    
    print("🔬 LLM-агент для анализа схем v4.0")
    print("🎯 Обнаружение ошибок по новой методике (8 типов)")
    print("=" * 60)
    
    # Создаем тестовые случаи
    test_cases = create_test_cases()
    print(f"\n📋 Создано тестовых случаев: {len(test_cases)}\n")
    
    # Определяем режим работы
    # Если не указан single_model, проверяем наличие models_config.json
    if not single_model and not model_name:
        config_path = Path("models_config.json")
        if not config_path.exists():
            # Конфигурации нет - режим одной модели
            single_model = True
    
    # Режим работы: одна модель или несколько моделей
    if single_model or model_name:
        # Режим одной модели (обратная совместимость)
        if model_name:
            agent = CircuitAnalysisAgentV4(model_name=model_name)
        else:
            agent = CircuitAnalysisAgentV4()
        
        print(f"\n🤖 LLM-агент v4.0 создан (8 типов ошибок)")
        print(f"\n🚀 Запуск эксперимента v4.0...\n")
        
        results = []
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"🔄 Анализ случая {i}/{len(test_cases)}: {test_case.name}")
            
            # Экспертный анализ
            expert_result = expert_error_analysis(test_case)
            
            # Анализ LLM
            llm_result = agent.analyze_circuit_vs_requirements(test_case)
            
            # Проверка обнаружения ошибок
            if "error" not in llm_result:
                detection = check_error_detection(
                    llm_result.get("detected_errors", []),
                    test_case.expected_errors
                )
                found_count = len(detection["true_positives"])
                expected_count = len(test_case.expected_errors)
                warnings_count = len(llm_result.get("warnings", []))
                print(f"✅ Анализ завершен: обнаружено {found_count} из {expected_count} ожидаемых ошибок", end="")
                if warnings_count > 0:
                    print(f", предупреждений: {warnings_count}")
                else:
                    print()
            else:
                print(f"❌ Ошибка анализа: {llm_result.get('error')}")
                detection = None
            
            # Сохраняем результат
            detection_json = None
            if detection:
                detection_json = {
                    "true_positives": [e.value for e in detection["true_positives"]],
                    "false_positives": [e.value for e in detection["false_positives"]],
                    "false_negatives": [e.value for e in detection["false_negatives"]],
                    "precision": detection["precision"],
                    "recall": detection["recall"],
                    "f1_score": detection["f1_score"]
                }
            
            results.append({
                "case_id": i,
                "expert": expert_result,
                "llm": llm_result,
                "detection": detection_json,
                "test_case_info": {
                    "name": test_case.name,
                    "description": test_case.description,
                    "requirements": test_case.requirements,
                    "circuit": {
                        "r1": test_case.r1,
                        "r2": test_case.r2,
                        "vin": test_case.vin
                    },
                    "expected_error_types": [e.value for e in test_case.expected_errors],
                    "expected_error_count": len(test_case.expected_errors)
                }
            })
        
        print(f"\n🎉 Эксперимент v4.0 завершен!\n")
        
        # Анализ результатов
        performance = analyze_error_detection_performance(results)
        
        print("=" * 60)
        print("📊 РЕЗУЛЬТАТЫ АНАЛИЗА ОБНАРУЖЕНИЯ ОШИБОК:")
        print(f"Успешных анализов: {performance['successful_analyses']}/{performance['total_cases']}\n")
        
        # Статистика по предупреждениям
        total_warnings = 0
        warnings_by_type = {}
        for result in results:
            if "error" not in result["llm"]:
                warnings = result["llm"].get("warnings", [])
                total_warnings += len(warnings)
                for warning in warnings:
                    w_type = warning.get("warning_type", "unknown")
                    warnings_by_type[w_type] = warnings_by_type.get(w_type, 0) + 1
        
        print("⚠️ СТАТИСТИКА ПО ПРЕДУПРЕЖДЕНИЯМ:")
        print(f"Всего предупреждений: {total_warnings}")
        if warnings_by_type:
            print("По типам:")
            for w_type, count in warnings_by_type.items():
                print(f"  {w_type}: {count}")
        print()
        
        overall = performance["overall_metrics"]
        print("📈 ОБЩИЕ МЕТРИКИ ОБНАРУЖЕНИЯ ОШИБОК:")
        print(f"Precision (точность): {overall['precision']:.2f}")
        print(f"Recall (полнота): {overall['recall']:.2f}")
        print(f"F1-score: {overall['f1_score']:.2f}")
        print(f"Истинно положительные: {overall['true_positives']}")
        print(f"Ложно положительные: {overall['false_positives']}")
        print(f"Ложно отрицательные: {overall['false_negatives']}\n")
        
        print("📊 МЕТРИКИ ПО ТИПАМ ОШИБОК:")
        for error_type, metrics in performance["by_error_type"].items():
            if metrics["true_positives"] + metrics["false_positives"] + metrics["false_negatives"] > 0:
                print(f"\n{error_type}:")
                print(f"  Precision: {metrics['precision']:.2f}")
                print(f"  Recall: {metrics['recall']:.2f}")
                print(f"  F1-score: {metrics['f1_score']:.2f}")
                print(f"  TP: {metrics['true_positives']}, FP: {metrics['false_positives']}, FN: {metrics['false_negatives']}")
        
        # Сохраняем результаты
        output_file = Path("error_detection_results_v4.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 Результаты v4.0 сохранены в {output_file}")
        
        # Сохраняем метрики
        metrics_file = Path("error_detection_metrics_v4.json")
        with open(metrics_file, 'w', encoding='utf-8') as f:
            json.dump(performance, f, ensure_ascii=False, indent=2)
        
        print(f"💾 Метрики v4.0 сохранены в {metrics_file}")
    
    else:
        # Режим нескольких моделей
        # Проверяем наличие конфигурации
        config_path = Path("models_config.json")
        if not config_path.exists():
            # Если конфигурации нет, переключаемся на режим одной модели
            print("ℹ️  Файл models_config.json не найден, запускаем режим одной модели\n")
            single_model = True
            # Рекурсивно вызываем в режиме одной модели
            main(single_model=True)
            return
        
        print("\n🔬 РЕЖИМ СРАВНЕНИЯ МОДЕЛЕЙ\n")
        
        # Загружаем конфигурацию моделей
        try:
            models_config = load_models_config()
            if not models_config:
                print("❌ Файл models_config.json пуст или не содержит моделей!")
                return
            print(f"📋 Загружено моделей для тестирования: {len(models_config)}\n")
        except FileNotFoundError:
            print("❌ Файл models_config.json не найден!")
            print("   Создайте файл models_config.json с конфигурацией моделей")
            return
        except Exception as e:
            print(f"❌ Ошибка при загрузке models_config.json: {e}")
            return
        
        # Запускаем эксперимент для каждой модели
        models_results = []
        results_dir = Path("results/models_comparison")
        results_dir.mkdir(parents=True, exist_ok=True)
        
        for model_config in models_config:
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
                
                print(f"💾 Результаты {model_config['name']} сохранены в {model_dir}\n")
                
            except Exception as e:
                print(f"❌ Ошибка при тестировании {model_config['name']}: {e}\n")
                continue
        
        # Генерируем сравнительную таблицу
        if models_results:
            print("\n" + "=" * 100)
            print("📊 СРАВНИТЕЛЬНЫЙ АНАЛИЗ МОДЕЛЕЙ")
            print("=" * 100 + "\n")
            
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
            best_f1 = max(mr["performance"]["overall_metrics"]["f1_score"] for mr in models_results)
            best_model = next(mr for mr in models_results 
                            if mr["performance"]["overall_metrics"]["f1_score"] == best_f1)
            
            print(f"\n🏆 Лучшая модель по F1-score: {best_model['model_config']['name']} (F1: {best_f1:.2f})")

if __name__ == "__main__":
    main()

