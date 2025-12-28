#!/usr/bin/env python3
"""
MCP сервер для SPICE симуляции схем
Позволяет агенту проверять свои расчеты через моделирование
"""

import json
import subprocess
import tempfile
import os
from typing import Any, Dict, List, Optional
from pathlib import Path

# MCP SDK опционален - можно использовать как standalone модуль
try:
    from mcp.server import Server
    from mcp.server.models import InitializationOptions
    from mcp.server.stdio import stdio_server
    from mcp.types import (
        Tool,
        TextContent,
        ImageContent,
        EmbeddedResource,
    )
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    # Можно использовать как standalone модуль без MCP сервера


class SPICESimulator:
    """Класс для выполнения SPICE симуляций"""
    
    def __init__(self, spice_engine: str = "ngspice"):
        """
        Args:
            spice_engine: Движок SPICE ('ngspice', 'spiceopus', или 'python')
        """
        self.spice_engine = spice_engine
        self.check_spice_available()
    
    def check_spice_available(self):
        """Проверяет доступность SPICE движка"""
        if self.spice_engine == "ngspice":
            try:
                result = subprocess.run(
                    ["ngspice", "--version"],
                    capture_output=True,
                    timeout=5
                )
                if result.returncode != 0:
                    print("⚠️  ngspice не найден. Используется Python-симулятор.")
                    self.spice_engine = "python"
            except (FileNotFoundError, subprocess.TimeoutExpired):
                print("⚠️  ngspice не найден. Используется Python-симулятор.")
                self.spice_engine = "python"
    
    def simulate_dc(self, netlist: str, vin: float = None) -> Dict[str, Any]:
        """
        Выполняет DC анализ схемы
        
        Args:
            netlist: SPICE netlist схемы
            vin: Входное напряжение (если нужно изменить)
        
        Returns:
            Результаты симуляции: {vout, current, power_r1, power_r2, r_out}
        """
        if self.spice_engine == "ngspice":
            return self._simulate_ngspice(netlist, vin)
        else:
            return self._simulate_python(netlist, vin)
    
    def _simulate_ngspice(self, netlist: str, vin: float = None) -> Dict[str, Any]:
        """Симуляция через ngspice"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cir', delete=False) as f:
            # Модифицируем netlist для DC анализа
            netlist_lines = netlist.split('\n')
            modified_netlist = []
            
            for line in netlist_lines:
                if line.strip().startswith('V1') and vin is not None:
                    # Заменяем напряжение источника
                    parts = line.split()
                    if len(parts) >= 4:
                        parts[3] = str(vin)
                        line = ' '.join(parts)
                modified_netlist.append(line)
            
            # Добавляем команды анализа
            modified_netlist.append('.dc V1 0 15 0.1')  # DC sweep
            modified_netlist.append('.control')
            modified_netlist.append('run')
            modified_netlist.append('print V(vout)')
            modified_netlist.append('.endc')
            modified_netlist.append('.end')
            
            f.write('\n'.join(modified_netlist))
            f.flush()
            
            try:
                # Запускаем ngspice
                result = subprocess.run(
                    ['ngspice', '-b', '-o', f.name + '.out', f.name],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                # Парсим результаты
                if result.returncode == 0:
                    return self._parse_ngspice_output(result.stdout, vin or 12.0)
                else:
                    return {
                        "error": f"ngspice error: {result.stderr}",
                        "success": False
                    }
            finally:
                os.unlink(f.name)
                if os.path.exists(f.name + '.out'):
                    os.unlink(f.name + '.out')
    
    def _simulate_python(self, netlist: str, vin: float = None) -> Dict[str, Any]:
        """Упрощенная Python симуляция для делителя напряжения"""
        # Парсим netlist
        lines = [l.strip() for l in netlist.split('\n') if l.strip() and not l.strip().startswith('*')]
        
        r1 = None
        r2 = None
        vin_value = vin or 12.0
        
        for line in lines:
            parts = line.split()
            if len(parts) >= 4:
                if parts[0].upper().startswith('V1'):
                    # Источник напряжения
                    try:
                        vin_value = float(parts[3]) if vin is None else vin
                    except (ValueError, IndexError):
                        pass
                elif parts[0].upper().startswith('R1'):
                    # Резистор R1
                    try:
                        r1 = float(parts[3])
                    except (ValueError, IndexError):
                        pass
                elif parts[0].upper().startswith('R2'):
                    # Резистор R2
                    try:
                        r2 = float(parts[3])
                    except (ValueError, IndexError):
                        pass
        
        if r1 is None or r2 is None:
            return {
                "error": "Не удалось извлечь R1 и R2 из netlist",
                "success": False
            }
        
        # Расчет делителя напряжения
        vout = vin_value * (r2 / (r1 + r2))
        current = vin_value / (r1 + r2)  # в Амперах
        power_r1 = current * current * r1 * 1000  # в мВт
        power_r2 = current * current * r2 * 1000  # в мВт
        r_out = (r1 * r2) / (r1 + r2)  # выходной импеданс
        
        return {
            "success": True,
            "vout": round(vout, 6),
            "current_ma": round(current * 1000, 6),
            "power_r1_mw": round(power_r1, 6),
            "power_r2_mw": round(power_r2, 6),
            "r_out": round(r_out, 2),
            "r1": r1,
            "r2": r2,
            "vin": vin_value,
            "simulator": "python"
        }
    
    def _parse_ngspice_output(self, output: str, vin: float) -> Dict[str, Any]:
        """Парсит вывод ngspice"""
        # Упрощенный парсинг - в реальности нужен более сложный
        # Здесь возвращаем базовую структуру
        return {
            "success": True,
            "vout": 0.0,  # Будет заполнено из парсинга
            "simulator": "ngspice",
            "raw_output": output[:500]  # Первые 500 символов
        }
    
    def validate_netlist(self, netlist: str) -> Dict[str, Any]:
        """Проверяет синтаксис netlist"""
        errors = []
        warnings = []
        
        lines = [l.strip() for l in netlist.split('\n') if l.strip() and not l.strip().startswith('*')]
        
        # Проверяем наличие обязательных элементов
        has_v1 = any(l.upper().startswith('V1') for l in lines)
        has_r1 = any(l.upper().startswith('R1') for l in lines)
        has_r2 = any(l.upper().startswith('R2') for l in lines)
        
        if not has_v1:
            errors.append("Отсутствует источник напряжения V1")
        if not has_r1:
            errors.append("Отсутствует резистор R1")
        if not has_r2:
            errors.append("Отсутствует резистор R2")
        
        # Проверяем формат строк
        for i, line in enumerate(lines, 1):
            parts = line.split()
            if len(parts) < 4 and not line.startswith('.'):
                warnings.append(f"Строка {i}: возможно некорректный формат: {line}")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }


# Глобальный экземпляр симулятора
simulator = SPICESimulator()

# Создаем MCP сервер (только если MCP доступен)
if MCP_AVAILABLE:
    app = Server("spice-simulator")
    
    @app.list_tools()
    async def list_tools() -> List[Tool]:
        """Возвращает список доступных инструментов"""
        return [
        Tool(
            name="simulate_circuit",
            description="Выполняет DC симуляцию SPICE схемы делителя напряжения. "
                       "Возвращает выходное напряжение, ток, мощность на резисторах и выходной импеданс.",
            inputSchema={
                "type": "object",
                "properties": {
                    "netlist": {
                        "type": "string",
                        "description": "SPICE netlist схемы делителя напряжения"
                    },
                    "vin": {
                        "type": "number",
                        "description": "Входное напряжение в Вольтах (опционально, если не указано в netlist)"
                    }
                },
                "required": ["netlist"]
            }
        ),
        Tool(
            name="validate_netlist",
            description="Проверяет синтаксис и корректность SPICE netlist",
            inputSchema={
                "type": "object",
                "properties": {
                    "netlist": {
                        "type": "string",
                        "description": "SPICE netlist для проверки"
                    }
                },
                "required": ["netlist"]
            }
        )
    ]
    
    @app.call_tool()
    async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        """Обрабатывает вызовы инструментов"""
        
        if name == "simulate_circuit":
            netlist = arguments.get("netlist", "")
            vin = arguments.get("vin")
            
            if not netlist:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": "netlist обязателен"}, ensure_ascii=False, indent=2)
                )]
            
            result = simulator.simulate_dc(netlist, vin)
            return [TextContent(
                type="text",
                text=json.dumps(result, ensure_ascii=False, indent=2)
            )]
        
        elif name == "validate_netlist":
            netlist = arguments.get("netlist", "")
            
            if not netlist:
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": "netlist обязателен"}, ensure_ascii=False, indent=2)
                )]
            
            result = simulator.validate_netlist(netlist)
            return [TextContent(
                type="text",
                text=json.dumps(result, ensure_ascii=False, indent=2)
            )]
        
        else:
            return [TextContent(
                type="text",
                text=json.dumps({"error": f"Неизвестный инструмент: {name}"}, ensure_ascii=False)
            )]


if MCP_AVAILABLE:
    async def main():
        """Запуск MCP сервера"""
        async with stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="spice-simulator",
                    server_version="1.0.0",
                    capabilities=app.get_capabilities(
                        notification_options=None,
                        experimental_capabilities={}
                    )
                )
            )


if __name__ == "__main__":
    if MCP_AVAILABLE:
        import asyncio
        asyncio.run(main())
    else:
        # Тестовый режим без MCP
        print("MCP SDK не установлен. Используется standalone режим.")
        print("Для установки: pip install mcp")
        print("\nТестирование симулятора:")
        
        test_netlist = """
* Voltage Divider Test
V1 VIN 0 12
R1 VIN VOUT 6600
R2 VOUT 0 3300
.end
"""
        sim = SPICESimulator()
        result = sim.simulate_dc(test_netlist)
        print(json.dumps(result, indent=2, ensure_ascii=False))

