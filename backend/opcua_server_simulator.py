import asyncio
import logging
import sys
import time
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta
from typing import List, Dict
import json
from pathlib import Path

from asyncua import Server, ua

# Configure logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("OPCUAServerSimulator")
logger.setLevel(logging.INFO)
logging.getLogger("asyncua").setLevel(logging.WARNING) # Suppress verbose asyncua logs


class SimulatorConfig:
    """Конфигурация симулятора"""
    def __init__(self):
        self.hanger_spawn_interval = 60  # Секунд между запуском новых подвесов
        self.bath_transition_time = 30  # Секунд на переход между ваннами
        self.bath_sequence = [3, 5, 7, 10, 17, 18, 19, 20, 31, 34]  # Порядок ванн
        self.time_in_bath = 120  # Секунд в каждой ванне
        self.max_hangers = 10  # Максимальное количество подвесов в системе
        
    def save(self, filepath: str = "simulator_config.json"):
        """Сохранить конфигурацию в файл"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                'hanger_spawn_interval': self.hanger_spawn_interval,
                'bath_transition_time': self.bath_transition_time,
                'bath_sequence': self.bath_sequence,
                'time_in_bath': self.time_in_bath,
                'max_hangers': self.max_hangers,
            }, f, indent=2)
    
    def load(self, filepath: str = "simulator_config.json"):
        """Загрузить конфигурацию из файла"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.hanger_spawn_interval = data.get('hanger_spawn_interval', 60)
                self.bath_transition_time = data.get('bath_transition_time', 30)
                self.bath_sequence = data.get('bath_sequence', [3, 5, 7, 10, 17, 18, 19, 20, 31, 34])
                self.time_in_bath = data.get('time_in_bath', 120)
                self.max_hangers = data.get('max_hangers', 10)
            return True
        except FileNotFoundError:
            return False


