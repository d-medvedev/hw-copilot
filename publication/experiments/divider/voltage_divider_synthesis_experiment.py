#!/usr/bin/env python3
"""
LLM-агент для синтеза схем делителей напряжения
Эксперимент: Синтез схемы делителя напряжения по заданным требованиям
"""

import json
import re
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path
from dataclasses import dataclass

# Для работы с LLM
import openai
from dotenv import load_dotenv
import os

# Импортируем общие классы из существующего эксперимента
from voltage_divider_experiment_v4 import (
    DividerErrorType,
    VoltageDivider,
    RESISTANCE_CRITERIA,
    ERROR_TYPE_DESCRIPTIONS
)

# Загружаем переменные окружения
load_dotenv()

@dataclass
class SynthesisTestCase:
    """Тестовый случай для синтеза схемы (только требования, без готовой схемы)"""
    name: str
    requirements: str
    load_info: str = ""
    bom: str = ""
    expected_solution: Optional[Dict] = None  # Эталонное решение для валидации
    description: str = ""

class NetlistParser:
    """Парсер SPICE netlist для извлечения параметров схемы"""
    
    @staticmethod
    def parse_netlist(netlist: str) -> Dict[str, Any]:
        """
        Парсинг SPICE netlist и извлечение параметров
        
        Возвращает:
        {
            "r1": float,
            "r2": float,
            "vin": float,
            "valid": bool,
            "errors": List[str]
        }
        """
        result = {
            "r1": None,
            "r2": None,
            "vin": None,
            "valid": False,
            "errors": []
        }
        
        if not netlist:
            result["errors"].append("Netlist is empty")
            return result
        
        # Извлекаем напряжение источника
        vin_pattern = r'V1\s+\w+\s+\w+\s+([\d.]+(?:[eE][+-]?\d+)?)'
        vin_match = re.search(vin_pattern, netlist, re.IGNORECASE)
        if vin_match:
            try:
                result["vin"] = float(vin_match.group(1))
            except ValueError:
                result["errors"].append(f"Invalid Vin value: {vin_match.group(1)}")
        else:
            result["errors"].append("Vin source (V1) not found")
        
        # Извлекаем R1
        r1_pattern = r'R1\s+\w+\s+\w+\s+([\d.]+(?:[eE][+-]?\d+)?)'
        r1_match = re.search(r1_pattern, netlist, re.IGNORECASE)
        if r1_match:
            try:
                result["r1"] = float(r1_match.group(1))
            except ValueError:
                result["errors"].append(f"Invalid R1 value: {r1_match.group(1)}")
        else:
            result["errors"].append("R1 not found")
        
        # Извлекаем R2
        r2_pattern = r'R2\s+\w+\s+\w+\s+([\d.]+(?:[eE][+-]?\d+)?)'
        r2_match = re.search(r2_pattern, netlist, re.IGNORECASE)
        if r2_match:
            try:
                result["r2"] = float(r2_match.group(1))
            except ValueError:
                result["errors"].append(f"Invalid R2 value: {r2_match.group(1)}")
        else:
            result["errors"].append("R2 not found")
        
        # Проверяем валидность
        if result["r1"] is not None and result["r2"] is not None and result["vin"] is not None:
            if result["r1"] > 0 and result["r2"] > 0 and result["vin"] > 0:
                result["valid"] = True
            else:
                result["errors"].append("Negative or zero values found")
        
        return result
    
    @staticmethod
    def extract_from_json(response: Dict) -> Dict[str, Any]:
        """Извлечение параметров из JSON ответа LLM (поддержка разных форматов)"""
        result = {
            "r1": None,
            "r2": None,
            "vin": None,
            "valid": False,
            "errors": []
        }
        
        # Формат 1: Стандартный формат с полем "circuit"
        circuit = response.get("circuit", {})
        
        # Пробуем извлечь из поля circuit
        if "r1" in circuit:
            result["r1"] = circuit["r1"]
        if "r2" in circuit:
            result["r2"] = circuit["r2"]
        if "vin" in circuit:
            result["vin"] = circuit["vin"]
        
        # Если есть netlist в circuit, парсим его
        if "netlist" in circuit:
            netlist_str = circuit["netlist"]
            if isinstance(netlist_str, list):
                # Если netlist - массив строк, объединяем их
                netlist_str = "\n".join(netlist_str)
            netlist_result = NetlistParser.parse_netlist(netlist_str)
            if netlist_result["valid"]:
                result["r1"] = netlist_result["r1"]
                result["r2"] = netlist_result["r2"]
                result["vin"] = netlist_result["vin"]
            else:
                result["errors"].extend(netlist_result["errors"])
        
        # Формат 2: Прямые поля R1, R2 (для GPT-4o-mini и других моделей)
        if result["r1"] is None and "R1" in response:
            result["r1"] = response["R1"]
        if result["r2"] is None and "R2" in response:
            result["r2"] = response["R2"]
        if result["vin"] is None and "Vin" in response:
            result["vin"] = response["Vin"]
        
        # Формат 3: SPICE_netlist как массив или строка
        if "SPICE_netlist" in response:
            netlist = response["SPICE_netlist"]
            if isinstance(netlist, list):
                netlist_str = "\n".join(netlist)
            else:
                netlist_str = str(netlist)
            netlist_result = NetlistParser.parse_netlist(netlist_str)
            if netlist_result["valid"]:
                result["r1"] = netlist_result["r1"]
                result["r2"] = netlist_result["r2"]
                result["vin"] = netlist_result["vin"]
            else:
                result["errors"].extend(netlist_result["errors"])
        
        # Проверяем валидность
        if result["r1"] is not None and result["r2"] is not None:
            if result["r1"] > 0 and result["r2"] > 0:
                result["valid"] = True
            else:
                result["errors"].append("Negative or zero resistance values")
        
        return result

