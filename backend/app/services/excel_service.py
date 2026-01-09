"""
Excel Service - handles Excel file parsing, caching, and data extraction.
"""
import os
import re
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

import pandas as pd

from app.core.config import settings
from app.core.text_utils import normalize_text

logger = logging.getLogger(__name__)


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
        sheet_name: str = "Подвесы",
        full_dataset: bool = False
    ) -> pd.DataFrame:
        """
        Get DataFrame from Excel file with caching.
        
        Args:
            file_path: Path to Excel file (uses config default if None)
            sheet_name: Name of the sheet to read (default: "Подвесы")
            full_dataset: If True, return all data; if False, filter recent
        
        Returns:
            DataFrame with production data
        """
        path = file_path or settings.excel_path
        if not path or not path.exists():
            return pd.DataFrame()

        # Check cache validity
        if self._is_cache_valid(path):
            logger.info(f"[CACHE HIT] Using cached data: {len(self._cache)} rows")
            df = self._cache.copy()
        else:
            # Read Excel file from specific sheet
            # skiprows=[0, 1] - skip instruction rows
            # usecols - specific columns matching original app.py
            start_time = time.time()
            try:
                # Use calamine engine for 4x faster reading (Rust-based)
                df = pd.read_excel(
                    path, 
                    sheet_name=sheet_name, 
                    skiprows=[0, 1],
                    usecols=[3, 4, 5, 7, 8, 10, 11, 12, 16, 19],
                    engine='calamine'
                )
                read_time = time.time() - start_time
                logger.info(f"[EXCEL READ] {len(df)} rows in {read_time:.2f}s from {path.name} (calamine)")
                
                # Rename columns to match expected format
                df.columns = ['date', 'number', 'time', 'material_type', 'defect',
                              'kpz_number', 'client', 'profile', 'color', 'lamels_qty']
                
                # Remove completely empty rows
                df = df.dropna(how='all')
                
                # Filter: keep rows where date OR number is present
                df = df[(pd.notna(df['date'])) | (pd.notna(df['number']))]
                
                logger.info(f"[EXCEL FILTERED] {len(df)} valid rows after filtering")
                
                self._cache = df
                self._cache_mtime = path.stat().st_mtime
                self._cache_path = path
            except Exception as e:
                logger.error(f"[EXCEL ERROR] Failed to read Excel file: {e}")
                if self._cache is not None:
                    return self._cache.copy()
                return pd.DataFrame()
        
        if full_dataset:
            return df
        
        # Filter to recent data (last 7 days by default)
        if 'date' in df.columns:
            try:
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
                cutoff = datetime.now() - timedelta(days=7)
                df = df[df['date'] >= cutoff]
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
        filters: Optional[Dict[str, Any]] = None,
        from_end: bool = True,
        loading_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get products from Excel with optional filtering.
        
        Args:
            limit: Maximum number of records
            days: Number of days to look back
            filters: Optional filters (client, profile, etc.)
            from_end: If True, read last N rows (default); if False, read first N
            loading_only: If True, only return loading rows (date+material filled, time empty)
        
        Returns:
            List of product dictionaries
        """
        df = self.get_dataframe(full_dataset=True)
        if df.empty:
            return []
        
        # Get last N rows from the end of the file
        # Keep original order: oldest first, newest last
        if from_end:
            df = df.tail(limit * 3 if loading_only else limit)  # Get more rows if filtering
        else:
            # Apply date filter only when not reading from end
            if 'date' in df.columns:
                try:
                    df['date'] = pd.to_datetime(df['date'], errors='coerce')
                    cutoff = datetime.now() - timedelta(days=days)
                    df = df[df['date'] >= cutoff]
                except Exception:
                    pass
            df = df.head(limit * 3 if loading_only else limit)
        
        # Apply additional filters
        if filters:
            for key, value in filters.items():
                if key in df.columns and value:
                    df = df[df[key].astype(str).str.contains(str(value), case=False, na=False)]
        
        # Process and format records
        records = self._process_dataframe(df, loading_only=loading_only)
        
        # Apply limit after filtering
        if loading_only and len(records) > limit:
            records = records[-limit:]  # Take last N (newest)
        
        return records[::-1]
    
    def _process_dataframe(self, df: pd.DataFrame, loading_only: bool = False) -> List[Dict[str, Any]]:
        """
        Process DataFrame and return list of formatted product dicts.
        Handles date/time formatting and lamels parsing.
        
        Args:
            loading_only: If True, only include loading rows (date+material filled, time empty)
        """
        products = []
        for _, row in df.iterrows():
            date_val = row.get('date')
            material_type = row.get('material_type')
            time_val = row.get('time')
            
            # For loading_only mode: strict filtering
            if loading_only:
                # Date must be filled
                if pd.isna(date_val) or not date_val:
                    continue
                # Material type must be filled
                if pd.isna(material_type) or not material_type or str(material_type).strip() in ('', '—'):
                    continue
                # Time must be EMPTY (this indicates a loading row, not unloading)
                if pd.notna(time_val) and str(time_val).strip() not in ('', '—', 'nan', 'NaT'):
                    continue
            # Handle lamels (can be "30+30" or number)
            lamels = row.get('lamels_qty')
            if pd.notna(lamels):
                try:
                    lamels_display = int(float(lamels))
                except (ValueError, TypeError):
                    lamels_display = str(lamels)
            else:
                lamels_display = 0
            
            # Format time (remove seconds)
            time_str = '—'
            time_val = row.get('time')
            if pd.notna(time_val):
                if hasattr(time_val, 'strftime'):
                    time_str = time_val.strftime('%H:%M')
                else:
                    time_val_str = str(time_val)
                    if ':' in time_val_str:
                        parts = time_val_str.split(':')
                        time_str = f"{parts[0]}:{parts[1]}"
                    else:
                        time_str = time_val_str
            
            # Format date
            date_str = '—'
            date_val = row.get('date')
            if pd.notna(date_val):
                try:
                    if hasattr(date_val, 'strftime'):
                        date_str = date_val.strftime('%d.%m.%y')
                    else:
                        date_str = str(date_val)
                except Exception:
                    date_str = str(date_val)
            
            profile_name = row.get('profile', '—')
            if pd.isna(profile_name) or not profile_name:
                profile_name = '—'
            
            # Check for defect (брак)
            defect_val = row.get('defect')
            is_defect = False
            if pd.notna(defect_val):
                defect_str = str(defect_val).lower().strip()
                is_defect = 'брак' in defect_str
            
            products.append({
                'number': row.get('number') if pd.notna(row.get('number')) else '—',
                'date': date_str,
                'time': time_str,
                'client': row.get('client') if pd.notna(row.get('client')) else '—',
                'profile': str(profile_name).strip(),
                'color': row.get('color') if pd.notna(row.get('color')) else '—',
                'lamels_qty': lamels_display,
                'kpz_number': row.get('kpz_number') if pd.notna(row.get('kpz_number')) else '—',
                'material_type': row.get('material_type') if pd.notna(row.get('material_type')) else '—',
                'is_defect': is_defect,
            })
        
        return products
    
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
    
    def get_unloading_products(
        self,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get unloading products - rows that have time filled in.
        
        "Выгрузка старая" - shows rows where time column is not empty,
        meaning the product has been unloaded from the line.
        
        Args:
            limit: Maximum number of records
        
        Returns:
            List of product dictionaries with time filled
        """
        df = self.get_dataframe(full_dataset=True)
        if df.empty:
            return []
        
        # Filter: only rows with time (выгрузка = unloaded)
        df_with_time = df[pd.notna(df['time'])]
        
        # Get last N rows (most recent unloads)
        # Keep original order: oldest first, newest last
        df_with_time = df_with_time.tail(limit)
        
        return self._process_dataframe(df_with_time)

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
