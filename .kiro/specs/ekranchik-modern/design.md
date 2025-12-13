# Design Document: Ekranchik Modern

## Overview

Ekranchik Modern — это полный рефакторинг системы мониторинга производственных процессов завода КТМ-2000. Система переходит с монолитной Flask-архитектуры на современный стек с разделением на Backend (FastAPI) и Frontend (React), объединённых через Docker Compose.

### Ключевые изменения:
- **Backend**: Flask → FastAPI с async/await
- **Frontend**: jQuery + HTML templates → React + TypeScript + Tailwind
- **Real-time**: Socket.IO → Native WebSockets
- **Database**: Raw SQLite → SQLAlchemy 2.0 + Alembic
- **Bot**: Aiogram 3.x (сохраняется)
- **DevOps**: Docker Compose для оркестрации

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Compose                            │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    Frontend Container                    │    │
│  │  ┌─────────────────────────────────────────────────┐    │    │
│  │  │  React App (Vite + TypeScript)                  │    │    │
│  │  │  - Dashboard Page                               │    │    │
│  │  │  - Catalog Page                                 │    │    │
│  │  │  - Analysis Page                                │    │    │
│  │  │  - useRealtimeData Hook (WebSocket)             │    │    │
│  │  └─────────────────────────────────────────────────┘    │    │
│  │  Nginx (Production) / Vite Dev Server                   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    Backend Container                     │    │
│  │  ┌─────────────────────────────────────────────────┐    │    │
│  │  │  FastAPI Application                            │    │    │
│  │  │  ├── REST API Routes                            │    │    │
│  │  │  ├── WebSocket Endpoints                        │    │    │
│  │  │  └── Static Files Server                        │    │    │
│  │  └─────────────────────────────────────────────────┘    │    │
│  │  ┌─────────────────────────────────────────────────┐    │    │
│  │  │  Background Services (asyncio tasks)            │    │    │
│  │  │  ├── ExcelWatcher (watchdog)                    │    │    │
│  │  │  ├── FTPPoller (60s interval)                   │    │    │
│  │  │  └── TelegramBot (aiogram polling)              │    │    │
│  │  └─────────────────────────────────────────────────┘    │    │
│  │  ┌─────────────────────────────────────────────────┐    │    │
│  │  │  Services Layer                                 │    │    │
│  │  │  ├── ExcelService                               │    │    │
│  │  │  ├── FTPService                                 │    │    │
│  │  │  ├── CatalogService                             │    │    │
│  │  │  └── WebSocketManager                           │    │    │
│  │  └─────────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│  ┌───────────────────────────┼───────────────────────────┐      │
│  │         Volumes           │                           │      │
│  │  ┌──────────┐  ┌──────────┴──────┐  ┌──────────────┐ │      │
│  │  │ SQLite   │  │ Excel File      │  │ Static Images│ │      │
│  │  │ Database │  │ (.xlsm)         │  │ (photos)     │ │      │
│  │  └──────────┘  └─────────────────┘  └──────────────┘ │      │
│  └───────────────────────────────────────────────────────┘      │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    External Systems                      │    │
│  │  ┌──────────────┐  ┌──────────────┐                     │    │
│  │  │ FTP Server   │  │ Telegram API │                     │    │
│  │  │ (Omron PLC)  │  │              │                     │    │
│  │  └──────────────┘  └──────────────┘                     │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### Backend Components

#### 1. FastAPI Application (`app/main.py`)
- Точка входа приложения
- Lifespan context manager для запуска/остановки фоновых задач
- Монтирование роутеров и статических файлов

#### 2. API Routes (`app/api/routes/`)
- `dashboard.py`: GET /api/dashboard — данные для главной таблицы
- `catalog.py`: GET/POST /api/catalog — CRUD для профилей
- `analysis.py`: GET /api/profiles/missing — профили без фото
- `signal.py`: POST /api/signal — приём сигналов от FTP

#### 3. WebSocket Handler (`app/api/websockets.py`)
- `/ws` endpoint для real-time обновлений
- WebSocketManager для управления подключениями
- Broadcast механизм для рассылки обновлений

#### 4. Services Layer (`app/services/`)

**ExcelService** (`excel_service.py`):
```python
class ExcelService:
    async def get_dataframe(full_dataset: bool = False) -> pd.DataFrame
    async def get_products(limit: int, days: int, filters: dict) -> dict
    async def parse_profile_with_processing(text: str) -> dict
    def invalidate_cache() -> None
```

**FTPService** (`ftp_service.py`):
```python
class FTPService:
    async def connect() -> FTP | None
    async def read_today_log() -> str
    async def parse_unload_events(content: str) -> list[UnloadEvent]
    async def poll_incremental() -> list[UnloadEvent]
```

**CatalogService** (`catalog_service.py`):
```python
class CatalogService:
    async def search_profiles(query: str) -> list[Profile]
    async def get_profile(name: str) -> Profile | None
    async def create_or_update_profile(data: ProfileCreate) -> Profile
    async def upload_photo(profile_name: str, file: UploadFile) -> str
    async def get_profiles_without_photos() -> list[Profile]
```