class DividerSynthesisAgent:
    """LLM-агент для синтеза схем делителей напряжения"""
    
    def __init__(self, model_name: str = "gpt-4o-2024-08-06", 
                 api_provider: str = "openrouter", 
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
        timeout_config = openai.Timeout(60.0, read=120.0)
        
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
        
        # Схема ответа для синтеза
        self.response_schema = {
            "type": "object",
            "properties": {
                "circuit": {
                    "type": "object",
                    "properties": {
                        "r1": {"type": "number", "description": "Верхний резистор в Ом"},
                        "r2": {"type": "number", "description": "Нижний резистор в Ом"},
                        "vin": {"type": "number", "description": "Входное напряжение в В"},
                        "netlist": {
                            "type": "string",
                            "description": "SPICE netlist схемы"
                        }
                    },
                    "required": ["r1", "r2", "vin", "netlist"],
                    "additionalProperties": False
                },
                "calculations": {
                    "type": "object",
                    "properties": {
                        "vout_calculated": {"type": "number"},
                        "current_ma": {"type": "number"},
                        "power_r1_mw": {"type": "number"},
                        "power_r2_mw": {"type": "number"},
                        "r_out": {"type": "number"}
                    },
                    "required": ["vout_calculated", "current_ma", "power_r1_mw", "power_r2_mw", "r_out"],
                    "additionalProperties": False
                },
                "requirements_compliance": {
                    "type": "object",
                    "properties": {
                        "meets_voltage_spec": {"type": "boolean"},
                        "meets_current_spec": {"type": "boolean"},
                        "meets_power_spec": {"type": "boolean"},
                        "meets_impedance_spec": {"type": "boolean"},
                        "overall_compliance": {"type": "boolean"}
                    },
                    "required": ["meets_voltage_spec", "meets_current_spec", "meets_power_spec", "meets_impedance_spec", "overall_compliance"],
                    "additionalProperties": False
                },
                "additional_components": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "part": {"type": "string"},
                            "description": {"type": "string"}
                        }
                    }
                },
                "rationale": {
                    "type": "string",
                    "description": "Объяснение выбора номиналов"
                }
            },
            "required": ["circuit", "calculations", "requirements_compliance", "rationale"],
            "additionalProperties": False
        }
    
    def synthesize_circuit(self, test_case: SynthesisTestCase) -> Dict:
        """Синтез схемы делителя по требованиям"""
        
        # Формируем промпт
        load_section = ""
        if test_case.load_info:
            load_section = f"""
ИНФОРМАЦИЯ О НАГРУЗКЕ:
{test_case.load_info}
"""
        
        bom_section = ""
        if test_case.bom:
            bom_section = f"""
СПЕЦИФИКАЦИЯ КОМПОНЕНТОВ (BOM):
{test_case.bom}
"""
        
        prompt = f"""Ты - опытный инженер-электронщик. Разработай схему делителя напряжения согласно техническому заданию.

ТЕХНИЧЕСКОЕ ЗАДАНИЕ:
{test_case.requirements}
{load_section}{bom_section}

ЗАДАЧА:
1. Рассчитай номиналы резисторов R1 и R2 для делителя напряжения
2. Убедись, что выходное напряжение соответствует требованиям (с учетом допусков)
3. Проверь, что ток не превышает максимальный (если указан)
4. Проверь, что мощность на резисторах не превышает допустимую (если указана)
5. Учти требования к выходному импедансу (если указаны)
6. Учти требования к работе с АЦП (если указаны)
7. Добавь защитные элементы, если требуется (TVS, диоды)
8. Учти температурные требования (если указаны)

ВАЖНЫЕ КРИТЕРИИ:

**Выбор номиналов резисторов:**
- R_total (R1 + R2) должен быть в диапазоне 1 кОм - 1 МОм для большинства применений
- R_total < 100 Ом → слишком мало (перегрев, высокий ток)
- R_total > 10 МОм → слишком много (шумы, проблемы с входными токами)
- Для батарейных применений: выбирай большие номиналы для экономии энергии
- Для работы с АЦП: ток делителя должен быть > 10 * I_input_ADC

**Выходной импеданс:**
- R_out = R1 || R2 = (R1 * R2) / (R1 + R2)
- Если требуется R_out < X, то R_out должен быть < X
- Если нагрузка имеет входное сопротивление R_load, то R_out должно быть << R_load (обычно < 0.1 * R_load)

**Мощность:**
- P_r1 = I^2 * R1
- P_r2 = I^2 * R2
- Мощность на каждом резисторе не должна превышать номинальную мощность

**Защита:**
- Если указано "защита обязательна" или "защита от перенапряжения", добавь TVS диод
- Если указаны выбросы напряжения, добавь защиту

**Температурный коэффициент:**
- Для прецизионных применений (точность < 0.1%) используй резисторы с низким ТКС (< 50 ppm/°C)
- Для обычных применений подойдут стандартные резисторы

ФОРМАТ ОТВЕТА:
1. Предоставь значения R1 и R2 в Ом
2. Создай SPICE netlist схемы в формате:
   * Voltage Divider
   V1 VIN 0 <Vin>
   R1 VIN VOUT <R1>
   R2 VOUT 0 <R2>
   .end
3. Выполни расчеты: Vout, ток, мощность, выходной импеданс
4. Проверь соответствие всем требованиям
5. Укажи дополнительные компоненты, если нужны
6. Объясни выбор номиналов

Предоставь результаты в структурированном JSON формате."""
        
        try:
            api_params = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
            }
            
            # Проверяем поддержку structured output
            supports_structured = (
                self.api_provider == "openai" or 
                "gpt" in self.model_name.lower()
            )
            
            use_structured = supports_structured
            
            if use_structured:
                api_params["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "divider_synthesis",
                        "strict": True,
                        "schema": self.response_schema
                    }
                }
            else:
                json_schema_str = json.dumps(self.response_schema, ensure_ascii=False, indent=2)
                prompt = prompt + f"\n\nКРИТИЧЕСКИ ВАЖНО: Ответь ТОЛЬКО валидным JSON объектом без дополнительного текста, комментариев или markdown разметки (без ```json или ```). JSON должен строго соответствовать следующей структуре:\n{json_schema_str}"
                api_params["messages"] = [{"role": "user", "content": prompt}]
            
            # Выполняем запрос
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
                if use_structured and ("json_schema" in error_str.lower() or "format" in error_str.lower()):
                    api_params.pop("response_format", None)
                    prompt_with_json = prompt + "\n\nВАЖНО: Ответь ТОЛЬКО валидным JSON объектом без дополнительного текста."
                    api_params["messages"] = [{"role": "user", "content": prompt_with_json}]
                    try:
                        response = self.client.chat.completions.create(**api_params)
                    except Exception as retry_error:
                        return {"error": f"Retry failed: {str(retry_error)[:200]}"}
                else:
                    return {"error": f"API error: {error_str[:200]}"}
            
            content = response.choices[0].message.content
            
            if not content or content.strip() == "":
                return {"error": "Empty response from model"}
            
            # Парсим JSON ответ
            try:
                parsed = json.loads(content)
                if not isinstance(parsed, dict):
                    return {"error": f"Response is not a JSON object: {content[:200]}"}
                return parsed
            except json.JSONDecodeError:
                # Пытаемся извлечь JSON из текста
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

