# Implementation Plan

- [x] 1. Set up project structure and core configuration



  - [x] 1.1 Create backend directory structure with FastAPI skeleton

    - Create `backend/` folder with `app/`, `alembic/`, `static/`, `tests/` subdirectories
    - Create `app/api/`, `app/core/`, `app/db/`, `app/schemas/`, `app/services/` folders
    - Initialize `__init__.py` files in all packages
    - _Requirements: 6.1, 6.2_

  - [x] 1.2 Create frontend directory structure with Vite + React + TypeScript

    - Initialize Vite project with React TypeScript template
    - Create `src/pages/`, `src/components/`, `src/hooks/`, `src/api/` folders
    - Configure Tailwind CSS
    - _Requirements: 7.1, 7.3_

  - [x] 1.3 Create Docker Compose configuration

    - Create `docker-compose.yml` with backend and frontend services
    - Configure volume mounts for database, Excel file, and images
    - Set up environment variables
    - _Requirements: 5.1, 5.4, 5.5_

  - [x] 1.4 Create environment configuration module
    - Create `app/core/config.py` with Pydantic Settings
    - Define all configuration variables with defaults
    - _Requirements: 5.3_
  - [ ] 1.5 Write property test for configuration loading
    - **Property 9: Configuration from Environment**
    - **Validates: Requirements 5.3**

- [x] 2. Implement database layer and models



  - [x] 2.1 Create SQLAlchemy base and async engine

    - Create `app/db/base.py` with async engine setup
    - Create `app/db/session.py` with async session factory
    - _Requirements: 6.2_

  - [x] 2.2 Create Profile model

    - Create `app/db/models.py` with Profile SQLAlchemy model
    - Define all fields: id, name, quantity_per_hanger, length, notes, photo_thumb, photo_full, usage_count, created_at, updated_at
    - _Requirements: 2.2, 9.5_

  - [x] 2.3 Set up Alembic migrations

    - Initialize Alembic with async support
    - Create initial migration for profiles table
    - _Requirements: 5.2_
  - [x] 2.4 Create Pydantic schemas


    - Create `app/schemas/profile.py` with ProfileBase, ProfileCreate, ProfileResponse
    - Create `app/schemas/dashboard.py` with HangerData, UnloadEvent
    - Create `app/schemas/websocket.py` with WebSocketMessage
    - _Requirements: 9.1, 9.2_
  - [ ] 2.5 Write property test for Pydantic serialization round-trip
    - **Property 17: Pydantic Serialization Round-Trip**
    - **Validates: Requirements 9.2**
  - [ ] 2.6 Write property test for validation rejection
    - **Property 16: Pydantic Validation Rejects Invalid Data**
    - **Validates: Requirements 9.1**

- [x] 3. Implement text normalization utilities


  - [x] 3.1 Create text normalization module


    - Create `app/core/text_utils.py` with normalize_text function
    - Implement Latin/Cyrillic character mapping
    - Implement transliterate_cyrillic function for filenames
    - _Requirements: 2.1, 9.4_
  - [x] 3.2 Write property test for normalization idempotence


    - **Property 1: Text Normalization Idempotence**
    - **Validates: Requirements 9.4**

  - [x] 3.3 Write property test for transliteration consistency
    - **Property 6: Filename Transliteration Consistency**
    - **Validates: Requirements 3.5**


- [x] 4. Checkpoint - Ensure all tests pass



  - Ensure all tests pass, ask the user if questions arise.



- [x] 5. Implement CatalogService





  - [x] 5.1 Create CatalogService class
    - Create `app/services/catalog_service.py`
    - Implement search_profiles with normalized text comparison
    - Implement get_profile, create_or_update_profile methods
    - Implement get_profiles_without_photos method
    - _Requirements: 2.1, 2.2, 2.5, 8.1_
  - [x] 5.2 Write property test for Latin/Cyrillic search equivalence


    - **Property 2: Latin/Cyrillic Search Equivalence**
    - **Validates: Requirements 2.1**

  - [x] 5.3 Write property test for search results fields
    - **Property 3: Search Results Contain Required Fields**
    - **Validates: Requirements 2.2**
  - [x] 5.4 Write property test for search priority ordering
    - **Property 4: Search Priority Ordering**
    - **Validates: Requirements 2.5**
  - [x] 5.5 Write property test for missing photos sorting


    - **Property 13: Missing Photos Sorted by Usage**
    - **Validates: Requirements 8.1**
  - [x] 5.6 Implement photo upload functionality


    - Implement upload_photo method with thumbnail generation
    - Use PIL for image processing
    - _Requirements: 3.1, 3.2, 3.3_

  - [x] 5.7 Write property test for photo upload creates both versions
    - **Property 5: Photo Upload Creates Both Versions**
    - **Validates: Requirements 3.1**
  - [x] 5.8 Implement fuzzy search for duplicates
    - Implement search_duplicates method with similarity scoring
    - _Requirements: 8.4_
  - [x] 5.9 Write property test for fuzzy search similarity
    - **Property 15: Fuzzy Search Similarity**
    - **Validates: Requirements 8.4**

