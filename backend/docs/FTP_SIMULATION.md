# FTP Simulation Mode

## Overview

FTP Simulation mode allows testing the system without connecting to a real Omron PLC. It reads a local log file and simulates real-time FTP polling by processing the file line-by-line.

## Features

- ✅ Reads local log files (CJ2M format)
- ✅ Simulates real-time event streaming
- ✅ Broadcasts events via WebSocket
- ✅ Tracks progress (current line / total lines)
- ✅ Configurable processing speed
- ✅ Can be started/stopped via API

## API Endpoints

### Start Simulation

```http
POST /api/dashboard/simulation/start
Content-Type: application/json

{
  "file_path": "/path/to/log.txt"  // Optional, uses default if omitted
}
```

**Response:**
```json
{
  "active": true,
  "file_path": "/app/testdata/ftp/2025-11-29.txt",
  "current_line": 0,
  "total_lines": 152954,
  "progress_percent": 0
}
```

### Stop Simulation

```http
POST /api/dashboard/simulation/stop
```

### Get Status

```http
GET /api/dashboard/simulation/status
```

## Log Format

The simulation expects CJ2M log format:

```
HH:MM:SS.mmm L# Команда от CJ2M: Разгрузка подвеса - N в поз. 34.
```

Example:
```
00:07:20.145 L# Команда от CJ2M: Разгрузка подвеса - 16 в поз. 34.
```

## Configuration

### Processing Speed

Default: **425 lines per 0.5 seconds** (~850 lines/sec)

For a 150k line file, this takes approximately **3 minutes**.

To adjust speed, modify `lines_per_tick` in `ftp_poller.py`:

```python
events = await ftp_service.poll_simulation(lines_per_tick=425)
```

### Poll Interval

Simulation uses **0.5 second** polling interval (vs 5 seconds for real FTP).

Configured in `ftp_poller.py`:

```python
interval = 0.5 if ftp_service.is_simulation else self._poll_interval
```

## Testing

### Manual Test Script

Run the test script to verify simulation:

```bash
cd backend
python scripts/test_ftp_simulation.py
```

Expected output:
```
============================================================
FTP SIMULATION TEST
============================================================
✅ Test file found: D:\KTM\KTM2000\testdata\ftp\2025-11-29.txt
   Size: 7,727,785 bytes
   Lines: 152,954

📡 Starting simulation...
✅ Simulation started
   Mode: SIMULATION
   Connected: True

🔄 Starting poller...
✅ Poller started

🧪 Testing manual poll...
   Found 1 events in first 1000 lines
   First event: 00:07:20 - Hanger 16
```

### Automated Tests

Run property-based and integration tests:

```bash
# Property tests
pytest tests/property/test_ftp_properties.py -v

# Integration tests
pytest tests/integration/test_ftp_simulation_integration.py -v

# All FTP tests
pytest tests/property/test_ftp_properties.py tests/integration/test_ftp_simulation_integration.py -v
```

## Usage Example

### Python

```python
from pathlib import Path
from app.services.ftp_service import ftp_service
from app.services.ftp_poller import ftp_poller

# Start simulation
log_file = Path("testdata/ftp/2025-11-29.txt")
success = ftp_service.start_simulation(log_file)

# Start poller
await ftp_poller.start()

# Check progress
current, total = ftp_service.simulation_progress
print(f"Progress: {current}/{total} lines")

# Stop
await ftp_poller.stop()
ftp_service.stop_simulation()
```

### cURL

```bash
# Start simulation
curl -X POST http://localhost:8000/api/dashboard/simulation/start \
  -H "Content-Type: application/json"

# Check status
curl http://localhost:8000/api/dashboard/simulation/status

# Stop simulation
curl -X POST http://localhost:8000/api/dashboard/simulation/stop
```

## Troubleshooting

### No events found

**Problem:** Simulation runs but no events are detected.

**Solution:** Check that log file uses correct format. The regex pattern expects:
```
HH:MM:SS.mmm L# Команда от CJ2M: Разгрузка подвеса - N в поз. 34.
```

### Simulation too slow/fast

**Problem:** Processing speed doesn't match requirements.

**Solution:** Adjust `lines_per_tick` parameter:
- Faster: Increase value (e.g., 1000)
- Slower: Decrease value (e.g., 100)

### File not found

**Problem:** `Simulation file not found` error.

**Solution:** Check file paths in `dashboard.py`:
```python
possible_paths = [
    Path("/app/testdata/ftp/2025-11-29.txt"),  # Docker
    Path(__file__).parent.parent.parent.parent.parent / "testdata/ftp/2025-11-29.txt",  # Local
]
```

## Architecture

```
┌─────────────────┐
│  API Endpoint   │
│  /simulation/*  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  FTP Service    │
│  - Load file    │
│  - Parse events │
│  - Track progress│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  FTP Poller     │
│  - Poll loop    │
│  - 0.5s interval│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ WebSocket Mgr   │
│ - Broadcast     │
│ - Clients       │
└─────────────────┘
```

## Performance

- **File size:** 7.7 MB (152,954 lines)
- **Processing speed:** ~850 lines/sec
- **Total time:** ~3 minutes
- **Memory usage:** ~8 MB (file loaded into memory)
- **Events found:** ~1,500 unload events

## Date Handling

Simulation extracts date from filename:
- Filename: `2025-11-29.txt`
- Parsed date: `29.11.2025`

This date is attached to all parsed events.