def create_synthesis_test_cases() -> List[SynthesisTestCase]:
    """Создание тестовых случаев для синтеза (только требования, без готовых схем)"""
    
    test_cases = [
        # Случай 1: Базовый делитель
        SynthesisTestCase(
            name="Базовый делитель 3.3В",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 12В ±5%
            - Выходное напряжение: 3.3В ±2%
            - Максимальный ток потребления: 1мА
            - Максимальная мощность резисторов: 0.25Вт
            - Температурный диапазон: -40°C...+85°C
            """,
            expected_solution={
                "r1": 26700,
                "r2": 10000,
                "vin": 12.0,
                "vout": 3.3,
                "current_ma": 0.33
            },
            description="Простой делитель для стандартного применения"
        ),
        
        # Случай 2: Делитель для батарейного питания
        SynthesisTestCase(
            name="Батарейное питание - низкий ток",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 9В (батарея)
            - Выходное напряжение: 4.5В ±3%
            - Максимальный ток потребления: 0.1мА (для экономии батареи)
            - Время работы от батареи: >1000 часов
            """,
            expected_solution={
                "r1": 45000,
                "r2": 45000,
                "vin": 9.0,
                "vout": 4.5,
                "current_ma": 0.1
            },
            description="Делитель для батарейного устройства с низким потреблением"
        ),
        
        # Случай 3: Делитель с нагрузкой
        SynthesisTestCase(
            name="Делитель с учетом нагрузки",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 12В
            - Выходное напряжение: 5В ±1%
            - Входное сопротивление нагрузки: 10 кОм
            - Выходной импеданс делителя должен быть < 1 кОм
            """,
            load_info="""
            ИНФОРМАЦИЯ О НАГРУЗКЕ:
            - Входное сопротивление нагрузки: 10 кОм
            - Требуемый выходной импеданс делителя: < 1 кОм
            """,
            expected_solution={
                "r1": 7000,
                "r2": 5000,
                "vin": 12.0,
                "vout": 5.0,
                "r_out": 2917  # Это будет ошибка, так как > 1 кОм
            },
            description="Делитель с требованием к выходному импедансу"
        ),
        
        # Случай 4: Делитель для АЦП
        SynthesisTestCase(
            name="Делитель для АЦП",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 5В
            - Выходное напряжение: 2.5В ±0.1%
            - Подключение к АЦП микроконтроллера
            - Входной ток АЦП: 1мкА
            - Ток делителя должен быть > 10 * I_input_ADC = 10мкА
            """,
            load_info="""
            ИНФОРМАЦИЯ О НАГРУЗКЕ (АЦП):
            - Входное сопротивление: 1 МОм
            - Входной ток: 1 мкА
            - Входная емкость: 10 пФ
            - Требуемый ток делителя: > 10 * I_input_ADC = 10 мкА
            """,
            expected_solution={
                "r1": 250000,
                "r2": 250000,
                "vin": 5.0,
                "vout": 2.5,
                "current_ma": 0.01
            },
            description="Делитель для работы с АЦП"
        ),
        
        # Случай 5: Делитель с защитой
        SynthesisTestCase(
            name="Делитель с защитой от перенапряжения",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 30В (с возможными выбросами до 40В)
            - Выходное напряжение: 3.3В ±1%
            - Защита от перенапряжения: обязательна
            - Фильтрация помех: RC-фильтр на выходе
            - Применение: чувствительная аналоговая схема
            """,
            expected_solution={
                "r1": 80600,
                "r2": 10000,
                "vin": 30.0,
                "vout": 3.3
            },
            description="Делитель с обязательной защитой"
        ),
        
        # Случай 6: Прецизионный делитель
        SynthesisTestCase(
            name="Прецизионный делитель",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 5В (стабилизированное)
            - Выходное напряжение: 2.5В ±0.1%
            - Температурный диапазон: -55°C...+125°C
            - Температурный коэффициент: <50ppm/°C
            - Применение: прецизионное измерение
            """,
            bom="""
            ТРЕБОВАНИЯ К КОМПОНЕНТАМ:
            - Резисторы с низким ТКС (< 50 ppm/°C)
            - Точность резисторов: ±0.1% или лучше
            """,
            expected_solution={
                "r1": 1000,
                "r2": 1000,
                "vin": 5.0,
                "vout": 2.5
            },
            description="Прецизионный делитель с требованиями к TCR"
        ),
        
        # Случай 7: Промышленный делитель
        SynthesisTestCase(
            name="Промышленный делитель",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 24В ±10%
            - Выходное напряжение: 12В ±2%
            - Максимальная мощность резисторов: 0.25Вт
            - Применение: промышленное
            """,
            expected_solution={
                "r1": 2400,
                "r2": 2400,
                "vin": 24.0,
                "vout": 12.0
            },
            description="Промышленный делитель с ограничением мощности"
        ),
        
        # Случай 8: Делитель для IoT
        SynthesisTestCase(
            name="Делитель для IoT устройства",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 3.3В (от микроконтроллера)
            - Выходное напряжение: 1.65В ±0.5%
            - Максимальный ток: 10мкА (ультранизкое потребление)
            - Входной импеданс АЦП: >1МОм
            - Применение: батарейное устройство IoT
            """,
            expected_solution={
                "r1": 150000,
                "r2": 150000,
                "vin": 3.3,
                "vout": 1.65,
                "current_ma": 0.011
            },
            description="Делитель для IoT с ультранизким потреблением"
        ),
        
        # Случай 9: Делитель с высоким током
        SynthesisTestCase(
            name="Делитель с высоким током",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 12В
            - Выходное напряжение: 6В ±5%
            - Нагрузочная способность: 5мА
            - Максимальная мощность резисторов: 0.5Вт
            """,
            expected_solution={
                "r1": 1200,
                "r2": 1200,
                "vin": 12.0,
                "vout": 6.0,
                "current_ma": 5.0
            },
            description="Делитель с требованием к нагрузочной способности"
        ),
        
        # Случай 10: Граничный случай - минимальный ток
        SynthesisTestCase(
            name="Граничный случай - минимальный ток",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 5В
            - Выходное напряжение: 2.5В ±1%
            - Максимальный ток: 10мкА
            - Применение: работа с АЦП
            """,
            expected_solution={
                "r1": 250000,
                "r2": 250000,
                "vin": 5.0,
                "vout": 2.5,
                "current_ma": 0.01
            },
            description="Граничный случай с минимальным током"
        ),
        
        # Случай 11: Делитель с фильтром
        SynthesisTestCase(
            name="Делитель с RC-фильтром",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 12В
            - Выходное напряжение: 5В ±1%
            - Фильтрация помех: RC-фильтр на выходе обязателен
            - Частота среза фильтра: < 1 кГц
            """,
            expected_solution={
                "r1": 7000,
                "r2": 5000,
                "vin": 12.0,
                "vout": 5.0
            },
            description="Делитель с требованием RC-фильтра"
        ),
        
        # Случай 12: Делитель для высокого напряжения
        SynthesisTestCase(
            name="Делитель для высокого напряжения",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 48В (промышленное)
            - Выходное напряжение: 5В ±1%
            - Максимальная мощность резисторов: 0.5Вт
            - Защита от перенапряжения: обязательна
            """,
            expected_solution={
                "r1": 43000,
                "r2": 5000,
                "vin": 48.0,
                "vout": 5.0
            },
            description="Делитель для высокого напряжения с защитой"
        ),
        
        # Случай 13: Делитель с точным соотношением
        SynthesisTestCase(
            name="Делитель с точным соотношением",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 15В
            - Выходное напряжение: 10В ±1%
            - Соотношение делителя: 2:3 (R1:R2)
            - Точность: высокая (резисторы 1%)
            """,
            expected_solution={
                "r1": 10000,
                "r2": 15000,
                "vin": 15.0,
                "vout": 10.0
            },
            description="Делитель с требованием к соотношению резисторов"
        ),
        
        # Случай 14: Делитель для низкого напряжения
        SynthesisTestCase(
            name="Делитель для низкого напряжения",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 1.8В
            - Выходное напряжение: 0.9В ±2%
            - Максимальный ток: 50мкА
            - Применение: низковольтная схема
            """,
            expected_solution={
                "r1": 18000,
                "r2": 18000,
                "vin": 1.8,
                "vout": 0.9,
                "current_ma": 0.05
            },
            description="Делитель для низковольтного применения"
        ),
        
        # Случай 15: Делитель с множественными требованиями
        SynthesisTestCase(
            name="Делитель с множественными требованиями",
            requirements="""
            Требования к делителю напряжения:
            - Входное напряжение: 18В ±10%
            - Выходное напряжение: 12В ±1%
            - Максимальный ток: 0.5мА
            - Максимальная мощность: 0.1Вт на резистор
            - Точность: ±0.5%
            - Температурная стабильность: ±0.05%/°C
            - Выходной импеданс должен быть < 5 кОм
            """,
            expected_solution={
                "r1": 6000,
                "r2": 12000,
                "vin": 18.0,
                "vout": 12.0,
                "current_ma": 1.0
            },
            description="Сложный случай с множественными требованиями"
        )
    ]
    
    return test_cases