**WebSocketManager** (`websocket_manager.py`):
```python
class WebSocketManager:
    async def connect(websocket: WebSocket) -> None
    async def disconnect(websocket: WebSocket) -> None
    async def broadcast(message: dict) -> None
    async def send_personal(websocket: WebSocket, message: dict) -> None
```

#### 5. Background Tasks (`app/services/`)

**ExcelWatcher** (`excel_watcher.py`):
```python
class ExcelWatcher:
    def __init__(self, excel_path: Path, on_change: Callable)
    async def start() -> None
    async def stop() -> None
```

**FTPPoller** (`ftp_poller.py`):
```python
class FTPPoller:
    def __init__(self, interval: int = 60)
    async def start() -> None
    async def stop() -> None
    async def poll_once() -> list[UnloadEvent]
```

#### 6. Database Layer (`app/db/`)
- `base.py`: SQLAlchemy Base и engine
- `models.py`: ORM модели
- `session.py`: Async session factory

#### 7. Telegram Bot (`app/services/telegram_bot.py`)
- Aiogram 3.x dispatcher
- Handlers для команд и сообщений
- Интеграция с CatalogService

### Frontend Components

#### 1. Pages (`src/pages/`)
- `Dashboard.tsx`: Главная страница с таблицей подвесов
- `Catalog.tsx`: Справочник профилей
- `Analysis.tsx`: Анализ профилей без фото

#### 2. Components (`src/components/`)
- `DataTable.tsx`: Универсальная таблица с сортировкой
- `ProfileCard.tsx`: Карточка профиля
- `PhotoUploader.tsx`: Загрузчик фото с кропом
- `ConnectionStatus.tsx`: Индикатор WebSocket соединения
- `SearchInput.tsx`: Поле поиска с debounce

#### 3. Hooks (`src/hooks/`)
- `useRealtimeData.ts`: WebSocket подключение и обновления
- `useProfiles.ts`: TanStack Query для профилей
- `useDashboard.ts`: TanStack Query для dashboard данных

#### 4. API Client (`src/api/`)
- `client.ts`: Axios instance с базовой конфигурацией
- `dashboard.ts`: API методы для dashboard
- `catalog.ts`: API методы для каталога
- `analysis.ts`: API методы для анализа

## Data Models

### Database Models (SQLAlchemy)

```python
class Profile(Base):
    __tablename__ = "profiles"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    quantity_per_hanger: Mapped[int | None]
    length: Mapped[float | None]
    notes: Mapped[str | None] = mapped_column(Text)
    photo_thumb: Mapped[str | None] = mapped_column(String(500))
    photo_full: Mapped[str | None] = mapped_column(String(500))
    usage_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
```

### Pydantic Schemas

```python
class ProfileBase(BaseModel):
    name: str
    quantity_per_hanger: int | None = None
    length: float | None = None
    notes: str | None = None

class ProfileCreate(ProfileBase):
    pass

class ProfileResponse(ProfileBase):
    id: int
    photo_thumb: str | None = None
    photo_full: str | None = None
    usage_count: int = 0
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class HangerData(BaseModel):
    number: str
    date: str
    time: str
    client: str
    profile: str
    profiles_info: list[ProfileInfo]
    color: str
    lamels_qty: int | str
    kpz_number: str
    material_type: str

class UnloadEvent(BaseModel):
    time: str
    hanger: int
    timestamp: datetime

class WebSocketMessage(BaseModel):
    type: Literal["data_update", "unload_event", "status"]
    payload: dict
```

### TypeScript Types