class ConfigDialog:
    """Диалог настройки симулятора"""
    def __init__(self):
        self.config = SimulatorConfig()
        self.config.load()  # Попытка загрузить сохраненную конфигурацию
        self.result = None
        
    def show(self):
        """Показать диалог настройки"""
        root = tk.Tk()
        root.title("OPC UA Simulator - Настройка")
        root.geometry("600x500")
        root.resizable(False, False)
        
        # Основной фрейм
        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Заголовок
        title = ttk.Label(main_frame, text="Настройка симулятора OPC UA", font=('Arial', 14, 'bold'))
        title.grid(row=0, column=0, columnspan=2, pady=(0, 20))
        
        # Интервал запуска подвесов
        ttk.Label(main_frame, text="Интервал запуска подвесов (сек):").grid(row=1, column=0, sticky=tk.W, pady=5)
        spawn_var = tk.IntVar(value=self.config.hanger_spawn_interval)
        spawn_entry = ttk.Entry(main_frame, textvariable=spawn_var, width=10)
        spawn_entry.grid(row=1, column=1, sticky=tk.W, pady=5)
        
        # Время в ванне
        ttk.Label(main_frame, text="Время в каждой ванне (сек):").grid(row=2, column=0, sticky=tk.W, pady=5)
        bath_time_var = tk.IntVar(value=self.config.time_in_bath)
        bath_time_entry = ttk.Entry(main_frame, textvariable=bath_time_var, width=10)
        bath_time_entry.grid(row=2, column=1, sticky=tk.W, pady=5)
        
        # Время перехода между ваннами
        ttk.Label(main_frame, text="Время перехода между ваннами (сек):").grid(row=3, column=0, sticky=tk.W, pady=5)
        transition_var = tk.IntVar(value=self.config.bath_transition_time)
        transition_entry = ttk.Entry(main_frame, textvariable=transition_var, width=10)
        transition_entry.grid(row=3, column=1, sticky=tk.W, pady=5)
        
        # Максимум подвесов
        ttk.Label(main_frame, text="Максимум подвесов в системе:").grid(row=4, column=0, sticky=tk.W, pady=5)
        max_hangers_var = tk.IntVar(value=self.config.max_hangers)
        max_hangers_entry = ttk.Entry(main_frame, textvariable=max_hangers_var, width=10)
        max_hangers_entry.grid(row=4, column=1, sticky=tk.W, pady=5)
        
        # Последовательность ванн
        ttk.Label(main_frame, text="Последовательность ванн:").grid(row=5, column=0, sticky=tk.W, pady=5)
        ttk.Label(main_frame, text="(через запятую, например: 3,5,7,10,17,18,19,20,31,34)", 
                 font=('Arial', 8)).grid(row=6, column=0, columnspan=2, sticky=tk.W)
        
        sequence_var = tk.StringVar(value=','.join(map(str, self.config.bath_sequence)))
        sequence_entry = ttk.Entry(main_frame, textvariable=sequence_var, width=50)
        sequence_entry.grid(row=7, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        # Информация
        info_frame = ttk.LabelFrame(main_frame, text="Информация", padding="10")
        info_frame.grid(row=8, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=20)
        
        info_text = tk.Text(info_frame, height=6, width=60, wrap=tk.WORD, font=('Arial', 9))
        info_text.insert('1.0', 
            "Симулятор будет:\n"
            "• Запускать новый подвес каждые N секунд\n"
            "• Перемещать подвесы по заданной последовательности ванн\n"
            "• Держать подвес в каждой ванне заданное время\n"
            "• Имитировать время перехода между ваннами (подвес невидим)\n"
            "• Автоматически удалять подвес после прохождения всех ванн"
        )
        info_text.config(state='disabled')
        info_text.grid(row=0, column=0)
        
        # Кнопки
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=9, column=0, columnspan=2, pady=10)
        
        def on_start():
            try:
                # Валидация
                spawn = spawn_var.get()
                bath_time = bath_time_var.get()
                transition = transition_var.get()
                max_hangers = max_hangers_var.get()
                sequence_str = sequence_var.get().strip()
                
                if spawn < 1 or bath_time < 1 or transition < 0 or max_hangers < 1:
                    messagebox.showerror("Ошибка", "Все значения должны быть положительными числами")
                    return
                
                # Парсинг последовательности ванн
                sequence = [int(x.strip()) for x in sequence_str.split(',')]
                if not sequence:
                    messagebox.showerror("Ошибка", "Последовательность ванн не может быть пустой")
                    return
                
                if any(b < 1 or b > 40 for b in sequence):
                    messagebox.showerror("Ошибка", "Номера ванн должны быть от 1 до 40")
                    return
                
                # Сохранение конфигурации
                self.config.hanger_spawn_interval = spawn
                self.config.time_in_bath = bath_time
                self.config.bath_transition_time = transition
                self.config.max_hangers = max_hangers
                self.config.bath_sequence = sequence
                self.config.save()
                
                self.result = self.config
                root.destroy()
                
            except ValueError:
                messagebox.showerror("Ошибка", "Проверьте правильность введенных данных")
        
        def on_cancel():
            root.destroy()
        
        ttk.Button(button_frame, text="Запустить симулятор", command=on_start, width=20).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Отмена", command=on_cancel, width=15).pack(side=tk.LEFT, padx=5)
        
        root.mainloop()
        return self.result


class HangerState:
    """Состояние подвеса в системе"""
    def __init__(self, hanger_id: int, bath_sequence: List[int], time_in_bath: int, transition_time: int):
        self.hanger_id = hanger_id
        self.bath_sequence = bath_sequence
        self.time_in_bath = time_in_bath
        self.transition_time = transition_time
        
        self.current_bath_index = 0
        self.state = 'in_bath'  # 'in_bath' или 'transitioning'
        self.state_start_time = datetime.now()
        
    @property
    def current_bath(self) -> int:
        """Текущая ванна"""
        if self.current_bath_index < len(self.bath_sequence):
            return self.bath_sequence[self.current_bath_index]
        return None
    
    @property
    def elapsed_time(self) -> int:
        """Прошедшее время в текущем состоянии"""
        return int((datetime.now() - self.state_start_time).total_seconds())
    
    @property
    def is_finished(self) -> bool:
        """Подвес завершил маршрут"""
        return self.current_bath_index >= len(self.bath_sequence)
    
    def update(self) -> bool:
        """Обновить состояние подвеса. Возвращает True если нужно перейти к следующей ванне"""
        if self.is_finished:
            return False
        
        elapsed = self.elapsed_time
        
        if self.state == 'in_bath':
            if elapsed >= self.time_in_bath:
                # Переход к следующей ванне
                self.state = 'transitioning'
                self.state_start_time = datetime.now()
                return True
        
        elif self.state == 'transitioning':
            if elapsed >= self.transition_time:
                # Прибыл в следующую ванну
                self.current_bath_index += 1
                self.state = 'in_bath'
                self.state_start_time = datetime.now()
                return True
        
        return False