def validate_synthesized_circuit(llm_response: Dict, test_case: SynthesisTestCase) -> Dict:
    """
    Валидация синтезированной схемы
    
    Возвращает:
    {
        "netlist_valid": bool,
        "calculations_correct": bool,
        "requirements_met": bool,
        "errors": List[DividerErrorType],
        "warnings": List[str],
        "metrics": {...}
    }
    """
    result = {
        "netlist_valid": False,
        "calculations_correct": False,
        "requirements_met": False,
        "errors": [],
        "warnings": [],
        "metrics": {}
    }
    
    if "error" in llm_response:
        result["warnings"].append(f"LLM error: {llm_response['error']}")
        return result
    
    # Извлекаем параметры схемы
    parser = NetlistParser()
    circuit_params = parser.extract_from_json(llm_response)
    
    if not circuit_params["valid"]:
        result["warnings"].append(f"Invalid circuit parameters: {', '.join(circuit_params['errors'])}")
        return result
    
    result["netlist_valid"] = True
    
    r1 = circuit_params["r1"]
    r2 = circuit_params["r2"]
    vin = circuit_params.get("vin", llm_response.get("circuit", {}).get("vin"))
    
    if not vin:
        result["warnings"].append("Vin not found")
        return result
    
    # Создаем объект делителя для расчетов
    divider = VoltageDivider(r1, r2, vin)
    
    # Проверяем расчеты LLM
    llm_calc = llm_response.get("calculations", {})
    actual_vout = divider.calculate_vout()
    actual_current = divider.calculate_current()
    actual_p_r1, actual_p_r2, _ = divider.calculate_power()
    actual_r_out = (r1 * r2) / (r1 + r2)
    
    # Сравниваем расчеты
    calc_errors = []
    if "vout_calculated" in llm_calc:
        vout_diff = abs(llm_calc["vout_calculated"] - actual_vout)
        if vout_diff > 0.01:  # Допуск 10мВ
            calc_errors.append(f"Vout calculation error: {vout_diff:.3f}V")
    
    if "current_ma" in llm_calc:
        current_diff = abs(llm_calc["current_ma"] / 1000 - actual_current)
        if current_diff > 0.001:  # Допуск 1мкА
            calc_errors.append(f"Current calculation error: {current_diff*1000:.3f}mA")
    
    if calc_errors:
        result["warnings"].extend(calc_errors)
    else:
        result["calculations_correct"] = True
    
    # Проверяем соответствие требованиям
    requirements_met = True
    compliance = llm_response.get("requirements_compliance", {})
    
    # Проверяем выходное напряжение
    # Извлекаем требуемое Vout из требований
    vout_match = re.search(r'Выходное напряжение:\s*([\d.]+)\s*В', test_case.requirements)
    if vout_match:
        target_vout = float(vout_match.group(1))
        tolerance_match = re.search(r'±([\d.]+)%', test_case.requirements)
        tolerance = float(tolerance_match.group(1)) / 100 if tolerance_match else 0.02
        
        vout_error = abs(actual_vout - target_vout) / target_vout
        if vout_error > tolerance:
            result["errors"].append(DividerErrorType.TYPE_1_WRONG_RATIO)
            requirements_met = False
    
    # Проверяем ток
    max_current_match = re.search(r'Максимальный ток[^:]*:\s*([\d.]+)\s*мА', test_case.requirements)
    if max_current_match:
        max_current = float(max_current_match.group(1)) / 1000
        if actual_current > max_current:
            result["errors"].append(DividerErrorType.TYPE_2_TOO_SMALL)
            requirements_met = False
    
    # Проверяем мощность
    max_power_match = re.search(r'Максимальная мощность[^:]*:\s*([\d.]+)\s*Вт', test_case.requirements)
    if max_power_match:
        max_power = float(max_power_match.group(1))
        if actual_p_r1 > max_power or actual_p_r2 > max_power:
            result["errors"].append(DividerErrorType.TYPE_6_POWER_EXCEED)
            requirements_met = False
    
    # Проверяем выходной импеданс
    impedance_match = re.search(r'Выходной импеданс[^<]*должен быть\s*<\s*([\d.]+)\s*кОм', test_case.requirements)
    if impedance_match:
        max_r_out = float(impedance_match.group(1)) * 1000
        if actual_r_out >= max_r_out:
            result["errors"].append(DividerErrorType.TYPE_4_LOAD_IGNORED)
            requirements_met = False
    
    # Проверяем ток для АЦП
    adc_current_match = re.search(r'Ток делителя должен быть\s*>\s*([\d.]+)\s*мкА', test_case.requirements)
    if adc_current_match:
        min_current = float(adc_current_match.group(1)) / 1000
        if actual_current <= min_current:
            result["errors"].append(DividerErrorType.TYPE_5_ADC_MISMATCH)
            requirements_met = False
    
    # Проверяем защиту
    if "защита" in test_case.requirements.lower() and "обязательна" in test_case.requirements.lower():
        additional_components = llm_response.get("additional_components", [])
        has_protection = any("TVS" in str(c).upper() or "диод" in str(c).lower() for c in additional_components)
        if not has_protection:
            result["errors"].append(DividerErrorType.TYPE_7_NO_PROTECTION)
            requirements_met = False
    
    # Проверяем TCR
    if "температурный коэффициент" in test_case.requirements.lower():
        tcr_match = re.search(r'<([\d.]+)\s*ppm/°C', test_case.requirements)
        if tcr_match:
            max_tcr = float(tcr_match.group(1))
            # Проверяем, указаны ли резисторы с низким ТКС в BOM или rationale
            rationale = llm_response.get("rationale", "").lower()
            if "tcr" not in rationale and "температурный" not in rationale:
                result["warnings"].append("TCR requirements may not be addressed")
    
    # Проверяем критерии сопротивления
    r_total = r1 + r2
    
    # Type 2: слишком маленькие
    if r_total < RESISTANCE_CRITERIA["TYPE_2_TOO_SMALL"]["absolute_min"]:
        result["errors"].append(DividerErrorType.TYPE_2_TOO_SMALL)
        requirements_met = False
    elif r_total <= RESISTANCE_CRITERIA["TYPE_2_TOO_SMALL"]["typical_min"] and \
         actual_current > RESISTANCE_CRITERIA["TYPE_2_TOO_SMALL"]["current_threshold"]:
        result["errors"].append(DividerErrorType.TYPE_2_TOO_SMALL)
        requirements_met = False
    
    # Type 3: слишком большие
    if r_total >= RESISTANCE_CRITERIA["TYPE_3_TOO_LARGE"]["absolute_max"]:
        result["errors"].append(DividerErrorType.TYPE_3_TOO_LARGE)
        requirements_met = False
    elif r_total >= RESISTANCE_CRITERIA["TYPE_3_TOO_LARGE"]["typical_max"] and \
         actual_current < RESISTANCE_CRITERIA["TYPE_3_TOO_LARGE"]["current_threshold"]:
        result["errors"].append(DividerErrorType.TYPE_3_TOO_LARGE)
        requirements_met = False
    
    result["requirements_met"] = requirements_met
    
    # Сохраняем метрики
    result["metrics"] = {
        "r1": r1,
        "r2": r2,
        "vin": vin,
        "vout_actual": actual_vout,
        "current_ma": actual_current * 1000,
        "power_r1_mw": actual_p_r1 * 1000,
        "power_r2_mw": actual_p_r2 * 1000,
        "r_out": actual_r_out,
        "r_total": r_total
    }
    
    return result