```typescript
interface Profile {
  id: number;
  name: string;
  quantity_per_hanger: number | null;
  length: number | null;
  notes: string | null;
  photo_thumb: string | null;
  photo_full: string | null;
  usage_count: number;
  created_at: string;
  updated_at: string;
}

interface HangerData {
  number: string;
  date: string;
  time: string;
  client: string;
  profile: string;
  profiles_info: ProfileInfo[];
  color: string;
  lamels_qty: number | string;
  kpz_number: string;
  material_type: string;
}

interface WebSocketMessage {
  type: 'data_update' | 'unload_event' | 'status';
  payload: Record<string, unknown>;
}
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

Based on the prework analysis, the following properties have been identified after eliminating redundancy:

### Property 1: Text Normalization Idempotence
*For any* text string, applying the normalize_text function twice should produce the same result as applying it once: `normalize(normalize(x)) == normalize(x)`
**Validates: Requirements 9.4**

### Property 2: Latin/Cyrillic Search Equivalence
*For any* Profile in the database and any search query, searching with the Latin equivalent of a Cyrillic query (or vice versa) should return the same Profile results
**Validates: Requirements 2.1**

### Property 3: Search Results Contain Required Fields
*For any* search query that returns results, each Profile in the results should contain all required fields: name, quantity_per_hanger, length, notes, photo_thumb, photo_full
**Validates: Requirements 2.2**

### Property 4: Search Priority Ordering
*For any* search query, Profiles matching by name should appear before Profiles matching only by notes, and notes matches should appear before quantity/length matches
**Validates: Requirements 2.5**

### Property 5: Photo Upload Creates Both Versions
*For any* valid image upload, the system should create both a thumbnail and a full-size version, and both file paths should be stored in the Profile record
**Validates: Requirements 3.1**

### Property 6: Filename Transliteration Consistency
*For any* Cyrillic Profile name, the transliterated filename should contain only ASCII characters and the transliteration should be reversible (one-to-one mapping)
**Validates: Requirements 3.5**

### Property 7: Telegram Bot Multi-Match Limit
*For any* search query that matches more than 5 Profiles, the Telegram Bot should display exactly 5 inline buttons (not more)
**Validates: Requirements 4.3**

### Property 8: Authorization Persistence
*For any* user who successfully authenticates with the correct password, subsequent requests from that user should not require re-authentication
**Validates: Requirements 4.5**

### Property 9: Configuration from Environment
*For any* configuration setting, the system should read the value from environment variables, and missing required variables should cause startup failure with clear error message
**Validates: Requirements 5.3**

### Property 10: Cache Invalidation on File Change
*For any* Excel file modification, the cached DataFrame should be invalidated and the next read should return fresh data reflecting the modification
**Validates: Requirements 6.3**

### Property 11: WebSocket Broadcast to All Clients
*For any* broadcast message, all currently connected WebSocket clients should receive the same message content
**Validates: Requirements 6.5**

### Property 12: Table Sorting Consistency
*For any* table data and sort column, sorting in ascending order and then descending order should produce reversed results (excluding equal values)
**Validates: Requirements 7.4**

### Property 13: Missing Photos Sorted by Usage
*For any* list of Profiles without photos, the list should be sorted by usage_count in descending order
**Validates: Requirements 8.1**

### Property 14: Recent Records Limit
*For any* request for recent records, the system should return at most 50 records, ordered by recency (most recent first)
**Validates: Requirements 8.2**

### Property 15: Fuzzy Search Similarity
*For any* fuzzy search query, returned Profiles should have a similarity score above a threshold, and results should be ordered by similarity (highest first)
**Validates: Requirements 8.4**

### Property 16: Pydantic Validation Rejects Invalid Data
*For any* API request with invalid data (missing required fields, wrong types), the system should return a 422 validation error with field-specific messages
**Validates: Requirements 9.1**

### Property 17: Pydantic Serialization Round-Trip
*For any* Profile object, serializing to JSON and deserializing back should produce an equivalent object
**Validates: Requirements 9.2**

### Property 18: FTP Log Parsing Extracts Correct Data
*For any* valid FTP log entry containing an unload event, parsing should extract the correct hanger number and timestamp
**Validates: Requirements 10.3**

### Property 19: FTP Date Rollover Handling
*For any* date change, the FTP_Poller should reset its byte offset and start reading from the new date's file
**Validates: Requirements 10.5**

## Error Handling

### Backend Error Handling

1. **API Errors**: Return structured JSON responses with error codes
```python
class APIError(Exception):
    def __init__(self, status_code: int, detail: str, error_code: str):
        self.status_code = status_code
        self.detail = detail
        self.error_code = error_code

@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.detail, "code": exc.error_code}
    )
```

2. **Database Errors**: Wrap in try/except, log, return 500
3. **FTP Errors**: Log and continue, update status indicator
4. **Excel Errors**: Log and return cached data if available
5. **WebSocket Errors**: Graceful disconnect, client reconnection

### Frontend Error Handling

1. **API Errors**: Display toast notifications
2. **WebSocket Disconnect**: Show status indicator, auto-reconnect
3. **Validation Errors**: Inline form field errors
4. **Network Errors**: Retry with exponential backoff

## Testing Strategy

### Property-Based Testing Library
- **Python**: `hypothesis` for property-based tests
- **TypeScript**: `fast-check` for frontend property tests

### Unit Tests
- Test individual service methods
- Test Pydantic schema validation
- Test text normalization functions
- Test FTP log parsing regex

### Property-Based Tests
Each correctness property will be implemented as a property-based test:
- Generate random inputs using hypothesis strategies
- Verify the property holds for all generated inputs
- Minimum 100 iterations per property test

### Integration Tests
- Test API endpoints with test database
- Test WebSocket connections
- Test file upload flow

### Test File Structure
```
backend/
  tests/
    unit/
      test_text_normalization.py
      test_ftp_parsing.py
      test_pydantic_schemas.py
    property/
      test_search_properties.py
      test_normalization_properties.py
      test_serialization_properties.py
    integration/
      test_api_endpoints.py
      test_websocket.py

frontend/
  src/
    __tests__/
      hooks/
        useRealtimeData.test.ts
      components/
        DataTable.test.tsx
      property/
        sorting.property.test.ts
```
