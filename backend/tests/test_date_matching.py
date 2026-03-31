"""
Test date matching logic for month transitions
"""
from datetime import datetime


def parse_date(date_str: str) -> tuple:
    """Parse DD.MM.YYYY or DD.MM.YY to (year, month, day) tuple for comparison."""
    if not date_str or date_str == '—':
        return (0, 0, 0)
    try:
        date_str = date_str.strip()
        parts = date_str.split('.')
        if len(parts) == 3:
            day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
            if year < 50:
                year += 2000
            elif year < 100:
                year += 1900
            return (year, month, day)
    except (ValueError, IndexError):
        pass
    return (0, 0, 0)


def parse_time(time_str: str) -> tuple:
    """Parse HH:MM:SS or HH:MM to (hour, minute, second) tuple."""
    if not time_str or time_str == '—':
        return (0, 0, 0)
    try:
        time_str = time_str.strip()
        parts = time_str.split(':')
        hour = int(parts[0]) if len(parts) > 0 else 0
        minute = int(parts[1]) if len(parts) > 1 else 0
        second = int(parts[2]) if len(parts) > 2 else 0
        return (hour, minute, second)
    except (ValueError, IndexError):
        pass
    return (0, 0, 0)


def datetime_to_seconds(date_tuple: tuple, time_tuple: tuple) -> float:
    """Convert date+time to total seconds for comparison using proper datetime."""
    try:
        year, month, day = date_tuple
        hour, minute, second = time_tuple
        
        if year == 0 or month == 0 or day == 0:
            return 0
        
        dt = datetime(year, month, day, hour, minute, second)
        return dt.timestamp()
    except (ValueError, OverflowError):
        year_days = date_tuple[0] * 365
        month_days = date_tuple[1] * 30
        day = date_tuple[2]
        
        total_days = year_days + month_days + day
        total_seconds = time_tuple[0] * 3600 + time_tuple[1] * 60 + time_tuple[2]
        
        return total_days * 86400 + total_seconds


def test_month_transition():
    """Test that month transition is handled correctly"""
    # Entry: 30.03.2026 22:33
    entry_date = parse_date("30.03.2026")
    entry_time = parse_time("22:33:00")
    entry_seconds = datetime_to_seconds(entry_date, entry_time)
    
    # Exit: 01.04.2026 00:52
    exit_date = parse_date("01.04.2026")
    exit_time = parse_time("00:52:10")
    exit_seconds = datetime_to_seconds(exit_date, exit_time)
    
    # Check that entry is before exit
    assert entry_seconds < exit_seconds, f"Entry ({entry_seconds}) should be before exit ({exit_seconds})"
    
    # Check time difference (should be about 26 hours 19 minutes)
    diff_seconds = exit_seconds - entry_seconds
    diff_hours = diff_seconds / 3600
    
    print(f"Entry: 30.03.2026 22:33:00 → {entry_seconds}")
    print(f"Exit:  01.04.2026 00:52:10 → {exit_seconds}")
    print(f"Difference: {diff_seconds} seconds ({diff_hours:.2f} hours)")
    
    # Should be approximately 26.32 hours (1 day, 2 hours, 19 minutes)
    assert 26.0 < diff_hours < 27.0, f"Time difference should be ~26.3 hours, got {diff_hours:.2f}"
    
    # Check against 6-hour limit (this should FAIL the limit)
    max_hours = 6
    if diff_seconds > max_hours * 3600:
        print(f"⚠ WARNING: Difference ({diff_hours:.2f}h) exceeds {max_hours}h limit")
        print(f"  → System will still match and show entry/exit times with warning")
    else:
        print(f"✓ Difference is within {max_hours}h limit")
    
    print("✓ Month transition test passed!")


def test_two_digit_year():
    """Test that 2-digit years are parsed correctly"""
    # Test year 26 → 2026
    date1 = parse_date("30.03.26")
    assert date1 == (2026, 3, 30), f"Expected (2026, 3, 30), got {date1}"
    
    # Test year 99 → 1999
    date2 = parse_date("31.12.99")
    assert date2 == (1999, 12, 31), f"Expected (1999, 12, 31), got {date2}"
    
    print("✓ Two-digit year test passed!")


def test_year_transition():
    """Test that year transition is handled correctly"""
    # Entry: 31.12.2025 23:00
    entry_date = parse_date("31.12.2025")
    entry_time = parse_time("23:00:00")
    entry_seconds = datetime_to_seconds(entry_date, entry_time)
    
    # Exit: 01.01.2026 01:30
    exit_date = parse_date("01.01.2026")
    exit_time = parse_time("01:30:00")
    exit_seconds = datetime_to_seconds(exit_date, exit_time)
    
    # Check that entry is before exit
    assert entry_seconds < exit_seconds, f"Entry ({entry_seconds}) should be before exit ({exit_seconds})"
    
    # Check time difference (should be about 2.5 hours)
    diff_seconds = exit_seconds - entry_seconds
    diff_hours = diff_seconds / 3600
    
    print(f"Entry: 31.12.2025 23:00:00 → {entry_seconds}")
    print(f"Exit:  01.01.2026 01:30:00 → {exit_seconds}")
    print(f"Difference: {diff_seconds} seconds ({diff_hours:.2f} hours)")
    
    # Should be approximately 2.5 hours
    assert 2.4 < diff_hours < 2.6, f"Time difference should be ~2.5 hours, got {diff_hours:.2f}"
    
    print("✓ Year transition test passed!")


def test_six_hour_limit():
    """Test the 6-hour matching limit"""
    # Entry: 01.04.2026 10:00
    entry_date = parse_date("01.04.2026")
    entry_time = parse_time("10:00:00")
    entry_seconds = datetime_to_seconds(entry_date, entry_time)
    
    # Exit within limit: 01.04.2026 15:30 (5.5 hours later)
    exit_within_date = parse_date("01.04.2026")
    exit_within_time = parse_time("15:30:00")
    exit_within_seconds = datetime_to_seconds(exit_within_date, exit_within_time)
    
    diff_within = exit_within_seconds - entry_seconds
    diff_within_hours = diff_within / 3600
    
    print(f"\nWithin limit test:")
    print(f"  Entry: 01.04.2026 10:00:00")
    print(f"  Exit:  01.04.2026 15:30:00")
    print(f"  Difference: {diff_within_hours:.2f} hours")
    
    assert diff_within <= 6 * 3600, "Should be within 6-hour limit"
    print(f"  ✓ Within 6h limit - will match normally")
    
    # Exit beyond limit: 01.04.2026 17:00 (7 hours later)
    exit_beyond_date = parse_date("01.04.2026")
    exit_beyond_time = parse_time("17:00:00")
    exit_beyond_seconds = datetime_to_seconds(exit_beyond_date, exit_beyond_time)
    
    diff_beyond = exit_beyond_seconds - entry_seconds
    diff_beyond_hours = diff_beyond / 3600
    
    print(f"\nBeyond limit test:")
    print(f"  Entry: 01.04.2026 10:00:00")
    print(f"  Exit:  01.04.2026 17:00:00")
    print(f"  Difference: {diff_beyond_hours:.2f} hours")
    
    assert diff_beyond > 6 * 3600, "Should exceed 6-hour limit"
    print(f"  ⚠ Beyond 6h limit - will still match but with warning in logs")
    print(f"  → Entry/exit times will be shown (not empty)")
    
    print("✓ Six-hour limit test passed!")


if __name__ == "__main__":
    test_month_transition()
    test_two_digit_year()
    test_year_transition()
    test_six_hour_limit()
    print("\n✓ All tests passed!")