def load_models_config(config_path: str = "models_config_extended.json") -> List[Dict]:
    """Загрузка конфигурации моделей из JSON"""
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    return config.get("models", [])

def run_synthesis_experiment_for_model(model_config: Dict, test_cases: List[SynthesisTestCase]) -> Dict:
    """Запуск эксперимента синтеза для одной модели"""
    
    model_name = model_config["name"]
    model_id = model_config["model_id"]
    provider = model_config.get("provider", "openrouter")
    api_key_env = model_config.get("api_key_env", "OPENROUTER_API_KEY")
    api_key = os.getenv(api_key_env)
    
    print(f"\n{'='*60}")
    print(f"🤖 Тестирование модели: {model_name}")
    print(f"   Model ID: {model_id}")
    print(f"   Provider: {provider}")
    print(f"{'='*60}\n")
    
    # Создаем агента
    agent = DividerSynthesisAgent(
        model_name=model_id,
        api_provider=provider,
        api_key=api_key
    )
    
    results = []
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"🔄 [{model_name}] Синтез случая {i}/{len(test_cases)}: {test_case.name}", flush=True)
        
        try:
            # Синтез схемы
            print(f"   Отправка запроса к API...", flush=True)
            llm_response = agent.synthesize_circuit(test_case)
            
            # Валидация
            validation = None
            if "error" not in llm_response:
                validation = validate_synthesized_circuit(llm_response, test_case)
                
                success = validation["netlist_valid"] and validation["requirements_met"]
                error_count = len(validation["errors"])
                print(f"✅ Синтез завершен: валидный={validation['netlist_valid']}, требования={validation['requirements_met']}, ошибок={error_count}", flush=True)
            else:
                print(f"❌ Ошибка синтеза: {llm_response.get('error')}", flush=True)
            
            # Сохраняем результат
            # Преобразуем DividerErrorType в строки для JSON сериализации
            validation_json = None
            if validation:
                validation_json = {
                    "netlist_valid": validation["netlist_valid"],
                    "calculations_correct": validation["calculations_correct"],
                    "requirements_met": validation["requirements_met"],
                    "errors": [e.value if isinstance(e, DividerErrorType) else str(e) for e in validation["errors"]],
                    "warnings": validation["warnings"],
                    "metrics": validation["metrics"]
                }
            
            results.append({
                "case_id": i,
                "test_case_info": {
                    "name": test_case.name,
                    "description": test_case.description,
                    "requirements": test_case.requirements,
                    "load_info": test_case.load_info,
                    "bom": test_case.bom
                },
                "llm_response": llm_response,
                "validation": validation_json
            })
            
        except Exception as e:
            print(f"❌ Критическая ошибка на тесте {i}: {str(e)[:200]}", flush=True)
            import traceback
            traceback.print_exc()
            results.append({
                "case_id": i,
                "test_case_info": {
                    "name": test_case.name,
                    "description": test_case.description,
                    "requirements": test_case.requirements
                },
                "llm_response": {"error": f"Exception: {str(e)[:200]}"},
                "validation": None
            })
    
    # Анализ результатов
    performance = analyze_synthesis_performance(results)
    
    return {
        "model_config": model_config,
        "results": results,
        "performance": performance
    }

