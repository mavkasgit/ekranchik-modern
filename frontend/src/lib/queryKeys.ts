// Ключи кэша запросов в одном месте: по ним же строит инвалидацию realtime-модуль.
export const DASHBOARD_KEY = ['dashboard'] as const
export const FILE_STATUS_KEY = [...DASHBOARD_KEY, 'fileStatus'] as const
export const OPCUA_STATUS_KEY = [...DASHBOARD_KEY, 'opcuaStatus'] as const
export const MATCHED_UNLOAD_KEY = [...DASHBOARD_KEY, 'opcuaMatchedUnloadEvents'] as const
export const JOURNAL_KEY = ['journal', 'passes'] as const
export const LINE_STATUS_KEY = ['line', 'status'] as const