- [x] 6. Implement ExcelService
  - [x] 6.1 Create ExcelService class
    - Create `app/services/excel_service.py`
    - Implement get_dataframe with caching
    - Implement cache invalidation
    - _Requirements: 6.3_
  - [x] 6.2 Implement Excel parsing logic
    - Port parse_profile_with_processing from legacy code
    - Port split_profiles function
    - Implement get_products with filters
    - _Requirements: 1.1_

  - [x] 6.3 Write property test for cache invalidation

    - **Property 10: Cache Invalidation on File Change**

    - **Validates: Requirements 6.3**
  - [x] 6.4 Implement recent profiles methods
    - Implement get_recent_profiles with limit
    - Implement get_recent_missing_profiles with pagination
    - _Requirements: 8.2, 8.3_
  - [x] 6.5 Write property test for recent records limit
    - **Property 14: Recent Records Limit**
    - **Validates: Requirements 8.2**

- [x] 7. Implement FTPService
  - [x] 7.1 Create FTPService class
    - Create `app/services/ftp_service.py`
    - Implement async FTP connection
    - Implement read_today_log method
    - _Requirements: 10.1, 10.2_
  - [x] 7.2 Implement FTP log parsing
    - Implement parse_unload_events with regex
    - Port parsing logic from legacy ftp_manager.py
    - _Requirements: 10.3_
  - [x] 7.3 Write property test for FTP log parsing
    - **Property 18: FTP Log Parsing Extracts Correct Data**
    - **Validates: Requirements 10.3**
  - [x] 7.4 Implement incremental polling
    - Implement poll_incremental with byte offset tracking
    - Implement date rollover handling
    - _Requirements: 10.5_
  - [x] 7.5 Write property test for date rollover handling
    - **Property 19: FTP Date Rollover Handling**
    - **Validates: Requirements 10.5**

- [x] 8. Checkpoint - Ensure all tests pass


  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement WebSocket infrastructure
  - [x] 9.1 Create WebSocketManager class
    - Create `app/services/websocket_manager.py`
    - Implement connect, disconnect, broadcast methods
    - Implement connection tracking
    - _Requirements: 6.5_
  - [x] 9.2 Write property test for broadcast to all clients
    - **Property 11: WebSocket Broadcast to All Clients**
    - **Validates: Requirements 6.5**
  - [x] 9.3 Create WebSocket endpoint
    - Create `app/api/websockets.py`
    - Implement /ws endpoint with connection handling
    - _Requirements: 1.2, 1.4_

- [x] 10. Implement background services
  - [x] 10.1 Create ExcelWatcher service
    - Create `app/services/excel_watcher.py`
    - Use watchdog for file monitoring
    - Integrate with WebSocketManager for broadcasts
    - _Requirements: 1.1_
  - [x] 10.2 Create FTPPoller service
    - Create `app/services/ftp_poller.py`
    - Implement async polling loop with 60s interval
    - Integrate with WebSocketManager for broadcasts
    - _Requirements: 1.3, 6.4_

- [x] 11. Implement API routes
  - [x] 11.1 Create dashboard routes


    - Create `app/api/routes/dashboard.py`
    - Implement GET /api/dashboard endpoint
    - _Requirements: 1.1, 1.2_

  - [x] 11.2 Create catalog routes

    - Create `app/api/routes/catalog.py`
    - Implement GET /api/catalog with search
    - Implement POST /api/catalog for photo upload
    - _Requirements: 2.1, 2.2, 3.1, 3.3_


  - [x] 11.3 Create analysis routes
    - Create `app/api/routes/analysis.py`
    - Implement GET /api/profiles/missing
    - Implement GET /api/profiles/search-duplicates
    - _Requirements: 8.1, 8.2, 8.3, 8.4_


  - [x] 11.4 Create signal route
    - Create `app/api/routes/signal.py`
    - Implement POST /api/signal for FTP events
    - _Requirements: 1.3_

