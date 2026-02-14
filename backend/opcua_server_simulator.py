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
        self.manual_recipe = []  # Сохраненный рецепт для ручного режима
        self.manual_transition_time = 30  # Время перехода для ручного режима
        
    def save(self, filepath: str = "simulator_config.json"):
        """Сохранить конфигурацию в файл"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                'hanger_spawn_interval': self.hanger_spawn_interval,
                'bath_transition_time': self.bath_transition_time,
                'bath_sequence': self.bath_sequence,
                'time_in_bath': self.time_in_bath,
                'max_hangers': self.max_hangers,
                'manual_recipe': self.manual_recipe,
                'manual_transition_time': self.manual_transition_time,
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
                self.manual_recipe = data.get('manual_recipe', [])
                self.manual_transition_time = data.get('manual_transition_time', 30)
                self.manual_recipe_times = data.get('manual_recipe_times', [])
            return True
        except FileNotFoundError:
            return False


class ManualHangerWindow:
    """Окно для запуска подвесов вручную в ручном режиме"""
    def __init__(self, manual_queue, config=None):
        self.manual_queue = manual_queue
        self.config = config
        self.root = None
        self.hanger_id_var = None
        self.transition_var = None
        self.bath_entries = []
        self.time_entries = []
        self.bath_checkboxes = []
        self.bath_saved_values = [0] * 7
        self.time_saved_values = [30] * 7
        self.transition_saved_value = 30
        self.should_exit = False  # Флаг для выхода из скрипта
        self.time_saved_values = [30] * 7
        
    def show(self):
        """Показать окно ручного режима"""
        self.root = tk.Tk()
        self.root.title("OPC UA Simulator - Ручной режим запуска подвесов")
        self.root.geometry("850x750")
        self.root.resizable(False, False)
        
        # Центрируем окно на экране
        self.root.update_idletasks()
        width = 850
        height = 750
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
        
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Заголовок
        title = ttk.Label(main_frame, text="Запуск подвеса - Ручной режим", font=('Arial', 14, 'bold'))
        title.grid(row=0, column=0, columnspan=4, pady=(0, 15))
        
        # Параметры подвеса
        params_frame = ttk.LabelFrame(main_frame, text="Параметры подвеса", padding="10")
        params_frame.grid(row=1, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=10)
        
        ttk.Label(params_frame, text="Номер подвеса:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.hanger_id_var = tk.IntVar(value=1)
        hanger_id_entry = ttk.Entry(params_frame, textvariable=self.hanger_id_var, width=10)
        hanger_id_entry.grid(row=0, column=1, sticky=tk.W, pady=5)
        
        ttk.Label(params_frame, text="Время перехода между ваннами (сек):").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.transition_var = tk.IntVar(value=30)
        transition_entry = ttk.Entry(params_frame, textvariable=self.transition_var, width=10)
        transition_entry.grid(row=1, column=1, sticky=tk.W, pady=5)
        
        # Рецепт (7 ванн с временем)
        recipe_frame = ttk.LabelFrame(main_frame, text="Рецепт (7 ванн)", padding="10")
        recipe_frame.grid(row=2, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=10)
        
        # Заголовки
        ttk.Label(recipe_frame, text="Ванна", font=('Arial', 10, 'bold')).grid(row=0, column=0, padx=5, pady=5)
        ttk.Label(recipe_frame, text="Время (сек)", font=('Arial', 10, 'bold')).grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(recipe_frame, text="Активно", font=('Arial', 9, 'bold')).grid(row=0, column=2, padx=5, pady=5)
        
        # Кнопка очистить весь рецепт (справа)
        clear_all_btn = ttk.Button(recipe_frame, text="🗑️ Очистить", command=self._clear_all_recipe, width=10)
        clear_all_btn.grid(row=0, column=3, padx=5, pady=5)
        
        # 7 строк для ванн и времени
        for i in range(7):
            ttk.Label(recipe_frame, text=f"Ванна {i+1}:").grid(row=i+1, column=0, sticky=tk.W, padx=5, pady=5)
            
            bath_var = tk.IntVar(value=0)
            bath_entry = ttk.Entry(recipe_frame, textvariable=bath_var, width=10)
            bath_entry.grid(row=i+1, column=0, sticky=tk.E, padx=5, pady=5)
            bath_entry.bind("<FocusIn>", lambda e: e.widget.select_range(0, tk.END))
            self.bath_entries.append((bath_entry, bath_var))
            
            time_var = tk.IntVar(value=30)
            time_entry = ttk.Entry(recipe_frame, textvariable=time_var, width=10)
            time_entry.grid(row=i+1, column=1, sticky=tk.W, padx=5, pady=5)
            time_entry.bind("<FocusIn>", lambda e: e.widget.select_range(0, tk.END))
            self.time_entries.append((time_entry, time_var))
            
            # Переключатель активности строки
            active_var = tk.BooleanVar(value=True)
            active_check = ttk.Checkbutton(
                recipe_frame,
                variable=active_var,
                command=lambda idx=i, bath_e=bath_entry, time_e=time_entry, bath_v=bath_var, time_v=time_var, active_v=active_var: self._toggle_row_active(idx, bath_e, time_e, bath_v, time_v, active_v)
            )
            active_check.grid(row=i+1, column=2, padx=5, pady=5)
            self.bath_checkboxes.append((active_check, active_var))
            
            # Кнопка очистить строку
            clear_btn = ttk.Button(
                recipe_frame, 
                text="Очистить", 
                width=8,
                command=lambda idx=i, bath_e=bath_entry, time_e=time_entry, bath_v=bath_var, time_v=time_var, active_v=active_var: self._clear_row(idx, bath_e, time_e, bath_v, time_v, active_v)
            )
            clear_btn.grid(row=i+1, column=3, padx=5, pady=5)
        
        # Кнопки
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=4, pady=10)
        
        def on_launch():
            try:
                hanger_id = self.hanger_id_var.get()
                transition = self.transition_var.get()
                
                if hanger_id < 1:
                    messagebox.showerror("Ошибка", "Номер подвеса должен быть положительным")
                    return
                
                if transition < 0:
                    messagebox.showerror("Ошибка", "Время перехода должно быть положительным числом")
                    return
                
                # Собираем рецепт из введенных данных
                bath_sequence = []
                time_in_bath_list = []
                
                for i in range(7):
                    # Проверяем активность строки
                    active_var = self.bath_checkboxes[i][1]
                    if not active_var.get():
                        continue
                    
                    bath_entry, bath_var = self.bath_entries[i]
                    time_entry, time_var = self.time_entries[i]
                    
                    bath_num = bath_var.get()
                    bath_time = time_var.get()
                    
                    if bath_num and bath_num != 0:
                        if bath_num < 1 or bath_num > 40:
                            messagebox.showerror("Ошибка", f"Номер ванны должен быть от 1 до 40 (строка {i+1})")
                            return
                        
                        if bath_time < 1:
                            messagebox.showerror("Ошибка", f"Время должно быть положительным (строка {i+1})")
                            return
                        
                        bath_sequence.append(bath_num)
                        time_in_bath_list.append(bath_time)
                
                if not bath_sequence:
                    messagebox.showerror("Ошибка", "Нужно указать хотя бы одну ванну")
                    return
                
                # Добавляем в очередь
                hanger_data = {
                    'hanger_id': hanger_id,
                    'bath_sequence': bath_sequence,
                    'time_in_bath_list': time_in_bath_list,
                    'transition_time': transition
                }
                
                self.manual_queue.append(hanger_data)
                logger.info(f"📋 Подвес {hanger_id} добавлен в очередь: ванны {bath_sequence}, времена {time_in_bath_list}сек")
                messagebox.showinfo("Успех", f"Подвес {hanger_id} добавлен в очередь запуска")
                
                # Только увеличиваем номер подвеса, остальное остается как есть
                self.hanger_id_var.set(self.hanger_id_var.get() + 1)
                
            except ValueError as e:
                messagebox.showerror("Ошибка", f"Проверьте правильность введенных данных: {e}")
        
        def on_exit():
            self._save_recipe()
            self.should_exit = True
            self.root.destroy()
        
        ttk.Button(button_frame, text="Запустить подвес", command=on_launch, width=20).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Выход", command=on_exit, width=15).pack(side=tk.LEFT, padx=5)
        
        # Загружаем сохраненный рецепт при открытии
        self._load_recipe()
        
        self.root.mainloop()
    
    def _toggle_row_active(self, idx, bath_entry, time_entry, bath_var, time_var, active_var):
        """Переключить активность строки (включить/выключить)"""
        if active_var.get():
            # Включаем строку - восстанавливаем сохраненные значения или ставим дефолтные
            if self.bath_saved_vars[idx][1].get():
                bath_var.set(self.bath_saved_values[idx])
                time_var.set(self.time_saved_values[idx])
            else:
                bath_var.set(0)
                time_var.set(30)
            bath_entry.config(state='normal', foreground='black')
            time_entry.config(state='normal', foreground='black')
            logger.info(f"▶ Строка {idx+1} включена")
        else:
            # Выключаем строку - очищаем и блокируем
            bath_var.set(0)
            time_var.set(30)
            bath_entry.config(state='disabled', foreground='gray')
            time_entry.config(state='disabled', foreground='gray')
            logger.info(f"▶ Строка {idx+1} отключена")
    
    def _toggle_row_save(self, idx, bath_entry, time_entry, bath_var, time_var, check_var):
        """Переключить сохранение значений для всей строки (ванна + время)"""
        if check_var.get():
            # Сохраняем текущие значения
            self.bath_saved_values[idx] = bath_var.get()
            self.time_saved_values[idx] = time_var.get()
            bath_entry.config(state='disabled', foreground='gray')
            time_entry.config(state='disabled', foreground='gray')
            logger.info(f"✓ Строка {idx+1} сохранена: ванна {self.bath_saved_values[idx]}, время {self.time_saved_values[idx]}сек")
        else:
            # Разблокируем редактирование
            bath_entry.config(state='normal', foreground='black')
            time_entry.config(state='normal', foreground='black')
            logger.info(f"✗ Строка {idx+1} разблокирована")
    
    def _toggle_transition_save(self, entry, var, check_var):
        """Переключить сохранение времени перехода"""
        if check_var.get():
            # Сохраняем текущее значение
            self.transition_saved_value = var.get()
            entry.config(state='disabled', foreground='gray')
            logger.info(f"✓ Время перехода сохранено: {self.transition_saved_value}сек")
        else:
            # Разблокируем редактирование
            entry.config(state='normal', foreground='black')
            logger.info(f"✗ Время перехода разблокировано")
    
    def _toggle_bath_save(self, idx, var, entry, check_var):
        """Переключить сохранение значения ванны"""
        if check_var.get():
            # Сохраняем текущее значение
            self.bath_saved_values[idx] = var.get()
            entry.config(state='disabled', foreground='gray')
            logger.info(f"✓ Ванна {idx+1} сохранена: {self.bath_saved_values[idx]}")
        else:
            # Разблокируем редактирование
            entry.config(state='normal', foreground='black')
            logger.info(f"✗ Ванна {idx+1} разблокирована")
    
    def _toggle_time_save(self, idx, var, entry, check_var):
        """Переключить сохранение значения времени"""
        if check_var.get():
            # Сохраняем текущее значение
            self.time_saved_values[idx] = var.get()
            entry.config(state='disabled', foreground='gray')
            logger.info(f"✓ Время {idx+1} сохранено: {self.time_saved_values[idx]}сек")
        else:
            # Разблокируем редактирование
            entry.config(state='normal', foreground='black')
            logger.info(f"✗ Время {idx+1} разблокировано")
    
    def _clear_row(self, idx, bath_entry, time_entry, bath_var, time_var, active_var):
        """Очистить значения в строке"""
        bath_var.set(0)
        time_var.set(30)
        active_var.set(True)
        bath_entry.config(state='normal', foreground='black')
        time_entry.config(state='normal', foreground='black')
        logger.info(f"🗑️ Строка {idx+1} очищена")
    
    def _clear_all_recipe(self):
        """Очистить весь рецепт"""
        for i in range(7):
            bath_entry, bath_var = self.bath_entries[i]
            time_entry, time_var = self.time_entries[i]
            active_var = self.bath_checkboxes[i][1]
            
            bath_var.set(0)
            time_var.set(30)
            active_var.set(True)
            bath_entry.config(state='normal', foreground='black')
            time_entry.config(state='normal', foreground='black')
        
        logger.info(f"🗑️ Весь рецепт очищен")
    
    def _save_recipe(self):
        """Сохранить текущий рецепт в конфиг"""
        if not self.config:
            return
        
        recipe = []
        
        for i in range(7):
            bath_entry, bath_var = self.bath_entries[i]
            time_entry, time_var = self.time_entries[i]
            active_var = self.bath_checkboxes[i][1]
            
            recipe.append({
                'bath': bath_var.get(),
                'time': time_var.get(),
                'active': active_var.get()
            })
        
        self.config.manual_recipe = recipe
        self.config.manual_transition_time = self.transition_var.get()
        self.config.save()
        logger.info("💾 Рецепт сохранен")
    
    def _load_recipe(self):
        """Загрузить сохраненный рецепт из конфига"""
        if not self.config:
            logger.warning("⚠️ Config not available for loading recipe")
            return
        
        if not self.config.manual_recipe:
            logger.info("📂 No saved recipe found")
            return
        
        logger.info(f"📂 Loading recipe with {len(self.config.manual_recipe)} items")
        
        # Загружаем время перехода
        if hasattr(self.config, 'manual_transition_time'):
            self.transition_var.set(self.config.manual_transition_time)
            logger.info(f"📂 Loaded transition time: {self.config.manual_transition_time}")
        
        for i in range(7):
            if i < len(self.config.manual_recipe):
                recipe_item = self.config.manual_recipe[i]
                bath_entry, bath_var = self.bath_entries[i]
                time_entry, time_var = self.time_entries[i]
                active_var = self.bath_checkboxes[i][1]
                
                bath_val = recipe_item.get('bath', 0)
                time_val = recipe_item.get('time', 30)
                active_val = recipe_item.get('active', True)
                
                bath_var.set(bath_val)
                time_var.set(time_val)
                active_var.set(active_val)
                
                logger.info(f"📂 Row {i+1}: bath={bath_val}, time={time_val}, active={active_val}")
                
                # Обновляем состояние полей
                if active_var.get():
                    bath_entry.config(state='normal', foreground='black')
                    time_entry.config(state='normal', foreground='black')
                else:
                    bath_entry.config(state='disabled', foreground='gray')
                    time_entry.config(state='disabled', foreground='gray')
        
        logger.info("✅ Рецепт загружен")


class ConfigDialog:
    """Диалог настройки симулятора"""
    def __init__(self):
        self.config = SimulatorConfig()
        self.config.load()  # Попытка загрузить сохраненную конфигурацию
        self.result = None
        self.manual_mode = False  # Флаг ручного режима
        
    def show(self):
        """Показать диалог настройки"""
        root = tk.Tk()
        root.title("OPC UA Simulator - Настройка")
        root.geometry("700x600")
        root.resizable(False, False)
        
        # Центрируем окно на экране
        root.update_idletasks()
        width = 700
        height = 600
        x = (root.winfo_screenwidth() // 2) - (width // 2)
        y = (root.winfo_screenheight() // 2) - (height // 2)
        root.geometry(f'{width}x{height}+{x}+{y}')
        
        # Основной фрейм
        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Заголовок
        title = ttk.Label(main_frame, text="Настройка симулятора OPC UA", font=('Arial', 14, 'bold'))
        title.grid(row=0, column=0, columnspan=2, pady=(0, 20))
        
        # Переключатель режима
        mode_var = tk.StringVar(value="auto")
        mode_frame = ttk.Frame(main_frame)
        mode_frame.grid(row=1, column=0, columnspan=2, pady=10)
        ttk.Radiobutton(mode_frame, text="Автоматический", variable=mode_var, value="auto").pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(mode_frame, text="Ручной", variable=mode_var, value="manual").pack(side=tk.LEFT, padx=10)
        
        # Автоматический режим
        auto_frame = ttk.LabelFrame(main_frame, text="Автоматический режим", padding="10")
        auto_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)
        
        ttk.Label(auto_frame, text="Интервал запуска подвесов (сек):").grid(row=0, column=0, sticky=tk.W, pady=5)
        spawn_var = tk.IntVar(value=self.config.hanger_spawn_interval)
        spawn_entry = ttk.Entry(auto_frame, textvariable=spawn_var, width=10)
        spawn_entry.grid(row=0, column=1, sticky=tk.W, pady=5)
        spawn_entry.bind("<FocusIn>", lambda e: e.widget.select_range(0, tk.END))
        
        ttk.Label(auto_frame, text="Максимум подвесов в системе:").grid(row=1, column=0, sticky=tk.W, pady=5)
        max_hangers_var = tk.IntVar(value=self.config.max_hangers)
        max_hangers_entry = ttk.Entry(auto_frame, textvariable=max_hangers_var, width=10)
        max_hangers_entry.grid(row=1, column=1, sticky=tk.W, pady=5)
        max_hangers_entry.bind("<FocusIn>", lambda e: e.widget.select_range(0, tk.END))
        
        # Общие параметры
        common_frame = ttk.LabelFrame(main_frame, text="Параметры ванн", padding="10")
        common_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)
        
        ttk.Label(common_frame, text="Время в каждой ванне (сек):").grid(row=0, column=0, sticky=tk.W, pady=5)
        bath_time_var = tk.IntVar(value=self.config.time_in_bath)
        bath_time_entry = ttk.Entry(common_frame, textvariable=bath_time_var, width=10)
        bath_time_entry.grid(row=0, column=1, sticky=tk.W, pady=5)
        bath_time_entry.bind("<FocusIn>", lambda e: e.widget.select_range(0, tk.END))
        
        ttk.Label(common_frame, text="Время перехода между ваннами (сек):").grid(row=1, column=0, sticky=tk.W, pady=5)
        transition_var = tk.IntVar(value=self.config.bath_transition_time)
        transition_entry = ttk.Entry(common_frame, textvariable=transition_var, width=10)
        transition_entry.grid(row=1, column=1, sticky=tk.W, pady=5)
        transition_entry.bind("<FocusIn>", lambda e: e.widget.select_range(0, tk.END))
        
        ttk.Label(common_frame, text="Последовательность ванн (через запятую):").grid(row=2, column=0, sticky=tk.W, pady=5)
        sequence_var = tk.StringVar(value=','.join(map(str, self.config.bath_sequence)))
        sequence_entry = ttk.Entry(common_frame, textvariable=sequence_var, width=50)
        sequence_entry.grid(row=2, column=1, sticky=(tk.W, tk.E), pady=5)
        sequence_entry.bind("<FocusIn>", lambda e: e.widget.select_range(0, tk.END))
        
        # Информация
        info_frame = ttk.LabelFrame(main_frame, text="Информация", padding="10")
        info_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)
        
        info_text = tk.Text(info_frame, height=4, width=70, wrap=tk.WORD, font=('Arial', 9))
        info_text.insert('1.0', 
            "Автоматический режим: Симулятор автоматически запускает подвесы по расписанию.\n"
            "Ручной режим: Вы сможете запускать подвесы вручную через интерфейс с разными рецептами."
        )
        info_text.config(state='disabled')
        info_text.grid(row=0, column=0)
        
        # Кнопки
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=2, pady=20)
        
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
                
                self.manual_mode = (mode_var.get() == "manual")
                self.result = self.config
                root.destroy()
                
            except ValueError:
                messagebox.showerror("Ошибка", "Проверьте правильность введенных данных")
        
        def on_cancel():
            root.destroy()
        
        # Большие кнопки
        btn_start_auto = ttk.Button(button_frame, text="🚀\nЗАПУСТИТЬ\nАВТОМАТИЧЕСКИЙ", command=on_start)
        btn_start_auto.pack(side=tk.LEFT, padx=10)
        
        btn_start_manual = ttk.Button(button_frame, text="🛠️\nЗАПУСТИТЬ\nРУЧНОЙ", command=lambda: (mode_var.set("manual"), on_start()))
        btn_start_manual.pack(side=tk.LEFT, padx=10)
        
        btn_cancel = ttk.Button(button_frame, text="❌\nОТМЕНА", command=on_cancel)
        btn_cancel.pack(side=tk.LEFT, padx=10)
        
        # Увеличиваем размер кнопок через padding
        for btn in [btn_start_auto, btn_start_manual, btn_cancel]:
            btn.config(padding=25)
        
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
    
    def get_bath_time(self) -> int:
        """Получить время в текущей ванне"""
        return self.time_in_bath
    
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


class HangerStateManual(HangerState):
    """Состояние подвеса с разными временами для каждой ванны (ручной режим)"""
    def __init__(self, hanger_id: int, bath_sequence: List[int], time_in_bath_list: List[int], transition_time: int):
        super().__init__(hanger_id, bath_sequence, 0, transition_time)
        self.time_in_bath_list = time_in_bath_list
    
    def get_bath_time(self) -> int:
        """Получить время для текущей ванны"""
        if self.current_bath_index < len(self.time_in_bath_list):
            return self.time_in_bath_list[self.current_bath_index]
        return 0
    
    def update(self) -> bool:
        """Обновить состояние подвеса с учетом разных времен"""
        if self.is_finished:
            return False
        
        elapsed = self.elapsed_time
        current_bath_time = self.get_bath_time()
        
        if self.state == 'in_bath':
            if elapsed >= current_bath_time:
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


async def run_opcua_server_simulation(config: SimulatorConfig, manual_mode: bool = False):
    """
    Runs an OPC UA server simulation matching the real Omron PLC structure.
    Creates nodes in namespace 4 to match the real server.
    
    Args:
        config: Simulator configuration
        manual_mode: If True, allows manual hanger launches via GUI
    """
    server = Server()
    
    # Setup our server
    server.set_endpoint("opc.tcp://0.0.0.0:4840/freeopcua/server/")
    
    logger.info(f"Starting OPC UA Server Simulation at {server.endpoint}")
    logger.info(f"Mode: {'MANUAL' if manual_mode else 'AUTOMATIC'}")
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
    
    # Очищаем кеш line_monitor перед началом симуляции
    try:
        line_monitor.clear_data()
        logger.info("Line monitor cache cleared")
    except Exception as e:
        logger.warning(f"Could not clear line monitor cache: {e}")
    
    # Simulation state
    hangers: Dict[int, HangerState] = {}  # {hanger_id: HangerState}
    next_hanger_id = 1
    last_spawn_time = datetime.now()
    manual_queue: List[Dict] = []  # Queue for manually-launched hangers
    
    # Если ручной режим - запускаем GUI окно
    manual_window = None
    if manual_mode:
        manual_window = ManualHangerWindow(manual_queue, config)
        # Запускаем GUI в отдельном потоке
        import threading
        gui_thread = threading.Thread(target=manual_window.show, daemon=True)
        gui_thread.start()
        logger.info("🎮 Manual mode GUI started")
    
    try:
        while True:
            # Проверяем флаг выхода из ручного режима
            if manual_mode and manual_window and manual_window.should_exit:
                logger.info("🛑 Exiting from manual mode")
                break
            
            current_time = datetime.now()
            
            # 1. Auto-spawn new hanger if needed (only in auto mode)
            if not manual_mode and len(hangers) < config.max_hangers:
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
            
            # 1b. Manual mode: check for manual launches from queue
            if manual_mode and manual_queue:
                hanger_data = manual_queue.pop(0)
                hanger_id = hanger_data['hanger_id']
                bath_sequence = hanger_data['bath_sequence']
                time_in_bath_list = hanger_data['time_in_bath_list']
                transition_time = hanger_data['transition_time']
                
                # Создаем специальный HangerState для ручного режима
                hanger = HangerStateManual(
                    hanger_id,
                    bath_sequence,
                    time_in_bath_list,
                    transition_time
                )
                hangers[hanger_id] = hanger
                logger.info(f"🎯 Manual launch: Hanger {hanger_id}, baths {bath_sequence}, times {time_in_bath_list}s")
            
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
                # Также удаляем из line_monitor кеша
                try:
                    if hanger_id in line_monitor._hangers:
                        del line_monitor._hangers[hanger_id]
                        logger.info(f"Removed hanger {hanger_id} from line_monitor cache")
                except Exception as e:
                    logger.warning(f"Could not remove hanger from cache: {e}")
            
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
                    
                    # Check if bath is already occupied
                    current_pallete = await bath_vars[bath_num]['Pallete'].read_value()
                    if current_pallete != 0:
                        # Bath is already occupied, skip this hanger (shouldn't happen in normal operation)
                        logger.warning(f"⚠️ Bath {bath_num} already occupied by hanger {current_pallete}, skipping hanger {hanger_id}")
                        continue
                    
                    elapsed = hanger.elapsed_time
                    
                    await bath_vars[bath_num]['InUse'].write_value(True)
                    await bath_vars[bath_num]['Free'].write_value(False)
                    await bath_vars[bath_num]['Pallete'].write_value(hanger.hanger_id)
                    await bath_vars[bath_num]['InTime'].write_value(elapsed)
                    await bath_vars[bath_num]['OutTime'].write_value(hanger.get_bath_time())
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
        
        # Очищаем кеш OPC UA сервиса
        try:
            await opcua_service.disconnect()
            logger.info("OPC UA cache cleared")
        except Exception as e:
            logger.warning(f"Could not clear OPC UA cache: {e}")


if __name__ == "__main__":
    # Show configuration dialog
    dialog = ConfigDialog()
    config = dialog.show()
    
    if config:
        manual_mode = dialog.manual_mode
        
        # Run simulator with configuration
        try:
            if manual_mode:
                logger.info("🎮 Starting simulator in MANUAL mode")
                logger.info("GUI window will open for manual hanger launches")
                asyncio.run(run_opcua_server_simulation(config, manual_mode=True))
            else:
                logger.info("🤖 Starting simulator in AUTOMATIC mode")
                asyncio.run(run_opcua_server_simulation(config, manual_mode=False))
        except KeyboardInterrupt:
            logger.info("Simulator stopped by user (Ctrl+C)")
    else:
        logger.info("Simulator cancelled by user")
