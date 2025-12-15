#!/usr/bin/env python3
"""
Comprehensive FTP connection and file testing script.

Usage:
    python scripts/test_ftp_connection.py                    # Test today's file
    python scripts/test_ftp_connection.py --date 2025-12-13  # Test specific date
    python scripts/test_ftp_connection.py --days 2           # Test last 2 days
    python scripts/test_ftp_connection.py --all              # Run all tests
"""

import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ftplib import FTP, error_perm
from app.core.config import settings


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.RESET}\n")


def print_success(text: str):
    print(f"{Colors.GREEN}✓ {text}{Colors.RESET}")


def print_error(text: str):
    print(f"{Colors.RED}✗ {text}{Colors.RESET}")


def print_warning(text: str):
    print(f"{Colors.YELLOW}⚠ {text}{Colors.RESET}")


def print_info(text: str):
    print(f"{Colors.BLUE}ℹ {text}{Colors.RESET}")


def test_connection() -> bool:
    """Test 1: Basic FTP connection"""
    print_header("TEST 1: FTP Connection")
    
    try:
        print_info(f"Connecting to {settings.FTP_HOST}:{settings.FTP_PORT}...")
        start = time.time()
        
        ftp = FTP()
        ftp.connect(settings.FTP_HOST, settings.FTP_PORT, timeout=10)
        
        connect_time = time.time() - start
        print_success(f"Connected in {connect_time:.3f}s")
        
        print_info(f"Logging in as {settings.FTP_USER}...")
        start = time.time()
        
        ftp.login(settings.FTP_USER, settings.FTP_PASSWORD)
        
        login_time = time.time() - start
        print_success(f"Logged in in {login_time:.3f}s")
        
        # Get welcome message
        welcome = ftp.getwelcome()
        print_info(f"Server: {welcome}")
        
        ftp.quit()
        print_success("Connection test PASSED")
        return True
        
    except Exception as e:
        print_error(f"Connection test FAILED: {e}")
        return False


def test_base_path() -> bool:
    """Test 2: Base path accessibility"""
    print_header("TEST 2: Base Path Access")
    
    try:
        ftp = FTP()
        ftp.connect(settings.FTP_HOST, settings.FTP_PORT, timeout=10)
        ftp.login(settings.FTP_USER, settings.FTP_PASSWORD)
        
        print_info(f"Changing to directory: {settings.FTP_BASE_PATH}")
        start = time.time()
        
        ftp.cwd(settings.FTP_BASE_PATH)
        
        cwd_time = time.time() - start
        print_success(f"Changed directory in {cwd_time:.3f}s")
        
        # Get current directory
        current = ftp.pwd()
        print_info(f"Current directory: {current}")
        
        ftp.quit()
        print_success("Base path test PASSED")
        return True
        
    except Exception as e:
        print_error(f"Base path test FAILED: {e}")
        return False


def test_list_files() -> bool:
    """Test 3: List files in base path"""
    print_header("TEST 3: List Files")
    
    try:
        ftp = FTP()
        ftp.connect(settings.FTP_HOST, settings.FTP_PORT, timeout=10)
        ftp.login(settings.FTP_USER, settings.FTP_PASSWORD)
        ftp.cwd(settings.FTP_BASE_PATH)
        
        print_info("Listing files...")
        start = time.time()
        
        files = []
        ftp.retrlines('LIST', files.append)
        
        list_time = time.time() - start
        print_success(f"Listed {len(files)} items in {list_time:.3f}s")
        
        # Show last 10 files
        print_info("Last 10 items:")
        for line in files[-10:]:
            print(f"  {line}")
        
        ftp.quit()
        print_success("List files test PASSED")
        return True
        
    except Exception as e:
        print_error(f"List files test FAILED: {e}")
        return False


def test_file_exists(date: datetime) -> tuple[bool, str]:
    """Test 4: Check if specific date file exists"""
    filename = date.strftime("%Y-%m-%d.txt")
    print_header(f"TEST 4: File Existence - {filename}")
    
    try:
        ftp = FTP()
        ftp.connect(settings.FTP_HOST, settings.FTP_PORT, timeout=10)
        ftp.login(settings.FTP_USER, settings.FTP_PASSWORD)
        ftp.cwd(settings.FTP_BASE_PATH)
        
        print_info(f"Checking if {filename} exists...")
        
        # Try to get file size
        try:
            size = ftp.size(filename)
            print_success(f"File exists! Size: {size:,} bytes ({size / 1024 / 1024:.2f} MB)")
            
            ftp.quit()
            return True, filename
            
        except error_perm:
            print_warning(f"File {filename} does not exist")
            ftp.quit()
            return False, filename
        
    except Exception as e:
        print_error(f"File existence test FAILED: {e}")
        return False, filename


