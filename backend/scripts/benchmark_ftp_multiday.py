"""
Benchmark for reading multiple FTP log files.
Tests performance of reading 1-7 days of logs.

Usage:
    # Default (testdata/ftp directory)
    python scripts/benchmark_ftp_multiday.py
    
    # Custom path
    python scripts/benchmark_ftp_multiday.py --path /path/to/ftp/logs
    
    # Test specific days
    python scripts/benchmark_ftp_multiday.py --days 1 2
    
    # Custom path + specific days
    python scripts/benchmark_ftp_multiday.py --path /path/to/logs --days 2 7
"""
import time
import sys
from pathlib import Path
from datetime import date, timedelta

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.ftp_service import FTPService


# Global variable for testdata path (can be overridden)
TESTDATA_PATH = None


def benchmark_read_files(days: int = 2):
    """
    Benchmark reading N days of log files.
    
    Args:
        days: Number of days to read (1-7)
    """
    print("=" * 70)
    print(f"FTP MULTI-DAY READ BENCHMARK - {days} DAYS")
    print("=" * 70)
    
    service = FTPService()
    
    # Get test files for multiple days
    if TESTDATA_PATH:
        testdata_dir = TESTDATA_PATH
    else:
        testdata_dir = Path(__file__).parent.parent.parent / "testdata/ftp"
    
    # Generate file list for N days (going backwards from 2025-11-29)
    base_date = date(2025, 11, 29)
    test_files = []
    total_size = 0
    
    for day_offset in range(days):
        file_date = base_date - timedelta(days=day_offset)
        filename = file_date.strftime("%Y-%m-%d.txt")
        file_path = testdata_dir / filename
        
        if file_path.exists():
            test_files.append(file_path)
            total_size += file_path.stat().st_size
        else:
            print(f"⚠️  File not found: {filename} (using available files)")
    
    if not test_files:
        print(f"❌ No test files found in {testdata_dir}")
        return
    
    print(f"\n📁 Test files:")
    for f in test_files:
        size = f.stat().st_size
        print(f"   • {f.name}: {size:,} bytes ({size / 1024 / 1024:.2f} MB)")
    
    print(f"\n📊 Total data: {total_size:,} bytes ({total_size / 1024 / 1024:.2f} MB)")
    
    # Benchmark: Read and parse N files
    print(f"\n⏱️  Benchmark: Read + Parse {len(test_files)} files")
    
    start = time.time()
    all_events = []
    
    for file_path in test_files:
        # Read file
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Parse events
        events = service.parse_unload_events_cj2m(content)
        all_events.extend(events)
    
    elapsed = time.time() - start
    
    print(f"   ✅ Read {len(test_files)} files in {elapsed:.3f} seconds")
    print(f"   📊 Found {len(all_events):,} total events")
    print(f"   ⚡ Speed: {total_size / elapsed / 1024 / 1024:.2f} MB/s")
    print(f"   📈 Events/sec: {len(all_events) / elapsed:.0f}")
    
    # Benchmark: Multiple reads (simulate API calls)
    print(f"\n⏱️  Benchmark: 10 consecutive reads (simulate API calls)")
    
    times = []
    for i in range(10):
        start = time.time()
        
        all_events = []
        for file_path in test_files:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            events = service.parse_unload_events_cj2m(content)
            all_events.extend(events)
        
        elapsed = time.time() - start
        times.append(elapsed)
    
    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)
    
    print(f"   Average: {avg_time:.3f}s")
    print(f"   Min: {min_time:.3f}s")
    print(f"   Max: {max_time:.3f}s")
    print(f"   📊 {len(all_events):,} events per request")
    
    # Performance analysis
    print(f"\n📊 Performance Analysis:")
    
    if avg_time < 0.1:
        print(f"   ✅ EXCELLENT: < 100ms - Real-time ready!")
    elif avg_time < 0.5:
        print(f"   ✅ GOOD: < 500ms - Acceptable for API")
    elif avg_time < 1.0:
        print(f"   ⚠️  OK: < 1s - Consider caching")
    else:
        print(f"   ❌ SLOW: > 1s - Caching required!")
    
    # Recommendations
    print(f"\n💡 Recommendations:")
    
    if avg_time > 0.5:
        print(f"   • Consider caching parsed events in memory")
        print(f"   • Update cache incrementally (only new events)")
        print(f"   • Cache TTL: 1-5 seconds")
    else:
        print(f"   • Current performance is acceptable")
        print(f"   • Can read directly from files on each request")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Benchmark FTP multi-day file reading')
    parser.add_argument('--path', type=str, help='Path to FTP log files directory (default: testdata/ftp)')
    parser.add_argument('--days', type=int, nargs='+', default=[1, 2, 3, 7], help='Number of days to test (default: 1 2 3 7)')
    
    args = parser.parse_args()
    
    # Override testdata path if provided
    if args.path:
        TESTDATA_PATH = Path(args.path)
        print(f"Using custom path: {TESTDATA_PATH}\n")
    
    # Test different scenarios
    for days in args.days:
        benchmark_read_files(days)
        print("\n")
