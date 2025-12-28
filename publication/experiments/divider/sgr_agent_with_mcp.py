#!/usr/bin/env python3
"""
Интеграция SGR агента с MCP инструментом для SPICE симуляции
Позволяет агенту проверять свои расчеты через моделирование
"""

import json
import requests
import re
from typing import Dict, Optional, List
from test_sgr_agent import SGRAgentClient, SynthesisTestCase, validate_synthesized_circuit
from voltage_divider_synthesis_experiment import create_synthesis_test_cases


class SPICESimulatorClient:
    """Клиент для работы с MCP SPICE симулятором"""
    
    def __init__(self, mcp_server_url: Optional[str] = None):
        """
        Args:
            mcp_server_url: URL MCP сервера (если используется HTTP API)
                          Если None, используется локальный Python симулятор
        """
        self.mcp_server_url = mcp_server_url
        self.use_local = mcp_server_url is None
    
    def simulate_circuit(self, netlist: str, vin: Optional[float] = None) -> Dict:
        """Выполняет симуляцию схемы"""
        if self.use_local:
            return self._simulate_local(netlist, vin)
        else:
            return self._simulate_remote(netlist, vin)
    
    def _simulate_local(self, netlist: str, vin: Optional[float] = None) -> Dict:
        """Локальная Python симуляция"""
        from mcp_spice_server import SPICESimulator
        simulator = SPICESimulator()
        return simulator.simulate_dc(netlist, vin)
    
    def _simulate_remote(self, netlist: str, vin: Optional[float] = None) -> Dict:
        """Удаленная симуляция через MCP HTTP API"""
        payload = {
            "netlist": netlist
        }
        if vin is not None:
            payload["vin"] = vin
        
        try:
            response = requests.post(
                f"{self.mcp_server_url}/tools/simulate_circuit",
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e), "success": False}
    
    def validate_netlist(self, netlist: str) -> Dict:
        """Проверяет синтаксис netlist"""
        if self.use_local:
            from mcp_spice_server import SPICESimulator
            simulator = SPICESimulator()
            return simulator.validate_netlist(netlist)
        else:
            try:
                response = requests.post(
                    f"{self.mcp_server_url}/tools/validate_netlist",
                    json={"netlist": netlist},
                    timeout=5
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                return {"error": str(e), "valid": False}


class SGRAgentWithMCP:
    """SGR агент с интеграцией MCP инструмента для проверки расчетов"""
    
    def __init__(self, base_url: str = "http://89.169.178.142:8010", 
                 mcp_server_url: Optional[str] = None):
        self.sgr_client = SGRAgentClient(base_url)
        self.spice_client = SPICESimulatorClient(mcp_server_url)
    
    def synthesize_with_verification(self, test_case: SynthesisTestCase, 
                                     model: str = "sgr_agent",
                                     max_iterations: int = 3) -> Dict:
        """
        Синтезирует схему с проверкой через SPICE симуляцию
        
        Args:
            test_case: Тестовый случай
            model: Модель агента
            max_iterations: Максимальное количество итераций улучшения
        
        Returns:
            Результат синтеза с проверкой
        """
        print(f"🔄 Синтез схемы: {test_case.name}")
        
        # Первая попытка синтеза
        llm_response = self.sgr_client.synthesize_circuit(test_case, model)
        
        if "error" in llm_response:
            return {
                "synthesis": llm_response,
                "verification": None,
                "iterations": 0,
                "final_valid": False
            }
        
        # Извлекаем netlist из ответа
        netlist = self._extract_netlist(llm_response)
        
        if not netlist:
            return {
                "synthesis": llm_response,
                "verification": {"error": "Не удалось извлечь netlist"},
                "iterations": 0,
                "final_valid": False
            }
        
        # Проверяем через симуляцию
        verification_results = []
        
        for iteration in range(max_iterations):
            print(f"  📊 Итерация {iteration + 1}: проверка через SPICE симуляцию...")
            
            # Валидация netlist
            validation = self.spice_client.validate_netlist(netlist)
            if not validation.get("valid", False):
                verification_results.append({
                    "iteration": iteration + 1,
                    "validation": validation,
                    "simulation": None,
                    "needs_correction": True
                })
                break
            
            # Симуляция
            simulation = self.spice_client.simulate_circuit(netlist)
            
            if not simulation.get("success", False):
                verification_results.append({
                    "iteration": iteration + 1,
                    "validation": validation,
                    "simulation": simulation,
                    "needs_correction": True
                })
                break
            
            # Извлекаем требуемое напряжение из test_case
            vout_required = self._extract_required_vout(test_case)
            vout_tolerance = self._extract_vout_tolerance(test_case)
            
            # Проверяем соответствие требованиям
            vout_sim = simulation.get("vout", 0)
            
            # Проверяем точность
            error_percent = abs((vout_sim - vout_required) / vout_required * 100) if vout_required > 0 else 100
            
            verification_results.append({
                "iteration": iteration + 1,
                "validation": validation,
                "simulation": simulation,
                "vout_simulated": vout_sim,
                "vout_required": vout_required,
                "error_percent": error_percent,
                "needs_correction": error_percent > vout_tolerance if vout_required > 0 else False
            })
            
            # Если точность достаточна, завершаем
            if vout_required > 0 and error_percent <= vout_tolerance:
                print(f"  ✅ Точность достаточна: {error_percent:.2f}% < {vout_tolerance}%")
                break
            
            # Если нужна коррекция и есть еще итерации
            if iteration < max_iterations - 1 and vout_required > 0:
                print(f"  ⚠️  Точность недостаточна: {error_percent:.2f}% > {vout_tolerance}%")
                print(f"  🔧 Запрос коррекции у агента...")
                
                # Запрашиваем коррекцию у агента
                correction_prompt = self._create_correction_prompt(
                    test_case, llm_response, simulation, error_percent
                )
                
                correction_response = self.sgr_client.chat_completion(
                    model=model,
                    messages=[{"role": "user", "content": correction_prompt}],
                    max_tokens=1000,
                    temperature=0.1
                )
                
                # Пытаемся извлечь исправленный netlist
                new_netlist = self._extract_netlist_from_text(
                    correction_response.get("choices", [{}])[0].get("message", {}).get("content", "")
                )
                
                if new_netlist:
                    netlist = new_netlist
                    llm_response = self._update_response_with_netlist(llm_response, new_netlist)
                else:
                    print(f"  ❌ Не удалось извлечь исправленный netlist")
                    break
        
        # Финальная валидация
        final_validation = validate_synthesized_circuit(llm_response, test_case)
        
        return {
            "synthesis": llm_response,
            "verification": {
                "iterations": len(verification_results),
                "results": verification_results,
                "final_simulation": verification_results[-1].get("simulation") if verification_results else None
            },
            "final_validation": final_validation,
            "final_valid": final_validation.get("netlist_valid", False) if final_validation else False
        }
    
    def _extract_netlist(self, response: Dict) -> Optional[str]:
        """Извлекает netlist из ответа LLM"""
        # Пробуем извлечь из структурированного ответа
        if isinstance(response, dict):
            circuit = response.get("circuit", {})
            if isinstance(circuit, dict):
                netlist = circuit.get("netlist")
                if netlist:
                    return netlist
        
        # Пробуем найти в тексте
        if "raw_response" in response:
            return self._extract_netlist_from_text(response["raw_response"])
        
        return None
    
    def _extract_netlist_from_text(self, text: str) -> Optional[str]:
        """Извлекает netlist из текста"""
        # Ищем блок netlist
        patterns = [
            r'```(?:spice|netlist)?\s*\n(.*?)\n```',
            r'netlist["\']?\s*[:=]\s*["\']([^"\']+)["\']',
            r'(V1\s+\w+\s+\w+\s+[\d.]+\s*\nR1\s+\w+\s+\w+\s+[\d.]+\s*\nR2\s+\w+\s+\w+\s+[\d.]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _extract_required_vout(self, test_case: SynthesisTestCase) -> float:
        """Извлекает требуемое выходное напряжение из test_case"""
        # Пробуем из expected_solution
        if test_case.expected_solution and "vout" in test_case.expected_solution:
            return float(test_case.expected_solution["vout"])
        
        # Парсим из requirements
        import re
        vout_match = re.search(r'Выходное напряжение[:\s]+([\d.]+)\s*В', test_case.requirements, re.IGNORECASE)
        if vout_match:
            return float(vout_match.group(1))
        
        return 0.0
    
    def _extract_vout_tolerance(self, test_case: SynthesisTestCase) -> float:
        """Извлекает допустимую погрешность выходного напряжения"""
        import re
        tolerance_match = re.search(r'±([\d.]+)%', test_case.requirements)
        if tolerance_match:
            return float(tolerance_match.group(1))
        return 2.0  # По умолчанию 2%
    
    def _create_correction_prompt(self, test_case: SynthesisTestCase, 
                                  original_response: Dict,
                                  simulation: Dict,
                                  error_percent: float) -> str:
        """Создает промпт для коррекции схемы"""
        vout_sim = simulation.get("vout", 0)
        vout_req = self._extract_required_vout(test_case)
        vout_tol = self._extract_vout_tolerance(test_case)
        
        return f"""Твоя предыдущая схема делителя напряжения была проверена через SPICE симуляцию.

РЕЗУЛЬТАТЫ СИМУЛЯЦИИ:
- Выходное напряжение (симуляция): {vout_sim:.3f} В
- Требуемое напряжение: {vout_req:.3f} В
- Ошибка: {error_percent:.2f}%
- Допустимая ошибка: {vout_tol}%

ТРЕБОВАНИЯ:
{test_case.requirements}

ИСПРАВЬ схему так, чтобы выходное напряжение было ближе к требуемому значению.
Предоставь исправленный netlist и значения R1, R2."""
    
    def _update_response_with_netlist(self, response: Dict, new_netlist: str) -> Dict:
        """Обновляет ответ с новым netlist"""
        if isinstance(response, dict):
            if "circuit" not in response:
                response["circuit"] = {}
            response["circuit"]["netlist"] = new_netlist
        return response


def test_sgr_with_mcp():
    """Тест SGR агента с MCP инструментом"""
    print("🔬 Тест SGR Agent с MCP SPICE симулятором")
    print("=" * 60)
    
    # Создаем агента с MCP
    agent = SGRAgentWithMCP()
    
    # Берем один тестовый случай
    test_cases = create_synthesis_test_cases()
    test_case = test_cases[0]  # Базовый делитель 3.3В
    
    agent = SGRAgentWithMCP()
    
    print(f"\n📋 Тестовый случай: {test_case.name}")
    vout_req = agent._extract_required_vout(test_case)
    vout_tol = agent._extract_vout_tolerance(test_case)
    print(f"   Требуемое Vout: {vout_req} В ±{vout_tol}%")
    
    # Синтез с проверкой
    result = agent.synthesize_with_verification(test_case, model="sgr_agent", max_iterations=2)
    
    print(f"\n📊 РЕЗУЛЬТАТЫ:")
    print(f"   Итераций: {result['verification']['iterations']}")
    print(f"   Финальная валидность: {result['final_valid']}")
    
    if result['verification']['results']:
        last_result = result['verification']['results'][-1]
        if last_result.get('simulation'):
            sim = last_result['simulation']
            print(f"   Vout (симуляция): {sim.get('vout', 'N/A')} В")
            print(f"   Ток: {sim.get('current_ma', 'N/A')} мА")
            print(f"   Ошибка: {last_result.get('error_percent', 'N/A'):.2f}%")
    
    return result


if __name__ == "__main__":
    test_sgr_with_mcp()