def analyze_synthesis_performance(results: List[Dict]) -> Dict:
    """Анализ качества синтеза"""
    
    successful_syntheses = [r for r in results if r.get("validation") and r["validation"]["netlist_valid"]]
    
    if not successful_syntheses:
        return {"error": "Нет успешных синтезов"}
    
    # Метрики синтеза
    total_cases = len(results)
    success_count = len(successful_syntheses)
    success_rate = success_count / total_cases if total_cases > 0 else 0.0
    
    # Метрики расчетов
    calc_correct = sum(1 for r in successful_syntheses if r["validation"]["calculations_correct"])
    calc_accuracy = calc_correct / success_count if success_count > 0 else 0.0
    
    # Метрики соответствия требованиям
    requirements_met = sum(1 for r in successful_syntheses if r["validation"]["requirements_met"])
    compliance_rate = requirements_met / success_count if success_count > 0 else 0.0
    
    # Метрики ошибок
    error_type_counts = {error_type: 0 for error_type in DividerErrorType}
    total_errors = 0
    
    for result in successful_syntheses:
        validation = result["validation"]
        for error in validation["errors"]:
            if isinstance(error, DividerErrorType):
                error_type_counts[error] += 1
                total_errors += 1
    
    error_rate = total_errors / success_count if success_count > 0 else 0.0
    
    # Метрики по типам ошибок
    error_type_metrics = {}
    for error_type in DividerErrorType:
        count = error_type_counts[error_type]
        error_type_metrics[error_type.value] = {
            "count": count,
            "rate": count / success_count if success_count > 0 else 0.0
        }
    
    return {
        "overall_metrics": {
            "success_rate": success_rate,
            "calculation_accuracy": calc_accuracy,
            "requirements_compliance": compliance_rate,
            "error_rate": error_rate,
            "total_cases": total_cases,
            "successful_syntheses": success_count,
            "requirements_met": requirements_met,
            "total_errors": total_errors
        },
        "by_error_type": error_type_metrics
    }

