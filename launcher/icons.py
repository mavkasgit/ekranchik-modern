"""
Material Design иконки для лаунчера
Генерируются программно через PIL вместо эмодзи
"""

from PIL import Image, ImageDraw


# Цветовая палитра
COLORS = {
    'accent': '#ff6b00',      # Omron оранжевый
    'accent_hover': '#ff8533',
    'success': '#4caf50',
    'success_dark': '#2e7d32',
    'danger': '#ef5350',
    'danger_dark': '#c62828',
    'warning': '#ffb74d',
    'text': '#e0e0e0',
    'text_muted': '#a0a0a0',
    'bg_dark': '#1e1e1e',
    'bg_card': '#2b2b2b',
    'bg_input': '#252525',
    'border': '#3d3d3d',
}


def create_icon(size: int = 20) -> Image.Image:
    """Базовая пустая иконка"""
    return Image.new('RGBA', (size, size), (0, 0, 0, 0))


def icon_play(size: int = 20, color: str = '#ffffff') -> Image.Image:
    """Иконка Play (треугольник)"""
    img = create_icon(size)
    draw = ImageDraw.Draw(img)
    margin = size // 5
    draw.polygon([
        (margin + 2, margin),
        (margin + 2, size - margin),
        (size - margin, size // 2)
    ], fill=color)
    return img


def icon_stop(size: int = 20, color: str = '#ffffff') -> Image.Image:
    """Иконка Stop (квадрат)"""
    img = create_icon(size)
    draw = ImageDraw.Draw(img)
    margin = size // 4
    draw.rectangle([margin, margin, size - margin, size - margin], fill=color)
    return img


def icon_restart(size: int = 20, color: str = '#ffffff') -> Image.Image:
    """Иконка Restart (круговая стрелка)"""
    img = create_icon(size)
    draw = ImageDraw.Draw(img)
    margin = size // 5
    # Дуга
    draw.arc([margin, margin, size - margin, size - margin], 45, 315, fill=color, width=2)
    # Стрелка
    arrow_size = size // 5
    cx, cy = size - margin - 2, size // 2 - arrow_size // 2
    draw.polygon([
        (cx - arrow_size, cy),
        (cx, cy - arrow_size),
        (cx, cy + arrow_size)
    ], fill=color)
    return img


def icon_copy(size: int = 20, color: str = '#ffffff') -> Image.Image:
    """Иконка Copy (два прямоугольника)"""
    img = create_icon(size)
    draw = ImageDraw.Draw(img)
    margin = size // 5
    offset = size // 6
    # Задний прямоугольник
    draw.rectangle([margin, margin, size - margin - offset, size - margin - offset], 
                   outline=color, width=1)
    # Передний прямоугольник
    draw.rectangle([margin + offset, margin + offset, size - margin, size - margin], 
                   fill=COLORS['bg_card'], outline=color, width=1)
    return img


def icon_trash(size: int = 20, color: str = '#ffffff') -> Image.Image:
    """Иконка Trash (корзина)"""
    img = create_icon(size)
    draw = ImageDraw.Draw(img)
    margin = size // 4
    # Крышка
    draw.rectangle([margin - 2, margin, size - margin + 2, margin + 2], fill=color)
    draw.rectangle([size // 2 - 2, margin - 2, size // 2 + 2, margin], fill=color)
    # Корпус
    draw.rectangle([margin, margin + 3, size - margin, size - margin], outline=color, width=1)
    # Линии
    for x in [size // 3, size // 2, size * 2 // 3]:
        draw.line([(x, margin + 5), (x, size - margin - 2)], fill=color, width=1)
    return img


def icon_folder(size: int = 20, color: str = '#ffffff') -> Image.Image:
    """Иконка Folder"""
    img = create_icon(size)
    draw = ImageDraw.Draw(img)
    margin = size // 5
    # Папка
    draw.rectangle([margin, margin + 3, size - margin, size - margin], fill=color)
    draw.rectangle([margin, margin, margin + size // 3, margin + 4], fill=color)
    return img


def icon_connection(size: int = 20, color: str = '#ffffff') -> Image.Image:
    """Иконка Connection (plug)"""
    img = create_icon(size)
    draw = ImageDraw.Draw(img)
    margin = size // 4
    # Вилка
    draw.rectangle([margin, size // 2 - 2, size - margin, size // 2 + 2], fill=color)
    draw.rectangle([margin + 2, margin, margin + 4, size // 2], fill=color)
    draw.rectangle([size - margin - 4, margin, size - margin - 2, size // 2], fill=color)
    # Провод
    draw.rectangle([size // 2 - 1, size // 2, size // 2 + 1, size - margin], fill=color)
    return img


def icon_calendar(size: int = 20, color: str = '#ffffff') -> Image.Image:
    """Иконка Calendar"""
    img = create_icon(size)
    draw = ImageDraw.Draw(img)
    margin = size // 5
    # Рамка
    draw.rectangle([margin, margin + 2, size - margin, size - margin], outline=color, width=1)
    # Верхняя полоса
    draw.rectangle([margin, margin + 2, size - margin, margin + 5], fill=color)
    # Крепления
    draw.rectangle([margin + 3, margin, margin + 5, margin + 3], fill=color)
    draw.rectangle([size - margin - 5, margin, size - margin - 3, margin + 3], fill=color)
    return img


def icon_filter(size: int = 20, color: str = '#ffffff') -> Image.Image:
    """Иконка Filter (воронка)"""
    img = create_icon(size)
    draw = ImageDraw.Draw(img)
    margin = size // 5
    draw.polygon([
        (margin, margin),
        (size - margin, margin),
        (size // 2 + 2, size // 2),
        (size // 2 + 2, size - margin),
        (size // 2 - 2, size - margin),
        (size // 2 - 2, size // 2),
    ], fill=color)
    return img


def icon_refresh(size: int = 20, color: str = '#ffffff') -> Image.Image:
    """Иконка Refresh (две стрелки)"""
    img = create_icon(size)
    draw = ImageDraw.Draw(img)
    margin = size // 5
    # Верхняя дуга со стрелкой
    draw.arc([margin, margin, size - margin, size - margin], 180, 0, fill=color, width=2)
    # Нижняя дуга со стрелкой
    draw.arc([margin, margin, size - margin, size - margin], 0, 180, fill=color, width=2)
    return img


def status_dot(size: int = 10, color: str = '#4caf50') -> Image.Image:
    """Цветной кружок статуса"""
    img = create_icon(size)
    draw = ImageDraw.Draw(img)
    draw.ellipse([1, 1, size - 1, size - 1], fill=color)
    return img


# Кэш иконок
_icon_cache = {}


def get_ctk_image(icon_func, size: int = 20, color: str = '#ffffff', light_color: str = None):
    """Получить CTkImage для использования в кнопках"""
    import customtkinter as ctk
    
    cache_key = (icon_func.__name__, size, color, light_color)
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]
    
    dark_img = icon_func(size, color)
    light_img = icon_func(size, light_color or color)
    
    ctk_img = ctk.CTkImage(
        light_image=light_img,
        dark_image=dark_img,
        size=(size, size)
    )
    
    _icon_cache[cache_key] = ctk_img
    return ctk_img


def get_status_image(running: bool, size: int = 10):
    """Получить CTkImage для статуса"""
    import customtkinter as ctk
    
    color = COLORS['success'] if running else '#666666'
    cache_key = ('status', size, color)
    
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]
    
    img = status_dot(size, color)
    ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
    
    _icon_cache[cache_key] = ctk_img
    return ctk_img


# === Иконка для System Tray ===

def get_tray_icon():
    """Загружает иконку из launcher.ico для System Tray"""
    from pathlib import Path
    import sys
    
    # Определяем путь к иконке
    if getattr(sys, 'frozen', False):
        # Запуск из EXE - ищем в _MEIPASS
        icon_path = Path(sys._MEIPASS) / "launcher.ico"
    else:
        # Обычный запуск
        icon_path = Path(__file__).parent / "launcher.ico"
    
    # Пробуем загрузить .ico файл
    if icon_path.exists():
        try:
            # Открываем .ico файл
            img = Image.open(icon_path)
            
            # .ico может содержать несколько размеров, берём самый большой
            # Обычно это 256x256 или 128x128
            if hasattr(img, 'size'):
                # Если это один размер
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                # Масштабируем до 64x64 для трея
                if img.size != (64, 64):
                    img = img.resize((64, 64), Image.Resampling.LANCZOS)
                return img
            else:
                # Если это ICO с несколькими размерами, берём первый
                img = img.convert('RGBA')
                if img.size != (64, 64):
                    img = img.resize((64, 64), Image.Resampling.LANCZOS)
                return img
        except Exception as e:
            print(f"Не удалось загрузить launcher.ico: {e}")
    
    # Fallback - создаём простую иконку программно
    print("Используется fallback иконка")
    size = 64
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Оранжевый круг (Omron цвет)
    draw.ellipse([4, 4, 60, 60], fill='#ff6b00', outline='#ff8533', width=2)
    
    # Белая буква E
    draw.text((20, 16), "E", fill='white', font=None)
    
    return img
