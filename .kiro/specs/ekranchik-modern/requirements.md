# Requirements Document

## Introduction

Ekranchik — система мониторинга производственных процессов завода КТМ-2000. Текущая реализация представляет собой монолитное Flask-приложение с jQuery-фронтендом, которое отслеживает Excel-файл (.xlsm) с данными о подвесах, мониторит FTP-логи от ПЛК Omron для отслеживания событий разгрузки, и управляет справочником профилей с фотографиями. Система также включает Telegram-бота для поиска профилей.

Цель рефакторинга — переход на современный стек (FastAPI + React + Docker) для улучшения масштабируемости, поддерживаемости и производительности системы.

## Glossary

- **Ekranchik_System**: Система мониторинга производственных процессов, состоящая из Backend API, Frontend UI, Telegram Bot и фоновых сервисов
- **Profile**: Запись в справочнике профилей, содержащая название, количество на подвес, длину, примечания и фотографии
- **Hanger**: Подвес — производственная единица, отслеживаемая в Excel-файле и FTP-логах
- **Unload_Event**: Событие разгрузки подвеса, фиксируемое в FTP-логах ПЛК Omron
- **Excel_Watcher**: Сервис мониторинга изменений Excel-файла с данными о подвесах
- **FTP_Poller**: Сервис опроса FTP-сервера для получения событий разгрузки
- **WebSocket_Connection**: Двунаправленное соединение для real-time обновлений между Backend и Frontend
- **Dashboard**: Главная страница с таблицей данных о подвесах и статусами
- **Catalog**: Страница справочника профилей с фотографиями
- **Processing**: Дополнительная обработка профиля (окно, греб, сверло)

## Requirements

### Requirement 1

**User Story:** As a производственный оператор, I want to view real-time data about hangers on the dashboard, so that I can monitor production status without page refresh.

#### Acceptance Criteria

1. WHEN the Excel_Watcher detects a file modification THEN the Ekranchik_System SHALL parse the updated data and broadcast it via WebSocket_Connection within 5 seconds
2. WHEN a WebSocket_Connection receives updated data THEN the Dashboard SHALL render the new information without full page reload
3. WHEN the FTP_Poller detects an Unload_Event THEN the Ekranchik_System SHALL update the corresponding Hanger status and notify connected clients via WebSocket_Connection
4. WHILE the Dashboard is displayed THEN the Ekranchik_System SHALL show a connection status indicator reflecting the WebSocket_Connection state
5. IF the WebSocket_Connection is lost THEN the Ekranchik_System SHALL attempt automatic reconnection with exponential backoff

### Requirement 2

**User Story:** As a производственный оператор, I want to search and view profile information with photos, so that I can quickly identify profile specifications.

#### Acceptance Criteria

1. WHEN a user enters a search query in the Catalog THEN the Ekranchik_System SHALL return matching Profile records using normalized text comparison (Latin/Cyrillic equivalence)
2. WHEN displaying search results THEN the Ekranchik_System SHALL show Profile name, quantity per hanger, length, notes, and photo thumbnail
3. WHEN a user clicks on a Profile photo thumbnail THEN the Ekranchik_System SHALL display the full-size photo in a modal view
4. WHEN a Profile has no photo THEN the Ekranchik_System SHALL display a placeholder indicator and provide an upload option
5. WHEN searching for a Profile THEN the Ekranchik_System SHALL match against name, notes, quantity, and length fields with priority ordering

### Requirement 3

**User Story:** As a производственный оператор, I want to upload and manage profile photos, so that I can maintain an up-to-date visual reference.

#### Acceptance Criteria

1. WHEN a user uploads a photo for a Profile THEN the Ekranchik_System SHALL generate both thumbnail and full-size versions
2. WHEN a user crops an uploaded image THEN the Ekranchik_System SHALL apply the crop coordinates and save the result
3. WHEN a photo is successfully uploaded THEN the Ekranchik_System SHALL update the Profile record and refresh the display
4. IF an uploaded file exceeds 10MB THEN the Ekranchik_System SHALL reject the upload and display an error message
5. WHEN storing photos THEN the Ekranchik_System SHALL use transliterated filenames for Cyrillic Profile names

### Requirement 4

**User Story:** As a пользователь Telegram, I want to search for profiles via bot, so that I can access profile information from mobile device.

#### Acceptance Criteria

1. WHEN a user sends a profile name to the Telegram Bot THEN the Ekranchik_System SHALL search the Profile database and return matching results
2. WHEN exactly one Profile matches the search THEN the Telegram Bot SHALL display the Profile details with photo
3. WHEN multiple Profiles match the search THEN the Telegram Bot SHALL display a list of up to 5 options as inline buttons
4. WHEN a user is not authenticated THEN the Telegram Bot SHALL request password before allowing searches
5. WHEN a user enters the correct password THEN the Telegram Bot SHALL persist the authorization and provide access to search functionality

