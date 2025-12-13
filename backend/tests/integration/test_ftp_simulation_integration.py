"""
Integration test for FTP simulation.
Tests the full simulation flow including poller and event broadcasting.
"""
import pytest
import asyncio
from pathlib import Path

from app.services.ftp_service import ftp_service
from app.services.ftp_poller import ftp_poller


@pytest.fixture
def test_log_file():
    """Get path to test log file."""
    # Try multiple paths
    possible_paths = [
        Path(__file__).parent.parent.parent.parent / "testdata/ftp/2025-11-29.txt",
        Path("/app/testdata/ftp/2025-11-29.txt"),
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    
    pytest.skip("Test log file not found")


@pytest.mark.asyncio
async def test_simulation_full_cycle(test_log_file):
    """
    Test complete simulation cycle.
    
    Verifies:
    - Simulation starts successfully
    - Poller processes events
    - Progress is tracked correctly
    - Events are parsed from log
    """
    # Start simulation
    success = ftp_service.start_simulation(test_log_file)
    assert success, "Simulation should start successfully"
    assert ftp_service.is_simulation, "Should be in simulation mode"
    assert ftp_service.is_connected, "Should report as connected"
    
    # Start poller
    if not ftp_poller.is_running:
        await ftp_poller.start()
    
    try:
        # Wait for some processing
        await asyncio.sleep(2.0)
        
        # Check progress
        current, total = ftp_service.simulation_progress
        assert current > 0, "Should have processed some lines"
        assert total > 0, "Should have total lines count"
        assert current <= total, "Current should not exceed total"
        
        # Manually poll and check for events
        events = await ftp_service.poll_simulation(lines_per_tick=1000)
        
        # We know there's at least one event in first 1000 lines (line 990)
        # But we may have already passed it, so just check structure
        if events:
            event = events[0]
            assert event.time is not None
            assert event.hanger > 0
            assert event.date is not None
    
    finally:
        # Cleanup
        await ftp_poller.stop()
        ftp_service.stop_simulation()


@pytest.mark.asyncio
async def test_simulation_event_parsing(test_log_file):
    """
    Test that simulation correctly parses CJ2M log format.
    
    Verifies:
    - Events are extracted from log lines
    - Time, hanger, and date are parsed correctly
    """
    # Start simulation
    success = ftp_service.start_simulation(test_log_file)
    assert success
    
    try:
        # Process first 1000 lines (we know event is at line 990)
        events = await ftp_service.poll_simulation(lines_per_tick=1000)
        
        # Should find at least one event
        assert len(events) >= 1, "Should find at least one event in first 1000 lines"
        
        # Check first event structure
        event = events[0]
        assert event.time.count(':') == 2, "Time should be HH:MM:SS format"
        assert 1 <= event.hanger <= 99, "Hanger should be valid number"
        assert event.date is not None, "Date should be set"
        
        # Date should match filename (2025-11-29 -> 29.11.2025)
        assert event.date == "29.11.2025", f"Date should be 29.11.2025, got {event.date}"
    
    finally:
        ftp_service.stop_simulation()


@pytest.mark.asyncio
async def test_simulation_progress_tracking(test_log_file):
    """
    Test that simulation tracks progress correctly.
    
    Verifies:
    - Progress starts at 0
    - Progress increases with each poll
    - Progress doesn't exceed total
    """
    success = ftp_service.start_simulation(test_log_file)
    assert success
    
    try:
        # Initial progress
        current, total = ftp_service.simulation_progress
        assert current == 0, "Should start at line 0"
        assert total > 0, "Should have total lines"
        
        initial_total = total
        
        # Poll once
        await ftp_service.poll_simulation(lines_per_tick=100)
        current, total = ftp_service.simulation_progress
        assert current == 100, "Should have processed 100 lines"
        assert total == initial_total, "Total should not change"
        
        # Poll again
        await ftp_service.poll_simulation(lines_per_tick=200)
        current, total = ftp_service.simulation_progress
        assert current == 300, "Should have processed 300 lines total"
    
    finally:
        ftp_service.stop_simulation()


@pytest.mark.asyncio
async def test_simulation_stop_and_restart(test_log_file):
    """
    Test that simulation can be stopped and restarted.
    
    Verifies:
    - Stop clears simulation state
    - Restart begins from line 0
    """
    # Start
    success = ftp_service.start_simulation(test_log_file)
    assert success
    
    # Process some lines
    await ftp_service.poll_simulation(lines_per_tick=500)
    current, _ = ftp_service.simulation_progress
    assert current == 500
    
    # Stop
    ftp_service.stop_simulation()
    assert not ftp_service.is_simulation
    
    # Restart
    success = ftp_service.start_simulation(test_log_file)
    assert success
    
    # Should start from beginning
    current, _ = ftp_service.simulation_progress
    assert current == 0, "Should restart from line 0"
    
    # Cleanup
    ftp_service.stop_simulation()
