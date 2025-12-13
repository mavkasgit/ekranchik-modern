"""
Test script for FTP simulation.
Verifies that simulation starts and processes events correctly.
"""
import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.ftp_service import ftp_service
from app.services.ftp_poller import ftp_poller
from app.services.websocket_manager import websocket_manager


async def test_simulation():
    """Test FTP simulation end-to-end."""
    print("=" * 60)
    print("FTP SIMULATION TEST")
    print("=" * 60)
    
    # Find test file
    test_file = Path(__file__).parent.parent.parent / "testdata/ftp/2025-11-29.txt"
    
    if not test_file.exists():
        print(f"❌ Test file not found: {test_file}")
        return False
    
    print(f"✅ Test file found: {test_file}")
    print(f"   Size: {test_file.stat().st_size:,} bytes")
    
    # Count lines
    with open(test_file, 'r', encoding='utf-8', errors='ignore') as f:
        total_lines = sum(1 for _ in f)
    print(f"   Lines: {total_lines:,}")
    
    # Start simulation
    print("\n📡 Starting simulation...")
    success = ftp_service.start_simulation(test_file, lines_per_tick=100)
    
    if not success:
        print("❌ Failed to start simulation")
        return False
    
    print("✅ Simulation started")
    print(f"   Mode: {'SIMULATION' if ftp_service.is_simulation else 'NORMAL'}")
    print(f"   Connected: {ftp_service.is_connected}")
    
    # Start poller
    print("\n🔄 Starting poller...")
    if not ftp_poller.is_running:
        await ftp_poller.start()
        print("✅ Poller started")
    else:
        print("⚠️  Poller already running")
    
    # Manual poll test
    print("\n🧪 Testing manual poll...")
    events = await ftp_service.poll_simulation(lines_per_tick=1000)
    print(f"   Found {len(events)} events in first 1000 lines")
    
    if events:
        print(f"   First event: {events[0].time} - Hanger {events[0].hanger}")
        for i, event in enumerate(events[:5]):
            print(f"   Event {i+1}: {event.time} - Hanger {event.hanger}")
    
    # Check progress
    current, total = ftp_service.simulation_progress
    print(f"   Progress: {current}/{total} lines ({100*current//total if total > 0 else 0}%)")
    
    # Run poller for a few cycles
    print("\n⏱️  Running poller for 10 seconds...")
    event_count = 0
    last_current = 0
    
    for i in range(20):  # 20 cycles * 0.5s = 10 seconds
        await asyncio.sleep(0.5)
        current, total = ftp_service.simulation_progress
        progress = 100 * current // total if total > 0 else 0
        
        # Check if progress is being made
        lines_processed = current - last_current
        last_current = current
        
        if i % 2 == 0:  # Print every second
            print(f"   Cycle {i+1}: {current:,}/{total:,} lines ({progress}%) [+{lines_processed} lines/cycle]")
        
        if current >= total:
            print("   ✅ Reached end of file")
            break
    
    # Stop
    print("\n🛑 Stopping...")
    await ftp_poller.stop()
    ftp_service.stop_simulation()
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    try:
        result = asyncio.run(test_simulation())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