- [x] 12. Create FastAPI main application
  - [x] 12.1 Create main.py with lifespan


    - Create `app/main.py`
    - Implement lifespan context manager
    - Start ExcelWatcher, FTPPoller as background tasks
    - Mount routers and static files
    - _Requirements: 6.1_

- [x] 13. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. Implement Telegram Bot
  - [x] 14.1 Create Telegram bot module
    - Create `app/services/telegram_bot.py`
    - Port handlers from legacy bot.py
    - Integrate with CatalogService
    - _Requirements: 4.1, 4.2, 4.3_
  - [x] 14.2 Write property test for multi-match limit
    - **Property 7: Telegram Bot Multi-Match Limit**
    - **Validates: Requirements 4.3**
  - [x] 14.3 Implement authentication
    - Implement password check and user persistence
    - _Requirements: 4.4, 4.5_
  - [x] 14.4 Write property test for authorization persistence

    - **Property 8: Authorization Persistence**
    - **Validates: Requirements 4.5**

- [x] 15. Implement Frontend - Core setup
  - [x] 15.1 Create API client
    - Create `src/api/client.ts` with Axios instance
    - Create `src/api/dashboard.ts`, `src/api/catalog.ts`, `src/api/analysis.ts`
    - _Requirements: 7.2_
  - [x] 15.2 Create useRealtimeData hook
    - Create `src/hooks/useRealtimeData.ts`
    - Implement WebSocket connection with auto-reconnect
    - _Requirements: 1.2, 1.4, 1.5, 7.5_
  - [x] 15.3 Create TanStack Query hooks
    - Create `src/hooks/useProfiles.ts`
    - Create `src/hooks/useDashboard.ts`
    - _Requirements: 7.2_

- [ ] 16. Implement Frontend - Components
  - [ ] 16.1 Create DataTable component
    - Create `src/components/DataTable.tsx`
    - Implement sorting and filtering
    - _Requirements: 7.4_
  - [ ] 16.2 Write property test for table sorting
    - **Property 12: Table Sorting Consistency**
    - **Validates: Requirements 7.4**
  - [ ] 16.3 Create ProfileCard component
    - Create `src/components/ProfileCard.tsx`
    - Display profile info with photo
    - _Requirements: 2.2, 2.3_
  - [ ] 16.4 Create PhotoUploader component
    - Create `src/components/PhotoUploader.tsx`
    - Implement drag-drop and crop functionality
    - _Requirements: 3.1, 3.2_
  - [ ] 16.5 Create ConnectionStatus component
    - Create `src/components/ConnectionStatus.tsx`
    - Display WebSocket connection state
    - _Requirements: 1.4_

- [x] 17. Implement Frontend - Pages
  - [x] 17.1 Create Dashboard page
    - Create `src/pages/Dashboard.tsx`
    - Integrate DataTable with real-time updates
    - Display FTP status indicator
    - _Requirements: 1.1, 1.2, 10.1, 10.4_
  - [x] 17.2 Create Catalog page
    - Create `src/pages/Catalog.tsx`
    - Implement search with ProfileCard grid
    - _Requirements: 2.1, 2.2, 2.4_
  - [x] 17.3 Create Analysis page
    - Create `src/pages/Analysis.tsx`
    - Implement mode switching (Recent, Recent Missing)
    - Implement duplicate search
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
  - [x] 17.4 Create App routing
    - Create `src/App.tsx` with React Router
    - Set up navigation between pages
    - _Requirements: 7.1_

- [x] 18. Create Docker configuration
  - [x] 18.1 Create Backend Dockerfile
    - Create `backend/Dockerfile`
    - Configure Python environment and dependencies
    - _Requirements: 5.1_
  - [x] 18.2 Create Frontend Dockerfile
    - Create `frontend/Dockerfile`
    - Configure multi-stage build with Nginx
    - _Requirements: 5.1_
  - [x] 18.3 Create docker-compose.yml
    - Define backend and frontend services
    - Configure volumes and environment
    - _Requirements: 5.1, 5.4, 5.5_

- [x] 19. Final Checkpoint - Ensure all tests pass
  - All 84 backend tests passing
  - Frontend TypeScript compiles without errors
  - Docker configuration complete
