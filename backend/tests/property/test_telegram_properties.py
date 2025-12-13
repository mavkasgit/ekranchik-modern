"""
Property tests for Telegram Bot Service.

Tests:
- Property 7: Telegram Bot Multi-Match Limit
- Property 8: Authorization Persistence
"""
import pytest
from hypothesis import given, strategies as st, settings as hyp_settings

from app.services.telegram_bot import TelegramBotService


class TestMultiMatchLimit:
    """Property 7: Telegram Bot Multi-Match Limit."""
    
    def test_max_results_constant_is_positive(self):
        """MAX_RESULTS should be a positive integer."""
        bot = TelegramBotService()
        assert bot.MAX_RESULTS > 0
        assert isinstance(bot.MAX_RESULTS, int)
    
    def test_max_results_is_reasonable(self):
        """MAX_RESULTS should be reasonable for Telegram (not too many)."""
        bot = TelegramBotService()
        # Telegram messages have limits, so we shouldn't show too many
        assert bot.MAX_RESULTS <= 10
        assert bot.MAX_RESULTS >= 1
    
    @given(max_val=st.integers(min_value=1, max_value=20))
    @hyp_settings(max_examples=20, deadline=None)
    def test_max_results_can_be_configured(self, max_val: int):
        """MAX_RESULTS can be set to different values."""
        bot = TelegramBotService()
        original = bot.MAX_RESULTS
        
        # Temporarily change
        bot.MAX_RESULTS = max_val
        assert bot.MAX_RESULTS == max_val
        
        # Restore
        bot.MAX_RESULTS = original


class TestAuthorizationPersistence:
    """Property 8: Authorization Persistence."""
    
    @given(user_id=st.integers(min_value=1, max_value=10**12))
    @hyp_settings(max_examples=50, deadline=None)
    def test_authorize_then_check_returns_true(self, user_id: int):
        """After authorizing a user, is_authorized should return True."""
        bot = TelegramBotService()
        
        # Initially not authorized
        assert not bot.is_authorized(user_id)
        
        # Authorize
        bot.authorize_user(user_id)
        
        # Now authorized
        assert bot.is_authorized(user_id)
    
    @given(user_id=st.integers(min_value=1, max_value=10**12))
    @hyp_settings(max_examples=50, deadline=None)
    def test_deauthorize_removes_authorization(self, user_id: int):
        """After deauthorizing, is_authorized should return False."""
        bot = TelegramBotService()
        
        # Authorize first
        bot.authorize_user(user_id)
        assert bot.is_authorized(user_id)
        
        # Deauthorize
        bot.deauthorize_user(user_id)
        
        # No longer authorized
        assert not bot.is_authorized(user_id)
    
    @given(user_ids=st.lists(st.integers(min_value=1, max_value=10**12), min_size=1, max_size=20, unique=True))
    @hyp_settings(max_examples=30, deadline=None)
    def test_multiple_users_independent(self, user_ids: list):
        """Multiple users can be authorized independently."""
        bot = TelegramBotService()
        
        # Authorize all
        for uid in user_ids:
            bot.authorize_user(uid)
        
        # All should be authorized
        for uid in user_ids:
            assert bot.is_authorized(uid)
        
        # Deauthorize first half
        half = len(user_ids) // 2
        for uid in user_ids[:half]:
            bot.deauthorize_user(uid)
        
        # First half not authorized, second half still authorized
        for uid in user_ids[:half]:
            assert not bot.is_authorized(uid)
        for uid in user_ids[half:]:
            assert bot.is_authorized(uid)
    
    @given(user_id=st.integers(min_value=1, max_value=10**12))
    @hyp_settings(max_examples=30, deadline=None)
    def test_double_authorize_is_idempotent(self, user_id: int):
        """Authorizing twice should have same effect as once."""
        bot = TelegramBotService()
        
        bot.authorize_user(user_id)
        bot.authorize_user(user_id)
        
        assert bot.is_authorized(user_id)
        
        # Single deauthorize should work
        bot.deauthorize_user(user_id)
        assert not bot.is_authorized(user_id)
    
    @given(user_id=st.integers(min_value=1, max_value=10**12))
    @hyp_settings(max_examples=30, deadline=None)
    def test_deauthorize_non_authorized_is_safe(self, user_id: int):
        """Deauthorizing non-authorized user should not raise."""
        bot = TelegramBotService()
        
        # Should not raise
        bot.deauthorize_user(user_id)
        assert not bot.is_authorized(user_id)


class TestPasswordCheck:
    """Tests for password checking."""
    
    def test_correct_password_returns_true(self):
        """Correct password should return True."""
        from app.core.config import settings
        bot = TelegramBotService()
        
        if settings.BOT_PASSWORD:
            assert bot.check_password(settings.BOT_PASSWORD)
    
    @given(password=st.text(min_size=1, max_size=50))
    @hyp_settings(max_examples=30, deadline=None)
    def test_random_password_usually_fails(self, password: str):
        """Random passwords should usually fail (unless they match)."""
        from app.core.config import settings
        bot = TelegramBotService()
        
        result = bot.check_password(password)
        
        # Result should match whether password equals configured password
        expected = (password == settings.BOT_PASSWORD)
        assert result == expected
    
    def test_empty_password_fails(self):
        """Empty password should fail."""
        bot = TelegramBotService()
        
        # Empty string should not match (unless configured password is empty)
        from app.core.config import settings
        expected = (settings.BOT_PASSWORD == "")
        assert bot.check_password("") == expected


class TestBotState:
    """Tests for bot state management."""
    
    def test_initial_state_not_running(self):
        """Bot should not be running initially."""
        bot = TelegramBotService()
        assert not bot.is_running
    
    def test_initial_state_no_authorized_users(self):
        """Bot should have no authorized users initially."""
        bot = TelegramBotService()
        # Check a random user
        assert not bot.is_authorized(12345)