def generate_synthesis_comparison_table(models_results: List[Dict]) -> str:
    """Генерация сравнительной таблицы результатов синтеза"""
    
    table = []
    table.append("=" * 120)
    table.append("СРАВНИТЕЛЬНАЯ ТАБЛИЦА РЕЗУЛЬТАТОВ СИНТЕЗА СХЕМ")
    table.append("=" * 120)
    table.append("")
    
    # Заголовки колонок
    header = f"{'Модель':<25} {'Группа':<15} {'Размер':<10} {'Success':<10} {'Calc Acc':<10} {'Compliance':<12} {'Error Rate':<12} {'Errors':<8}"
    table.append(header)
    table.append("-" * 120)
    
    # Данные по моделям
    for model_data in models_results:
        model_name = model_data["model_config"]["name"]
        group = model_data["model_config"]["group"]
        size = model_data["model_config"]["size"]
        
        # Обрабатываем случай, когда performance содержит ошибку
        if "error" in model_data["performance"]:
            perf = {
                "success_rate": 0.0,
                "calculation_accuracy": 0.0,
                "requirements_compliance": 0.0,
                "error_rate": 0.0,
                "total_errors": 0
            }
        else:
            perf = model_data["performance"]["overall_metrics"]
        
        row = f"{model_name:<25} {group:<15} {size:<10} {perf['success_rate']:<10.2f} {perf['calculation_accuracy']:<10.2f} {perf['requirements_compliance']:<12.2f} {perf['error_rate']:<12.2f} {perf['total_errors']:<8}"
        table.append(row)
    
    table.append("=" * 120)
    table.append("")
    
    return "\n".join(table)

