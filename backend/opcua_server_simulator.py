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
        self._next_id = 1
        
    def get_next_id(self):
        """Получить следующий свободный ID и инкрементировать счетчик"""
        current = self._next_id
        self._next_id += 1
        return current

    def set_next_id(self, val):
        """Установить начальный ID (например, из GUI)"""
        self._next_id = max(self._next_id, val)
        
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
                
                # BUGFIX: Если в последовательности есть 33 (которая не должна там быть по ТЗ пользователя), 
                # сбрасываем на дефолтную рабочую последовательность
                if 33 in self.bath_sequence:
                    logger.warning("⚠️ Обнаружена некорректная ванна 33 в конфиге. Сброс последовательности на стандартную.")
                    self.bath_sequence = [3, 5, 7, 10, 17, 18, 19, 20, 31, 34]
            return True
        except FileNotFoundError:
            return False


class ToggleSwitch(tk.Canvas):
    """Кастомный переключатель-слайдер (Toggle Switch)"""
    def __init__(self, parent, variable, command=None, width=65, height=32, bg="#f0f0f0", **kwargs):
        # Если bg не передан, пытаемся взять у родителя
        if not bg and hasattr(parent, "cget"):
            try:
                bg = parent.cget("background")
            except:
                bg = "#f0f0f0"
            
        super().__init__(parent, width=width, height=height, highlightthickness=0, bg=bg, **kwargs)
        self.variable = variable
        self.command = command
        self.width = width
        self.height = height
        
        self.padding = 3
        self.radius = (height - 2 * self.padding) / 2
        
        self.bind("<Button-1>", self.toggle)
        self.update_switch()
        
        # Следим за изменением переменной извне
        self.variable.trace_add("write", lambda *args: self.update_switch())

    def toggle(self, event=None):
        self.variable.set(not self.variable.get())
        if self.command:
            try:
                self.command()
            except:
                pass
        self.update_switch()

    def update_switch(self):
        self.delete("all")
        is_on = self.variable.get()
        
        # Цвета
        bg_track = "#4CAF50" if is_on else "#BDBDBD" # Зеленый (ВКЛ) или Серый (ВЫКЛ)
        thumb_color = "white"
        
        # Рисуем подложку (дорожку)
        r = self.height / 2
        self.create_oval(0, 0, 2*r, self.height, fill=bg_track, outline="")
        self.create_oval(self.width - 2*r, 0, self.width, self.height, fill=bg_track, outline="")
        self.create_rectangle(r, 0, self.width - r, self.height, fill=bg_track, outline="")
        
        # Рисуем рычажок (круг)
        thumb_x = self.width - r if is_on else r
        self.create_oval(thumb_x - self.radius, self.height/2 - self.radius,
                         thumb_x + self.radius, self.height/2 + self.radius,
                         fill=thumb_color, outline="")


