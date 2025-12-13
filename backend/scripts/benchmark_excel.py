"""
Benchmark script for comparing Excel reading engines.
Run from backend folder: python scripts/benchmark_excel.py
"""
import sys
import time
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

# Excel file path
EXCEL_PATH = Path("../testdata/Учет КПЗ 2025.xlsm")

if not EXCEL_PATH.exists():
    print(f"❌ File not found: {EXCEL_PATH}")
    sys.exit(1)

print(f"📄 Testing file: {EXCEL_PATH}")
print(f"📦 File size: {EXCEL_PATH.stat().st_size / 1024 / 1024:.2f} MB")
print("=" * 60)

# Common read parameters
READ_PARAMS = {
    "sheet_name": "Подвесы",
    "skiprows": [0, 1],
    "usecols": [3, 4, 5, 7, 10, 11, 12, 16, 19],
}

COLUMN_NAMES = ['date', 'number', 'time', 'material_type', 'kpz_number', 
                'client', 'profile', 'color', 'lamels_qty']

results = []

# Test 1: openpyxl (default)
print("\n🔧 Test 1: openpyxl engine")
try:
    times = []
    for i in range(3):
        start = time.time()
        df = pd.read_excel(EXCEL_PATH, engine='openpyxl', **READ_PARAMS)
        elapsed = time.time() - start
        times.append(elapsed)
        print(f"   Run {i+1}: {elapsed:.3f}s ({len(df)} rows)")
    
    avg_time = sum(times) / len(times)
    results.append(("openpyxl", avg_time, len(df)))
    print(f"   ✅ Average: {avg_time:.3f}s")
except Exception as e:
    print(f"   ❌ Error: {e}")
    results.append(("openpyxl", None, 0))

# Test 2: calamine (fast Rust-based)
print("\n🔧 Test 2: calamine engine (Rust-based, fast)")
try:
    times = []
    for i in range(3):
        start = time.time()
        df = pd.read_excel(EXCEL_PATH, engine='calamine', **READ_PARAMS)
        elapsed = time.time() - start
        times.append(elapsed)
        print(f"   Run {i+1}: {elapsed:.3f}s ({len(df)} rows)")
    
    avg_time = sum(times) / len(times)
    results.append(("calamine", avg_time, len(df)))
    print(f"   ✅ Average: {avg_time:.3f}s")
except ImportError:
    print("   ⚠️ Not installed. Install with: pip install python-calamine")
    results.append(("calamine", None, 0))
except Exception as e:
    print(f"   ❌ Error: {e}")
    results.append(("calamine", None, 0))

# Test 3: xlrd (only for .xls, not .xlsx/.xlsm)
print("\n🔧 Test 3: xlrd engine (legacy, .xls only)")
print("   ⏭️ Skipped - xlrd doesn't support .xlsm files")

# Test 4: Read with nrows limit
print("\n🔧 Test 4: openpyxl with nrows=1000 (limited rows)")
try:
    times = []
    for i in range(3):
        start = time.time()
        df = pd.read_excel(EXCEL_PATH, engine='openpyxl', nrows=1000, **READ_PARAMS)
        elapsed = time.time() - start
        times.append(elapsed)
        print(f"   Run {i+1}: {elapsed:.3f}s ({len(df)} rows)")
    
    avg_time = sum(times) / len(times)
    results.append(("openpyxl+nrows", avg_time, len(df)))
    print(f"   ✅ Average: {avg_time:.3f}s")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 5: calamine with nrows
print("\n🔧 Test 5: calamine with nrows=1000")
try:
    times = []
    for i in range(3):
        start = time.time()
        df = pd.read_excel(EXCEL_PATH, engine='calamine', nrows=1000, **READ_PARAMS)
        elapsed = time.time() - start
        times.append(elapsed)
        print(f"   Run {i+1}: {elapsed:.3f}s ({len(df)} rows)")
    
    avg_time = sum(times) / len(times)
    results.append(("calamine+nrows", avg_time, len(df)))
    print(f"   ✅ Average: {avg_time:.3f}s")
except ImportError:
    print("   ⚠️ calamine not installed")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Summary
print("\n" + "=" * 60)
print("📊 SUMMARY")
print("=" * 60)
print(f"{'Engine':<20} {'Time (avg)':<15} {'Rows':<10} {'Speed':<15}")
print("-" * 60)

baseline = None
for engine, avg_time, rows in results:
    if avg_time is not None:
        if baseline is None:
            baseline = avg_time
            speed = "baseline"
        else:
            speedup = baseline / avg_time
            speed = f"{speedup:.1f}x faster"
        print(f"{engine:<20} {avg_time:.3f}s{'':<10} {rows:<10} {speed:<15}")
    else:
        print(f"{engine:<20} {'N/A':<15} {rows:<10} {'—':<15}")

print("\n💡 RECOMMENDATIONS:")
print("   1. Install calamine for 5-50x speedup: pip install python-calamine")
print("   2. Use caching to avoid re-reading unchanged files")
print("   3. Consider converting to CSV for fastest reads")