async def run_opcua_server_simulation(config: SimulatorConfig):
    """
    Runs an OPC UA server simulation matching the real Omron PLC structure.
    Creates nodes in namespace 4 to match the real server.
    """
    server = Server()
    
    # Setup our server
    server.set_endpoint("opc.tcp://0.0.0.0:4840/freeopcua/server/")
    
    logger.info(f"Starting OPC UA Server Simulation at {server.endpoint}")
    logger.info(f"Configuration:")
    logger.info(f"  - Hanger spawn interval: {config.hanger_spawn_interval}s")
    logger.info(f"  - Time in bath: {config.time_in_bath}s")
    logger.info(f"  - Transition time: {config.bath_transition_time}s")
    logger.info(f"  - Bath sequence: {config.bath_sequence}")
    logger.info(f"  - Max hangers: {config.max_hangers}")
    
    # Initialize server first
    await server.init()
    logger.info("OPC UA Server initialized!")
    
    # Register namespaces to get to index 4
    await server.register_namespace("urn:dummy:namespace2")
    await server.register_namespace("urn:dummy:namespace3")
    idx = await server.register_namespace("urn:omron:plc:namespace")  # This should be namespace 4
    
    logger.info(f"Registered namespace index: {idx}")
    
    # Get the standard OPC UA object node
    objects = server.get_objects_node()
    
    # Create Bath array structure (40 baths as expected by the client)
    bath_vars = {}
    for bath_num in range(1, 41):
        bath_node_id = ua.NodeId(f"Bath[{bath_num}]", idx)
        bath_obj = await objects.add_object(bath_node_id, f"Bath[{bath_num}]")
        
        bath_vars[bath_num] = {
            'InUse': await bath_obj.add_variable(
                ua.NodeId(f"Bath[{bath_num}].InUse", idx), "InUse", False, varianttype=ua.VariantType.Boolean
            ),
            'Free': await bath_obj.add_variable(
                ua.NodeId(f"Bath[{bath_num}].Free", idx), "Free", True, varianttype=ua.VariantType.Boolean
            ),
            'Pallete': await bath_obj.add_variable(
                ua.NodeId(f"Bath[{bath_num}].Pallete", idx), "Pallete", 0, varianttype=ua.VariantType.UInt32
            ),
            'InTime': await bath_obj.add_variable(
                ua.NodeId(f"Bath[{bath_num}].InTime", idx), "InTime", 0, varianttype=ua.VariantType.UInt32
            ),
            'OutTime': await bath_obj.add_variable(
                ua.NodeId(f"Bath[{bath_num}].OutTime", idx), "OutTime", 0, varianttype=ua.VariantType.UInt32
            ),
            'dTime': await bath_obj.add_variable(
                ua.NodeId(f"Bath[{bath_num}].dTime", idx), "dTime", 0, varianttype=ua.VariantType.UInt32
            ),
        }
    
    # Add power supply status variables
    power_node_id = ua.NodeId("S8VK_X", idx)
    power_obj = await objects.add_object(power_node_id, "S8VK_X")
    power_vars = {
        'Status': await power_obj.add_variable(
            ua.NodeId("S8VK_X.Status", idx), "Status", True, varianttype=ua.VariantType.Boolean
        ),
        'Voltage': await power_obj.add_variable(
            ua.NodeId("S8VK_X.Voltage", idx), "Voltage", 24.0, varianttype=ua.VariantType.Float
        ),
        'Current': await power_obj.add_variable(
            ua.NodeId("S8VK_X.Current", idx), "Current", 5.0, varianttype=ua.VariantType.Float
        ),
    }
    
    # Make all variables writable
    for bath_num in range(1, 41):
        for var in bath_vars[bath_num].values():
            await var.set_writable()
    
    for var in power_vars.values():
        await var.set_writable()
    
    logger.info("All variables created and configured")

    # Start the server after all setup is complete
    await server.start()
    logger.info("OPC UA Server started and ready!")
    
    # Simulation state
    hangers: Dict[int, HangerState] = {}  # {hanger_id: HangerState}
    next_hanger_id = 1
    last_spawn_time = datetime.now()
    
    try:
        while True:
            current_time = datetime.now()
            
            # 1. Spawn new hanger if needed
            if len(hangers) < config.max_hangers:
                if (current_time - last_spawn_time).total_seconds() >= config.hanger_spawn_interval:
                    hanger = HangerState(
                        next_hanger_id,
                        config.bath_sequence,
                        config.time_in_bath,
                        config.bath_transition_time
                    )
                    hangers[next_hanger_id] = hanger
                    logger.info(f"🚀 Spawned hanger {next_hanger_id}, starting at bath {hanger.current_bath}")
                    next_hanger_id += 1
                    last_spawn_time = current_time
            
            # 2. Update all hangers
            finished_hangers = []
            for hanger_id, hanger in hangers.items():
                hanger.update()
                
                if hanger.is_finished:
                    finished_hangers.append(hanger_id)
                    logger.info(f"✅ Hanger {hanger_id} completed the route")
            
            # 3. Remove finished hangers
            for hanger_id in finished_hangers:
                del hangers[hanger_id]
            
            # 4. Clear all baths first
            for bath_num in range(1, 41):
                await bath_vars[bath_num]['InUse'].write_value(False)
                await bath_vars[bath_num]['Free'].write_value(True)
                await bath_vars[bath_num]['Pallete'].write_value(0)
                await bath_vars[bath_num]['InTime'].write_value(0)
                await bath_vars[bath_num]['OutTime'].write_value(0)
                await bath_vars[bath_num]['dTime'].write_value(0)
            
            # 5. Update baths with current hangers
            for hanger_id, hanger in hangers.items():
                if hanger.state == 'in_bath' and hanger.current_bath:
                    bath_num = hanger.current_bath
                    elapsed = hanger.elapsed_time
                    
                    await bath_vars[bath_num]['InUse'].write_value(True)
                    await bath_vars[bath_num]['Free'].write_value(False)
                    await bath_vars[bath_num]['Pallete'].write_value(hanger.hanger_id)
                    await bath_vars[bath_num]['InTime'].write_value(elapsed)
                    await bath_vars[bath_num]['OutTime'].write_value(config.time_in_bath)
                    await bath_vars[bath_num]['dTime'].write_value(elapsed)
            
            # 6. Log status every 10 seconds
            if int(current_time.timestamp()) % 10 == 0:
                active_hangers = [f"{h.hanger_id}@Bath{h.current_bath}" 
                                 for h in hangers.values() if h.state == 'in_bath']
                transitioning = [f"{h.hanger_id}→" 
                                for h in hangers.values() if h.state == 'transitioning']
                logger.info(f"📊 Active: {len(hangers)} hangers | In baths: {active_hangers} | Moving: {transitioning}")
            
            await asyncio.sleep(1)  # Update every second
            
    finally:
        logger.info("Stopping OPC UA Server...")
        await server.stop()
        logger.info("OPC UA Server stopped.")


if __name__ == "__main__":
    # Show configuration dialog
    dialog = ConfigDialog()
    config = dialog.show()
    
    if config:
        # Run simulator with configuration
        try:
            asyncio.run(run_opcua_server_simulation(config))
        except KeyboardInterrupt:
            logger.info("Simulator stopped by user (Ctrl+C)")
    else:
        logger.info("Simulator cancelled by user")
