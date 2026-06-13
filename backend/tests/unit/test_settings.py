import pytest
from pathlib import Path
from unittest.mock import patch, mock_open

from app.core.config import settings
from app.services.opcua_service import opcua_service
from app.services.excel_service import excel_service


def test_update_simulation_mode_in_env():
    """Test that update_simulation_mode_in_env writes the correct value to .env file"""
    mock_data = "SIMULATION_ENABLED=true\nOTHER_VAR=123"
    
    with patch("builtins.open", mock_open(read_data=mock_data)) as mock_file, \
         patch.object(Path, "exists", return_value=True):
        
        settings.update_simulation_mode_in_env(False)
        
        # Verify it was opened twice: once for reading, once for writing
        assert mock_file.call_count == 2
        
        # Verify it attempted to write SIMULATION_ENABLED=false
        # The mock_file handles writelines, let's extract what was written
        writelines_calls = mock_file.mock_calls
        # Find writelines call arguments
        written_content = []
        for call in writelines_calls:
            if call[0] == '().writelines':
                written_content.extend(call[1][0])
                
        combined_write = "".join(written_content)
        assert "SIMULATION_ENABLED=false\n" in combined_write


@pytest.mark.asyncio
async def test_opcua_service_update_simulation_mode():
    """Test that opcua_service.update_simulation_mode updates endpoints correctly"""
    # Verify method exists and changes URL depending on mode
    with patch.object(opcua_service, "start") as mock_start, \
         patch.object(opcua_service, "stop") as mock_stop:
         
        # Test simulation mode enabled
        await opcua_service.update_simulation_mode(True)
        assert opcua_service._url == settings.OPCUA_SIM_ENDPOINT
        assert opcua_service._poll_interval == settings.OPCUA_SIM_POLL_INTERVAL
        
        # Test simulation mode disabled
        await opcua_service.update_simulation_mode(False)
        assert opcua_service._url == settings.OPCUA_ENDPOINT
        assert opcua_service._poll_interval == settings.OPCUA_POLL_INTERVAL


def test_excel_service_update_simulation_mode():
    """Test that excel_service.update_simulation_mode invalidates caches and updates path"""
    with patch.object(excel_service, "_load_persisted_active_file", return_value="test.xlsm") as mock_load:
        excel_service.update_simulation_mode()
        assert excel_service._active_file_name == "test.xlsm"
        assert excel_service._cache is None
        assert excel_service._cache_mtime is None
        assert excel_service._cache_path is None