class ManualHangerWindow:
    """Окно для запуска подвесов вручную в ручном режиме"""
    def __init__(self, manual_queue, config=None, hangers=None):
        self.manual_queue = manual_queue
        self.config = config
        self.hangers = hangers if hangers is not None else {}
        self.root = None
        self.hanger_id_var = None
        self.transition_var = None
        self.bath_entries = []
        self.time_entries = []
        self.bath_checkboxes = []
        self.bath_saved_values = [0] * 7
        self.time_saved_values = [30] * 7
        self.transition_saved_value = 30
        self.should_exit = False
        self.monitor_items = {}  # {hanger_id: monitor_widgets_dict}
        self.last_update = 0
        self.monitor_canvas = None
        self.monitor_scrollable = None
        self._root_after_handle = None
        self.auto_spawn_var = None
        self.spawn_interval_var = None
        
    def show(self):
        """Показать окно ручного режима с мониторингом"""
        self.root = tk.Tk()
        self.auto_spawn_var = tk.BooleanVar(value=False)
        self.spawn_interval_var = tk.IntVar(value=self.config.hanger_spawn_interval)
        
        # Слушатель для обновления интервала в конфиге в реальном времени
        self.spawn_interval_var.trace_add("write", self._on_interval_change)
        self.root.title("OPC UA Simulator - ПУЛЬТ УПРАВЛЕНИЯ")
        
        # Центрирование окна
        window_width = 1600
        window_height = 900
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        center_x = int(screen_width/2 - window_width / 2)
        center_y = int(screen_height/2 - window_height / 2)
        
        self.root.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
        self.root.resizable(True, True)
        
        # Стилизация
        self.root.option_add("*Font", "Arial 14")
        style = ttk.Style()
        style.configure(".", font=('Arial', 14))
        style.configure("Monitor.TFrame", background="#f0f0f0")
        style.configure("Hanger.TLabelframe", padding=10)
        style.configure("TButton", padding=10)
        style.configure("TEntry", font=('Arial', 14))
        style.configure("TLabelframe.Label", font=('Arial', 14, 'bold'))
        
        # Специальные стили для меток
        style.configure("Title.TLabel", font=('Arial', 18, 'bold'))
        style.configure("Bold.TLabel", font=('Arial', 14, 'bold'))
        style.configure("Timer.TLabel", font=('Arial', 16, 'bold'))
        
        # Главный контейнер (две колонки)
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # --- ЛЕВАЯ КОЛОНКА (ЗАПУСК) ---
        left_frame = ttk.Frame(main_paned, padding="5")
        main_paned.add(left_frame, weight=1)
        
        title = ttk.Label(left_frame, text="🚀 Запуск подвеса", style="Title.TLabel")
        title.pack(pady=(0, 15))
        
        # Параметры (Hanger ID, Transition)
        ps_frame = ttk.LabelFrame(left_frame, text="Параметры", padding=10)
        ps_frame.pack(fill=tk.X, pady=5)
        
        row1 = ttk.Frame(ps_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="Номер:").pack(side=tk.LEFT)
        self.hanger_id_var = tk.IntVar(value=1)
        ttk.Entry(row1, textvariable=self.hanger_id_var, width=10).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(row1, text="Переход (с):").pack(side=tk.LEFT, padx=(10, 0))
        self.transition_var = tk.IntVar(value=30)
        ttk.Entry(row1, textvariable=self.transition_var, width=10).pack(side=tk.LEFT, padx=5)
        
        row2 = ttk.Frame(ps_frame)
        row2.pack(fill=tk.X, pady=5)
        ttk.Label(row2, text="🤖 АВТО-ЗАПУСК:").pack(side=tk.LEFT)
        ToggleSwitch(row2, variable=self.auto_spawn_var).pack(side=tk.LEFT, padx=10)
        
        ttk.Label(row2, text="Интервал (с):").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Entry(row2, textvariable=self.spawn_interval_var, width=8).pack(side=tk.LEFT, padx=5)
        
        # Рецепт
        recipe_frame = ttk.LabelFrame(left_frame, text="Рецепт (ванны + время)", padding=10)
        recipe_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        grid_f = ttk.Frame(recipe_frame)
        grid_f.pack(fill=tk.X)
        
        ttk.Label(grid_f, text="Ванна", style="Bold.TLabel").grid(row=0, column=1, pady=5)
        ttk.Label(grid_f, text="Время (с)", style="Bold.TLabel").grid(row=0, column=2, pady=5)
        ttk.Button(grid_f, text="🗑️", width=5, command=self._clear_all_recipe).grid(row=0, column=4, padx=5)
        
        for i in range(7):
            ttk.Label(grid_f, text=f"{i+1}:").grid(row=i+1, column=0, pady=5)
            
            b_var = tk.IntVar(value=0)
            b_entry = ttk.Entry(grid_f, textvariable=b_var, width=8)
            b_entry.grid(row=i+1, column=1, padx=2, pady=5)
            self.bath_entries.append((b_entry, b_var))
            
            t_var = tk.IntVar(value=30)
            t_entry = ttk.Entry(grid_f, textvariable=t_var, width=8)
            t_entry.grid(row=i+1, column=2, padx=5, pady=5)
            self.time_entries.append((t_entry, t_var))
            
            a_var = tk.BooleanVar(value=True)
            a_check = ToggleSwitch(grid_f, variable=a_var, 
                                 command=lambda idx=i: self._update_row_active(idx))
            a_check.grid(row=i+1, column=3, padx=10)
            self.bath_checkboxes.append((a_check, a_var))
            
            ttk.Button(grid_f, text="×", width=5, 
                       command=lambda idx=i: self._clear_row_idx(idx)).grid(row=i+1, column=4, padx=2, pady=5)
        
        btn_f = ttk.Frame(left_frame)
        btn_f.pack(pady=10)
        ttk.Button(btn_f, text="ЗАПУСТИТЬ", command=self._on_launch, width=15, padding=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_f, text="СОХРАНИТЬ РЕЦЕПТ", command=self._save_recipe, width=20, padding=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_f, text="ВЫХОД", command=self._on_exit, width=10, padding=15).pack(side=tk.LEFT, padx=5)
        
        # --- ПРАВАЯ КОЛОНКА (МОНИТОРИНГ) ---
        right_frame = ttk.Frame(main_paned, padding="5", style="Monitor.TFrame")
        main_paned.add(right_frame, weight=2)
        
        ttk.Label(right_frame, text="📊 Мониторинг подвесов", style="Title.TLabel", background="#f0f0f0").pack(pady=(0, 15))
        
        # Скроллируемая область для карточек подвесов
        canvas_frame = ttk.Frame(right_frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self.monitor_canvas = tk.Canvas(canvas_frame, background="#f0f0f0", highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.monitor_canvas.yview)
        self.monitor_scrollable = ttk.Frame(self.monitor_canvas, style="Monitor.TFrame")
        
        self.monitor_scrollable.bind("<Configure>", lambda e: self.monitor_canvas.configure(scrollregion=self.monitor_canvas.bbox("all")))
        self.monitor_canvas.create_window((0, 0), window=self.monitor_scrollable, anchor="nw")
        self.monitor_canvas.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side="right", fill="y")
        self.monitor_canvas.pack(side="left", fill="both", expand=True)
        
        # Загружаем рецепт
        self._load_recipe()
        
        # Запуск цикла обновления
        self._root_after_handle = self.root.after(1000, self._update_loop)
        
        self.root.mainloop()

    def _update_loop(self):
        """Регулярное обновление мониторинга"""
        if self.should_exit: return
        
        try:
            self._do_update_monitoring()
        except Exception as e:
            logger.error(f"Error in UI update loop: {e}")
            
        self._root_after_handle = self.root.after(1000, self._update_loop)

    def _do_update_monitoring(self):
        """Обновить список карточек подвесов"""
        if not self.root: return
        
        active_ids = list(self.hangers.keys())
        
        # Удаляем карточки завершенных подвесов
        for h_id in list(self.monitor_items.keys()):
            if h_id not in active_ids:
                self.monitor_items[h_id]['frame'].destroy()
                del self.monitor_items[h_id]
        
        # Добавляем/обновляем карточки активных
        for h_id in active_ids:
            hanger = self.hangers[h_id]
            
            if h_id not in self.monitor_items:
                self._create_hanger_card(h_id)
            
            self._update_hanger_card(h_id, hanger)



    def _update_hanger_duration(self, h_id, var):
        """Обновить длительность текущего состояния подвеса"""
        if h_id in self.hangers:
            try:
                val = int(var.get())
                self.hangers[h_id].set_duration(val)
            except ValueError:
                messagebox.showerror("Ошибка", "Введите целое число!")

    def _on_interval_change(self, *args):
        """Обработка изменения интервала авто-запуска"""
        try:
            val = self.spawn_interval_var.get()
            if val > 0:
                self.config.hanger_spawn_interval = val
                logger.info(f"⚙️ Auto-spawn interval updated to {val}s")
        except:
            pass



    def _create_hanger_card(self, h_id):
        """Создать карточку для нового подвеса"""
        card = ttk.LabelFrame(self.monitor_scrollable, text=f"Подвес №{h_id}", style="Hanger.TLabelframe")
        card.pack(fill=tk.X, padx=5, pady=5)
        
        info_f = ttk.Frame(card)
        info_f.pack(fill=tk.X, side=tk.LEFT, expand=True)
        
        state_lbl = ttk.Label(info_f, text="Состояние: ...")
        state_lbl.pack(anchor=tk.W, pady=2)
        
        time_lbl = ttk.Label(info_f, text="Осталось: -- сек", style="Timer.TLabel")
        time_lbl.pack(anchor=tk.W, pady=2)
        
        # Кнопки управления
        ctrl_f = ttk.Frame(card)
        ctrl_f.pack(side=tk.RIGHT)
        
        # Редактирование времени (Прямой ввод)
        time_ctrl = ttk.Frame(ctrl_f)
        time_ctrl.pack(pady=2)
        
        dur_var = tk.StringVar()
        dur_entry = ttk.Entry(time_ctrl, textvariable=dur_var, width=5)
        dur_entry.pack(side=tk.LEFT, padx=2)
        
        ttk.Button(time_ctrl, text="OK", width=3, 
                   command=lambda v=dur_var: self._update_hanger_duration(h_id, v)).pack(side=tk.LEFT)
        
        # Действия
        act_ctrl = ttk.Frame(ctrl_f)
        act_ctrl.pack(pady=2)
        ttk.Button(act_ctrl, text="📝 МАРШРУТ", width=12, command=lambda: self._toggle_route(h_id)).pack(side=tk.LEFT, padx=2)
        ttk.Button(act_ctrl, text="⏩ SKIP", width=8, command=lambda: self._skip_hanger(h_id)).pack(side=tk.LEFT, padx=2)
        ttk.Button(act_ctrl, text="🗑️", width=3, command=lambda: self._delete_hanger(h_id)).pack(side=tk.LEFT, padx=2)
        
        # Скрытый фрейм для детального маршрута
        route_frame = ttk.Frame(card)
        # Пока не пакуем
        
        self.monitor_items[h_id] = {
            'frame': card,
            'state_lbl': state_lbl,
            'time_lbl': time_lbl,
            'dur_var': dur_var,
            'last_state': None,
            'route_frame': route_frame,
            'expanded': False
        }

    def _toggle_route(self, h_id):
        """Развернуть/свернуть детализацию маршрута"""
        item = self.monitor_items.get(h_id)
        if not item: return
        
        if item['expanded']:
            item['route_frame'].pack_forget()
            item['expanded'] = False
        else:
            item['route_frame'].pack(fill=tk.X, pady=5)
            item['expanded'] = True
            # Сразу обновляем список при открытии
            if h_id in self.hangers:
                self._refresh_route_list(h_id, self.hangers[h_id])

    def _refresh_route_list(self, h_id, hanger):
        """Отрисовать список ванн маршрута"""
        item = self.monitor_items[h_id]
        frame = item['route_frame']
        
        for widget in frame.winfo_children():
            widget.destroy()
            
        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)
        
        for i, bath_num in enumerate(hanger.bath_sequence):
            row = ttk.Frame(frame)
            row.pack(fill=tk.X, padx=10)
            
            # Определяем время (ручной или авто)
            if hasattr(hanger, 'time_in_bath_list'):
                dur = hanger.time_in_bath_list[i] if i < len(hanger.time_in_bath_list) else 0
            else:
                dur = hanger.time_in_bath
                
            is_current = (hanger.state == 'in_bath' and hanger.current_bath_index == i)
            
            fg = "green" if is_current else "black"
            font_w = "bold" if is_current else "normal"
            bg = "#e8f5e9" if is_current else None
            
            lbl_text = f"Ванна {bath_num}: {dur} сек"
            if is_current: lbl_text += "  👈 ТЕКУЩАЯ"
            
            lbl = tk.Label(row, text=lbl_text, fg=fg, font=('Arial', 12, font_w), anchor='w')
            if bg: lbl.config(bg=bg)
            lbl.pack(fill=tk.X, side=tk.LEFT, expand=True)

    def _update_hanger_card(self, h_id, hanger):
        """Обновить данные в карточке"""
        item = self.monitor_items[h_id]
        
        status = "ВАННА " + str(hanger.current_bath) if hanger.state == 'in_bath' else "ПЕРЕХОД..."
        item['state_lbl'].config(text=f"Статус: {status}")
        
        # Обновляем поле ввода при смене состояния
        current_state_key = f"{hanger.state}_{hanger.current_bath_index}"
        if item['last_state'] != current_state_key:
            total_needed = hanger.get_bath_time() if hanger.state == 'in_bath' else hanger.transition_time
            item['dur_var'].set(str(total_needed))
            item['last_state'] = current_state_key
            # Если развернуто, обновляем список ванн при смене состояния
            if item['expanded']:
                self._refresh_route_list(h_id, hanger)

        total_needed = hanger.get_bath_time() if hanger.state == 'in_bath' else hanger.transition_time
        left = max(0, total_needed - hanger.elapsed_time)
        
        color = "red" if left < 10 else "black"
        item['time_lbl'].config(text=f"Осталось: {left} сек", foreground=color)

    def _adjust_hanger_time(self, h_id, seconds):
        if h_id in self.hangers:
            self.hangers[h_id].adjust_time(seconds)

    def _skip_hanger(self, h_id):
        if h_id in self.hangers:
            self.hangers[h_id].force_next_state()

    def _delete_hanger(self, h_id):
        if h_id in self.hangers:
            if messagebox.askyesno("Удаление", f"Удалить подвес №{h_id} из системы?"):
                # Мы не можем удалить напрямую из словаря в GUI потоке безопасно без Lock, 
                # но в данном симуляторе мы доверимся тому что цикл в основном потоке его подхватит 
                # или просто пометим его как завершенный.
                # Самый простой способ - форсировать индекс до конца.
                self.hangers[h_id].current_bath_index = len(self.hangers[h_id].bath_sequence) + 1
                logger.warning(f"🗑️ Hanger {h_id} marked for deletion via GUI")

    def _on_launch(self):
        try:
            trans = self.transition_var.get()
            baths = []
            times = []
            for i in range(7):
                if self.bath_checkboxes[i][1].get():
                    b_num = self.bath_entries[i][1].get()
                    t_val = self.time_entries[i][1].get()
                    if b_num > 0:
                        baths.append(b_num)
                        times.append(t_val)
            
            if not baths:
                messagebox.showerror("Ошибка", "Рецепт пуст!")
                return
            
            # Используем централизованный ID из конфига
            h_id = self.config.get_next_id()
            self.hanger_id_var.set(h_id + 1) # Предлагаем следующий во фронте
                
            hanger_data = {
                'hanger_id': h_id,
                'bath_sequence': baths,
                'time_in_bath_list': times,
                'transition_time': trans
            }
            self.manual_queue.append(hanger_data)
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _on_exit(self):
        self._save_recipe()
        self.should_exit = True
        self.root.destroy()

    def _update_row_active(self, idx):
        """Обновить состояние полей строки"""
        active = self.bath_checkboxes[idx][1].get()
        state = 'normal' if active else 'disabled'
        self.bath_entries[idx][0].config(state=state)
        self.time_entries[idx][0].config(state=state)

    def _clear_row_idx(self, idx):
        self.bath_entries[idx][1].set(0)
        self.time_entries[idx][1].set(30)
        self.bath_checkboxes[idx][1].set(True)
        self._update_row_active(idx)

    def _clear_all_recipe(self):
        for i in range(7):
            self._clear_row_idx(i)

    def _save_recipe(self):
        """Сохранить текущий рецепт в конфиг"""
        if not self.config:
            return
        
        recipe = []
        for i in range(7):
            recipe.append({
                'bath': self.bath_entries[i][1].get(),
                'time': self.time_entries[i][1].get(),
                'active': self.bath_checkboxes[i][1].get()
            })
        
        self.config.manual_recipe = recipe
        self.config.manual_transition_time = self.transition_var.get()
        self.config.save()
        logger.info("💾 Рецепт сохранен")

    def _load_recipe(self):
        """Загрузить сохраненный рецепт из конфига"""
        if not self.config or not self.config.manual_recipe:
            return
        
        if hasattr(self.config, 'manual_transition_time'):
            self.transition_var.set(self.config.manual_transition_time)
        
        for i in range(min(7, len(self.config.manual_recipe))):
            item = self.config.manual_recipe[i]
            self.bath_entries[i][1].set(item.get('bath', 0))
            self.time_entries[i][1].set(item.get('time', 30))
            self.bath_checkboxes[i][1].set(item.get('active', True))
            self._update_row_active(i)
        logger.info("✅ Рецепт загружен")

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
    
    def adjust_time(self, seconds: int):
        """Изменить время начала состояния, чтобы добавить или убавить оставшееся время"""
        self.state_start_time = self.state_start_time - timedelta(seconds=seconds)
        logger.info(f"⏳ Hanger {self.hanger_id}: Adjusted time by {seconds}s")

    def set_duration(self, seconds: int):
        """Установить новую длительность текущего состояния"""
        if self.state == 'in_bath':
            self.time_in_bath = seconds
        else:
            self.transition_time = seconds
        logger.info(f"⏱️ Hanger {self.hanger_id}: Set new duration {seconds}s for {self.state}")

    def force_next_state(self):
        """Форсировать переход к следующему состоянию"""
        if self.is_finished:
            return
            
        if self.state == 'in_bath':
            self.state = 'transitioning'
            self.state_start_time = datetime.now()
            logger.info(f"⏭ Hanger {self.hanger_id}: Forced transition from bath {self.current_bath}")
        elif self.state == 'transitioning':
            self.current_bath_index += 1
            self.state = 'in_bath'
            self.state_start_time = datetime.now()
            logger.info(f"⏭ Hanger {self.hanger_id}: Forced arrival at next bath")

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
    
    def set_duration(self, seconds: int):
        """Установить новую длительность для текущей ванны или перехода (ручной режим)"""
        if self.state == 'in_bath':
            if self.current_bath_index < len(self.time_in_bath_list):
                self.time_in_bath_list[self.current_bath_index] = seconds
        else:
            self.transition_time = seconds
        logger.info(f"⏱️ Hanger {self.hanger_id} (Manual): Set new duration {seconds}s for {self.state}")
    
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


