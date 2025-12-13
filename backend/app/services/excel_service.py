"""
Excel Service - handles Excel file parsing, caching, and data extraction.
"""
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

import pandas as pd

from app.core.config import settings
from app.core.text_utils import normalize_text


class ExcelService:
    """
    Service for reading and parsing Excel files with production data.
    
    Features:
    - DataFrame caching with file modification detection
    - Profile parsing with processing extraction
    - Product filtering and pagination
    """
    
    def __init__(self):
        self._cache: Optional[pd.DataFrame] = None
        self._cache_mtime: Optional[float] = None
        self._cache_path: Optional[Path] = None
    
    def invalidate_cache(self) -> None:
        """Force cache invalidation."""
        self._cache = None
        self._cache_mtime = None
        self._cache_path = None
    
    def _is_cache_valid(self, file_path: Path) -> bool:
        """Check if cached data is still valid."""
        if self._cache is None:
            return False
        if self._cache_path != file_path:
            return False
        try:
            current_mtime = file_path.stat().st_mtime
            return self._cache_mtime == current_mtime
        except OSError:
            return False
    
    def get_dataframe(
        self,
        file_path: Optional[Path] = None,
        full_dataset: bool = False
    ) -> pd.DataFrame:
        """
        Get DataFrame from Excel file with caching.
        
        Args:
            file_path: Path to Excel file (uses config default if None)
            full_dataset: If True, return all data; if False, filter recent
        
        Returns:
            DataFrame with production data
        """
        path = file_path or settings.excel_path
        if not path or not path.exists():
            return pd.DataFrame()

        # Check cache validity
        if self._is_cache_valid(path):
            df = self._cache
        else:
            # Read Excel file
            try:
                df = pd.read_excel(path, engine='openpyxl')
                self._cache = df
                self._cache_mtime = path.stat().st_mtime
                self._cache_path = path
            except Exception as e:
                # Return cached data if available, empty DataFrame otherwise
                if self._cache is not None:
                    return self._cache
                return pd.DataFrame()
        
        if full_dataset:
            return df
        
        # Filter to recent data (last 7 days by default)
        if 'date' in df.columns or 'Дата' in df.columns:
            date_col = 'date' if 'date' in df.columns else 'Дата'
            try:
                df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
                cutoff = datetime.now() - timedelta(days=7)
                df = df[df[date_col] >= cutoff]
            except Exception:
                pass
        
        return df
    
    def parse_profile_with_processing(self, text: str) -> Dict[str, Any]:
        """
        Parse profile text and extract processing information.
        
        Extracts:
        - Base profile name
        - Processing types (окно, греб, сверло, etc.)
        
        Args:
            text: Raw profile text from Excel
        
        Returns:
            Dict with 'name', 'canonical_name', 'processing' list
        """
        if not text or pd.isna(text):
            return {'name': '', 'canonical_name': '', 'processing': []}
        
        text = str(text).strip()
        processing = []
        
        # Common processing patterns
        patterns = [
            (r'\bокно\b', 'окно'),
            (r'\bгреб\b', 'греб'),
            (r'\bсверло\b', 'сверло'),
            (r'\bфреза\b', 'фреза'),
            (r'\bпаз\b', 'паз'),
            (r'\bотв\b', 'отверстие'),
        ]
        
        text_lower = text.lower()
        for pattern, proc_name in patterns:
            if re.search(pattern, text_lower):
                processing.append(proc_name)
        
        # Extract canonical name (remove processing markers)
        canonical = text
        for pattern, _ in patterns:
            canonical = re.sub(pattern, '', canonical, flags=re.IGNORECASE)
        canonical = re.sub(r'\s+', ' ', canonical).strip()
        canonical = re.sub(r'[+\-*/]+$', '', canonical).strip()
        
        return {
            'name': text,
            'canonical_name': canonical,
            'processing': processing
        }
    
    def split_profiles(self, text: str) -> List[Dict[str, Any]]:
        """
        Split combined profile text into individual profiles.
        
        Handles formats like:
        - "Profile1 + Profile2"
        - "Profile1, Profile2"
        - "Profile1 / Profile2"
        
        Args:
            text: Combined profile text
        
        Returns:
            List of parsed profile dicts
        """
        if not text or pd.isna(text):
            return []
        
        text = str(text).strip()
        
        # Split by common separators
        parts = re.split(r'[+,/]', text)
        
        profiles = []
        for part in parts:
            part = part.strip()
            if part:
                profiles.append(self.parse_profile_with_processing(part))
        
        return profiles if profiles else [self.parse_profile_with_processing(text)]

    def get_products(
        self,
        limit: int = 100,
        days: int = 7,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get products from Excel with optional filtering.
        
        Args:
            limit: Maximum number of records
            days: Number of days to look back
            filters: Optional filters (client, profile, etc.)
        
        Returns:
            List of product dictionaries
        """
        df = self.get_dataframe(full_dataset=True)
        if df.empty:
            return []
        
        # Apply date filter
        date_col = 'date' if 'date' in df.columns else 'Дата' if 'Дата' in df.columns else None
        if date_col:
            try:
                df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
                cutoff = datetime.now() - timedelta(days=days)
                df = df[df[date_col] >= cutoff]
            except Exception:
                pass
        
        # Apply additional filters
        if filters:
            for key, value in filters.items():
                if key in df.columns and value:
                    df = df[df[key].astype(str).str.contains(str(value), case=False, na=False)]
        
        # Convert to list of dicts
        records = df.head(limit).to_dict('records')
        return records
    
    def get_recent_profiles(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent profile records.
        
        Args:
            limit: Maximum number of records (default 50)
        
        Returns:
            List of recent records with profile info
        """
        df = self.get_dataframe(full_dataset=True)
        if df.empty:
            return []
        
        # Sort by date descending if date column exists
        date_col = 'date' if 'date' in df.columns else 'Дата' if 'Дата' in df.columns else None
        if date_col:
            try:
                df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
                df = df.sort_values(date_col, ascending=False)
            except Exception:
                pass
        
        # Limit results
        df = df.head(limit)
        
        return df.to_dict('records')
    
    def get_recent_missing_profiles(
        self,
        limit: int = 50,
        profile_checker: Optional[callable] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent unique profiles that don't have photos.
        
        Args:
            limit: Maximum number of unique profiles
            profile_checker: Optional function to check if profile has photo
        
        Returns:
            List of unique profiles without photos
        """
        df = self.get_dataframe(full_dataset=True)
        if df.empty:
            return []
        
        # Find profile column
        profile_col = None
        for col in ['profile', 'Профиль', 'профиль', 'Profile']:
            if col in df.columns:
                profile_col = col
                break
        
        if not profile_col:
            return []
        
        # Sort by date descending
        date_col = 'date' if 'date' in df.columns else 'Дата' if 'Дата' in df.columns else None
        if date_col:
            try:
                df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
                df = df.sort_values(date_col, ascending=False)
            except Exception:
                pass
        
        # Get unique profiles
        seen = set()
        results = []
        
        for _, row in df.iterrows():
            profile_name = str(row.get(profile_col, '')).strip()
            if not profile_name or profile_name in seen:
                continue
            
            # Check if profile has photo (if checker provided)
            if profile_checker and profile_checker(profile_name):
                continue
            
            seen.add(profile_name)
            results.append(row.to_dict())
            
            if len(results) >= limit:
                break
        
        return results


# Singleton instance
excel_service = ExcelService()