def main():
    """Основная функция эксперимента"""
    
    print("🔬 LLM-агент для синтеза схем делителей напряжения")
    print("=" * 60)
    
    # Создаем тестовые случаи
    test_cases = create_synthesis_test_cases()
    print(f"\n📋 Создано тестовых случаев: {len(test_cases)}\n")
    
    # Загружаем конфигурацию моделей
    # Проверяем сначала тестовый конфиг, потом основной
    config_path = Path("models_config_test.json")
    if not config_path.exists():
        config_path = Path("models_config_extended.json")
    if not config_path.exists():
        print("❌ Файл models_config_extended.json не найден!")
        return
    
    try:
        models_config = load_models_config(str(config_path))
        if not models_config:
            print("❌ Файл models_config_extended.json пуст или не содержит моделей!")
            return
        print(f"📋 Загружено моделей для тестирования: {len(models_config)}\n")
    except Exception as e:
        print(f"❌ Ошибка при загрузке models_config_extended.json: {e}")
        return
    
    # Запускаем эксперимент для каждой модели
    models_results = []
    results_dir = Path("results/synthesis")
    results_dir.mkdir(parents=True, exist_ok=True)
    
    for model_config in models_config:
        try:
            model_result = run_synthesis_experiment_for_model(model_config, test_cases)
            models_results.append(model_result)
            
            # Сохраняем результаты для каждой модели
            model_name_safe = model_config["name"].replace(" ", "_").lower()
            model_dir = results_dir / model_name_safe
            model_dir.mkdir(exist_ok=True)
            
            # Сохраняем полные результаты
            results_file = model_dir / "synthesis_results.json"
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(model_result["results"], f, ensure_ascii=False, indent=2)
            
            # Сохраняем метрики
            metrics_file = model_dir / "synthesis_metrics.json"
            with open(metrics_file, 'w', encoding='utf-8') as f:
                json.dump(model_result["performance"], f, ensure_ascii=False, indent=2)
            
            print(f"💾 Результаты {model_config['name']} сохранены в {model_dir}\n")
            
        except Exception as e:
            print(f"❌ Ошибка при тестировании {model_config['name']}: {e}\n")
            continue
    
    # Генерируем сравнительный отчет
    if models_results:
        print("\n" + "=" * 120)
        print("📊 СРАВНИТЕЛЬНЫЙ АНАЛИЗ МОДЕЛЕЙ")
        print("=" * 120 + "\n")
        
        comparison_table = generate_synthesis_comparison_table(models_results)
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
                    "overall_metrics": mr["performance"].get("overall_metrics", {
                        "success_rate": 0.0,
                        "calculation_accuracy": 0.0,
                        "requirements_compliance": 0.0,
                        "error_rate": 0.0,
                        "total_errors": 0
                    }),
                    "by_error_type": mr["performance"].get("by_error_type", {})
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
        best_models = []
        for mr in models_results:
            perf = mr["performance"]
            if "overall_metrics" in perf:
                best_models.append((mr, perf["overall_metrics"]["success_rate"]))
        
        if best_models:
            best_model, best_success = max(best_models, key=lambda x: x[1])
            print(f"\n🏆 Лучшая модель по Success Rate: {best_model['model_config']['name']} ({best_success:.2f})")

if __name__ == "__main__":
    main()