async def run_opcua_server_simulation(config: SimulatorConfig):
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
    logger.info("Mode: UNIFIED (GUI + Optional Auto-spawn)")
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
    last_spawn_time = datetime.now() - timedelta(minutes=10) # Сразу готовы к спавну
    last_auto_mode = False
    manual_queue: List[Dict] = []  # Queue for manually-launched hangers
    
    # Всегда запускаем GUI окно (Пульт Управления)
    manual_window = ManualHangerWindow(manual_queue, config, hangers)
    
    # Запускаем GUI в отдельном потоке
    import threading
    gui_thread = threading.Thread(target=manual_window.show, daemon=True)
    gui_thread.start()
    
    logger.info("🎨 Unified Control Panel GUI started")
    
    try:
        while True:
            # Проверяем флаг выхода
            if manual_window and manual_window.should_exit:
                logger.info("🛑 Exiting from manual mode")
                break
            
            current_time = datetime.now()
            
            # 1. Смена режима: проверяем галочку в GUI
            auto_mode_active = False
            if manual_window.auto_spawn_var:
                auto_mode_active = manual_window.auto_spawn_var.get()
            
            # Если только что включили автозапуск - сбрасываем таймер для мгновенного первого спавна
            if auto_mode_active and not last_auto_mode:
                last_spawn_time = datetime.now() - timedelta(seconds=config.hanger_spawn_interval + 1)
            last_auto_mode = auto_mode_active
            
            # 1a. Auto-spawn new hanger if needed
            if auto_mode_active and len(hangers) < config.max_hangers:
                if (current_time - last_spawn_time).total_seconds() >= config.hanger_spawn_interval:
                    # Используем централизованный ID из конфига
                    h_id = config.get_next_id()
                    # Синхронизируем GUI
                    manual_window.hanger_id_var.set(h_id + 1)
                    
                    # Получаем рецепт из текущих настроек (поля GUI, сохраненные в конфиг)
                    baths = []
                    times = []
                    for item in config.manual_recipe:
                        if item.get('active') and item.get('bath', 0) > 0:
                            baths.append(item['bath'])
                            times.append(item['time'])
                    
                    if not baths:
                        # Резервный вариант, если рецепт не задан
                        baths = config.bath_sequence
                        times = [config.time_in_bath] * len(baths)
                        trans = config.bath_transition_time
                        hanger = HangerState(h_id, baths, config.time_in_bath, trans)
                    else:
                        trans = config.manual_transition_time
                        hanger = HangerStateManual(h_id, baths, times, trans)

                    hangers[h_id] = hanger
                    logger.info(f"🚀 (Auto) Spawned hanger {h_id}, using GUI recipe: {baths}")
                    last_spawn_time = current_time
            
            # 1b. Manual mode: check for manual launches from queue
            if manual_queue:
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


if __name__ == "__main__":
    # Load configuration
    config = SimulatorConfig()
    config.load()
    
    # Run simulator with configuration
    try:
        logger.info("🚀 Starting unified simulator with GUI")
        asyncio.run(run_opcua_server_simulation(config))
    except KeyboardInterrupt:
        logger.info("Simulator stopped by user (Ctrl+C)")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
