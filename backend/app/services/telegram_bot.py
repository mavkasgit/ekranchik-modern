"""
Telegram Bot Service - handles Telegram bot for profile search.
"""
import asyncio
import logging
from typing import Optional, Set, Dict
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from app.core.config import settings
from app.services.catalog_service import catalog_service

logger = logging.getLogger(__name__)


class TelegramBotService:
    """
    Telegram bot for profile search and photo viewing.
    
    Features:
    - Profile search with Latin/Cyrillic support
    - Photo display
    - Password-based authentication
    - Multi-match result limiting
    """
    
    MAX_RESULTS = 5  # Maximum results to show in Telegram
    
    def __init__(self):
        self._bot: Optional[Bot] = None
        self._dp: Optional[Dispatcher] = None
        self._running = False
        self._authorized_users: Set[int] = set()
        self._pending_auth: Dict[int, datetime] = {}
    
    @property
    def is_running(self) -> bool:
        """Check if bot is running."""
        return self._running
    
    def is_authorized(self, user_id: int) -> bool:
        """Check if user is authorized."""
        return user_id in self._authorized_users
    
    def authorize_user(self, user_id: int) -> None:
        """Add user to authorized set."""
        self._authorized_users.add(user_id)
    
    def deauthorize_user(self, user_id: int) -> None:
        """Remove user from authorized set."""
        self._authorized_users.discard(user_id)
    
    def check_password(self, password: str) -> bool:
        """Check if password is correct."""
        return password == settings.BOT_PASSWORD
    
    def _setup_handlers(self) -> None:
        """Set up message handlers."""
        if not self._dp:
            return
        
        @self._dp.message(Command("start"))
        async def cmd_start(message: Message):
            """Handle /start command."""
            if self.is_authorized(message.from_user.id):
                await message.answer(
                    "👋 Привет! Я бот для поиска профилей.\n\n"
                    "Просто отправь мне название профиля, и я найду его в базе.\n\n"
                    "Команды:\n"
                    "/search <запрос> - поиск профиля\n"
                    "/help - справка"
                )
            else:
                self._pending_auth[message.from_user.id] = datetime.now()
                await message.answer(
                    "🔐 Для доступа к боту введите пароль:"
                )
        
        @self._dp.message(Command("help"))
        async def cmd_help(message: Message):
            """Handle /help command."""
            if not self.is_authorized(message.from_user.id):
                await message.answer("🔐 Сначала авторизуйтесь с помощью /start")
                return
            
            await message.answer(
                "📖 Справка по боту:\n\n"
                "• Отправьте название профиля для поиска\n"
                "• Поддерживается латиница и кириллица\n"
                "• Показываются до 5 результатов\n\n"
                "Команды:\n"
                "/search <запрос> - поиск профиля\n"
                "/logout - выйти из системы"
            )
        
        @self._dp.message(Command("search"))
        async def cmd_search(message: Message):
            """Handle /search command."""
            if not self.is_authorized(message.from_user.id):
                await message.answer("🔐 Сначала авторизуйтесь с помощью /start")
                return
            
            # Extract query from command
            parts = message.text.split(maxsplit=1)
            if len(parts) < 2:
                await message.answer("❌ Укажите запрос: /search <название профиля>")
                return
            
            query = parts[1].strip()
            await self._handle_search(message, query)
        
        @self._dp.message(Command("logout"))
        async def cmd_logout(message: Message):
            """Handle /logout command."""
            self.deauthorize_user(message.from_user.id)
            await message.answer("👋 Вы вышли из системы. Для входа используйте /start")
        
        @self._dp.message(F.text)
        async def handle_text(message: Message):
            """Handle text messages."""
            user_id = message.from_user.id
            text = message.text.strip()
            
            # Check if user is pending auth
            if user_id in self._pending_auth:
                if self.check_password(text):
                    self.authorize_user(user_id)
                    del self._pending_auth[user_id]
                    await message.answer(
                        "✅ Авторизация успешна!\n\n"
                        "Теперь вы можете искать профили. "
                        "Просто отправьте название профиля."
                    )
                else:
                    await message.answer("❌ Неверный пароль. Попробуйте ещё раз:")
                return
            
            # Check authorization
            if not self.is_authorized(user_id):
                await message.answer("🔐 Для доступа к боту используйте /start")
                return
            
            # Handle as search query
            await self._handle_search(message, text)
    
    async def _handle_search(self, message: Message, query: str) -> None:
        """Handle profile search."""
        if not query:
            await message.answer("❌ Введите название профиля для поиска")
            return
        
        # Search profiles
        results = await catalog_service.search_profiles(
            query=query,
            limit=self.MAX_RESULTS
        )
        
        if not results:
            await message.answer(f"🔍 По запросу «{query}» ничего не найдено")
            return
        
        # Format results
        if len(results) == 1:
            # Single result - show details
            profile = results[0]
            text = self._format_profile_detail(profile)
            
            if profile.photo_thumb:
                # Send photo with caption
                try:
                    photo_url = f"{settings.BASE_URL}/static/{profile.photo_full or profile.photo_thumb}"
                    await message.answer_photo(photo=photo_url, caption=text)
                except Exception:
                    await message.answer(text)
            else:
                await message.answer(text)
        else:
            # Multiple results - show list
            text = f"🔍 Найдено {len(results)} профилей:\n\n"
            for i, profile in enumerate(results, 1):
                text += self._format_profile_short(profile, i)
            
            if len(results) == self.MAX_RESULTS:
                text += f"\n⚠️ Показаны первые {self.MAX_RESULTS} результатов"
            
            await message.answer(text)
    
    def _format_profile_detail(self, profile) -> str:
        """Format profile for detailed view."""
        lines = [f"📋 *{profile.name}*\n"]
        
        if profile.quantity_per_hanger:
            lines.append(f"📦 Кол-во на подвес: {profile.quantity_per_hanger}")
        
        if profile.length:
            lines.append(f"📏 Длина: {profile.length} мм")
        
        if profile.notes:
            lines.append(f"📝 Примечания: {profile.notes}")
        
        if profile.usage_count:
            lines.append(f"📊 Использований: {profile.usage_count}")
        
        if not profile.photo_thumb:
            lines.append("\n⚠️ Фото отсутствует")
        
        return "\n".join(lines)
    
    def _format_profile_short(self, profile, index: int) -> str:
        """Format profile for list view."""
        photo_icon = "📷" if profile.photo_thumb else "❌"
        return f"{index}. {photo_icon} *{profile.name}*\n"
    
    async def start(self) -> bool:
        """
        Start the Telegram bot.
        
        Returns:
            True if started successfully
        """
        if self._running:
            logger.warning("TelegramBot already running")
            return False
        
        if not settings.TELEGRAM_TOKEN:
            logger.error("TELEGRAM_TOKEN not configured")
            return False
        
        try:
            self._bot = Bot(token=settings.TELEGRAM_TOKEN)
            self._dp = Dispatcher()
            self._setup_handlers()
            
            self._running = True
            logger.info("TelegramBot started")
            
            # Start polling in background
            asyncio.create_task(self._dp.start_polling(self._bot))
            
            return True
        except Exception as e:
            logger.error(f"Failed to start TelegramBot: {e}")
            return False
    
    async def stop(self) -> None:
        """Stop the Telegram bot."""
        if not self._running:
            return
        
        self._running = False
        
        if self._dp:
            await self._dp.stop_polling()
        
        if self._bot:
            await self._bot.session.close()
        
        self._bot = None
        self._dp = None
        
        logger.info("TelegramBot stopped")


# Singleton instance
telegram_bot = TelegramBotService()