def test_file_download(filename: str) -> bool:
    """Test 5: Download and parse file"""
    print_header(f"TEST 5: Download & Parse - {filename}")
    
    try:
        ftp = FTP()
        ftp.connect(settings.FTP_HOST, settings.FTP_PORT, timeout=10)
        ftp.login(settings.FTP_USER, settings.FTP_PASSWORD)
        ftp.cwd(settings.FTP_BASE_PATH)
        
        print_info(f"Downloading {filename}...")
        start = time.time()
        
        lines = []
        def callback(line):
            lines.append(line)
        
        ftp.retrlines(f'RETR {filename}', callback)
        
        download_time = time.time() - start
        print_success(f"Downloaded {len(lines):,} lines in {download_time:.3f}s")
        print_info(f"Speed: {len(lines) / download_time:.0f} lines/sec")
        
        # Parse events
        print_info("Parsing events...")
        start = time.time()
        
        event_count = 0
        for line in lines:
            if "Команда от CJ2M: Разгрузка подвеса -" in line:
                event_count += 1
        
        parse_time = time.time() - start
        print_success(f"Found {event_count} events in {parse_time:.3f}s")
        
        # Show first 3 events
        if event_count > 0:
            print_info("First 3 events:")
            count = 0
            for line in lines:
                if "Команда от CJ2M: Разгрузка подвеса -" in line:
                    print(f"  {line}")
                    count += 1
                    if count >= 3:
                        break
        
        ftp.quit()
        print_success("Download & parse test PASSED")
        return True
        
    except Exception as e:
        print_error(f"Download & parse test FAILED: {e}")
        return False


def test_multiday_download(days: int) -> bool:
    """Test 6: Download multiple days"""
    print_header(f"TEST 6: Multi-Day Download ({days} days)")
    
    try:
        ftp = FTP()
        ftp.connect(settings.FTP_HOST, settings.FTP_PORT, timeout=10)
        ftp.login(settings.FTP_USER, settings.FTP_PASSWORD)
        ftp.cwd(settings.FTP_BASE_PATH)
        
        total_lines = 0
        total_events = 0
        total_time = 0
        
        for i in range(days):
            date = datetime.now() - timedelta(days=i)
            filename = date.strftime("%Y-%m-%d.txt")
            
            print_info(f"Day {i+1}/{days}: {filename}")
            
            try:
                start = time.time()
                lines = []
                ftp.retrlines(f'RETR {filename}', lines.append)
                download_time = time.time() - start
                
                events = sum(1 for line in lines if "Команда от CJ2M: Разгрузка подвеса -" in line)
                
                total_lines += len(lines)
                total_events += events
                total_time += download_time
                
                print_success(f"  {len(lines):,} lines, {events} events in {download_time:.3f}s")
                
            except error_perm:
                print_warning(f"  File not found, skipping")
        
        print_info(f"\nTotal: {total_lines:,} lines, {total_events} events in {total_time:.3f}s")
        print_info(f"Average: {total_time/days:.3f}s per file")
        
        ftp.quit()
        print_success("Multi-day download test PASSED")
        return True
        
    except Exception as e:
        print_error(f"Multi-day download test FAILED: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Comprehensive FTP testing')
    parser.add_argument('--date', type=str, help='Test specific date (YYYY-MM-DD)')
    parser.add_argument('--days', type=int, default=1, help='Number of days to test (default: 1)')
    parser.add_argument('--all', action='store_true', help='Run all tests')
    
    args = parser.parse_args()
    
    print(f"\n{Colors.BOLD}FTP Connection Test Suite{Colors.RESET}")
    print(f"Host: {settings.FTP_HOST}:{settings.FTP_PORT}")
    print(f"User: {settings.FTP_USER}")
    print(f"Path: {settings.FTP_BASE_PATH}")
    
    results = []
    
    # Test 1: Connection
    results.append(("Connection", test_connection()))
    
    # Test 2: Base path
    results.append(("Base Path", test_base_path()))
    
    # Test 3: List files
    results.append(("List Files", test_list_files()))
    
    # Test 4 & 5: File existence and download
    if args.date:
        test_date = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        test_date = datetime.now()
    
    exists, filename = test_file_exists(test_date)
    results.append((f"File Exists ({filename})", exists))
    
    if exists:
        results.append((f"Download ({filename})", test_file_download(filename)))
    
    # Test 6: Multi-day (if requested)
    if args.all or args.days > 1:
        results.append((f"Multi-Day ({args.days} days)", test_multiday_download(args.days)))
    
    # Summary
    print_header("TEST SUMMARY")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        if result:
            print_success(f"{name}")
        else:
            print_error(f"{name}")
    
    print(f"\n{Colors.BOLD}Results: {passed}/{total} tests passed{Colors.RESET}")
    
    if passed == total:
        print_success("All tests PASSED! ✓")
        return 0
    else:
        print_error(f"{total - passed} test(s) FAILED! ✗")
        return 1


if __name__ == "__main__":
    sys.exit(main())