### Requirement 5

**User Story:** As a системный администратор, I want to deploy the system using Docker, so that I can easily manage and scale the application.

#### Acceptance Criteria

1. WHEN running docker-compose up THEN the Ekranchik_System SHALL start Backend, Frontend, and all background services
2. WHEN the Backend container starts THEN the Ekranchik_System SHALL run database migrations automatically
3. WHEN configuring the system THEN the Ekranchik_System SHALL read all settings from environment variables
4. WHEN the Excel file path is mounted as a volume THEN the Excel_Watcher SHALL monitor the mounted file for changes
5. WHEN the static images directory is mounted as a volume THEN the Ekranchik_System SHALL persist uploaded photos across container restarts

### Requirement 6

**User Story:** As a разработчик, I want the backend to use FastAPI with async architecture, so that I can handle concurrent requests efficiently.

#### Acceptance Criteria

1. WHEN the Backend starts THEN the Ekranchik_System SHALL initialize Excel_Watcher, FTP_Poller, and Telegram Bot as concurrent async tasks
2. WHEN handling API requests THEN the Ekranchik_System SHALL use async database operations via SQLAlchemy 2.0
3. WHEN parsing Excel files THEN the Ekranchik_System SHALL cache the parsed data and invalidate cache on file modification
4. WHEN the FTP_Poller runs THEN the Ekranchik_System SHALL poll the FTP server every 60 seconds without blocking other operations
5. WHEN multiple clients connect via WebSocket THEN the Ekranchik_System SHALL broadcast updates to all connected clients simultaneously

### Requirement 7

**User Story:** As a разработчик, I want the frontend to use React with TypeScript, so that I can build a maintainable and type-safe UI.

#### Acceptance Criteria

1. WHEN building the Frontend THEN the Ekranchik_System SHALL use Vite as the build tool with TypeScript configuration
2. WHEN fetching data THEN the Frontend SHALL use TanStack Query for state management and caching
3. WHEN styling components THEN the Frontend SHALL use Tailwind CSS for consistent design
4. WHEN displaying tables THEN the Frontend SHALL use accessible UI components with sorting and filtering capabilities
5. WHEN handling real-time updates THEN the Frontend SHALL use a custom useRealtimeData hook that manages WebSocket_Connection lifecycle

### Requirement 8

**User Story:** As a производственный оператор, I want to view analysis of profiles without photos, so that I can identify missing documentation.

#### Acceptance Criteria

1. WHEN viewing the Analysis page THEN the Ekranchik_System SHALL display a list of Profiles without photos sorted by usage frequency
2. WHEN switching to "Recent" mode THEN the Ekranchik_System SHALL show the last 50 records with profile information and photo status
3. WHEN switching to "Recent Missing" mode THEN the Ekranchik_System SHALL show unique Profiles without photos from recent records
4. WHEN searching for duplicates THEN the Ekranchik_System SHALL find Profiles with similar names using fuzzy matching
5. WHEN displaying analysis results THEN the Ekranchik_System SHALL provide direct upload buttons for Profiles without photos

### Requirement 9

**User Story:** As a разработчик, I want proper data validation and serialization, so that I can ensure data integrity across the system.

#### Acceptance Criteria

1. WHEN receiving API requests THEN the Ekranchik_System SHALL validate input data using Pydantic v2 schemas
2. WHEN returning API responses THEN the Ekranchik_System SHALL serialize data using Pydantic models with consistent field naming
3. WHEN parsing Excel data THEN the Ekranchik_System SHALL handle missing values and type conversions gracefully
4. WHEN normalizing text for search THEN the Ekranchik_System SHALL apply Latin/Cyrillic character mapping consistently
5. WHEN storing Profile data THEN the Ekranchik_System SHALL validate required fields and enforce data constraints

### Requirement 10

**User Story:** As a производственный оператор, I want to see FTP connection status and unload events, so that I can monitor PLC communication.

#### Acceptance Criteria

1. WHEN the FTP_Poller successfully connects THEN the Ekranchik_System SHALL display a green status indicator on the Dashboard
2. IF the FTP_Poller fails to connect THEN the Ekranchik_System SHALL display a red status indicator and log the error
3. WHEN an Unload_Event is detected THEN the Ekranchik_System SHALL parse the hanger number and timestamp from the log entry
4. WHEN displaying Unload_Events THEN the Ekranchik_System SHALL show the event time and hanger number in the Dashboard
5. WHEN the FTP log file changes date THEN the FTP_Poller SHALL reset its position and read from the new file
