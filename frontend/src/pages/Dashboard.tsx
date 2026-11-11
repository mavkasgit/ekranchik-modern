import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  RefreshCw,
  Wifi,
  WifiOff,
  FileSpreadsheet,
  Server,
  Image,
  Maximize2,
  Minimize2,
  X,
  AlertTriangle,
  Inbox,
  Clock,
  Pencil,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ClickableBookPath } from "@/components/ClickableBookPath";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";

import {
  useDashboard,
  useFileStatus,
  useOPCUAStatus,
  useOPCUAMatchedUnloadEvents,
} from "@/hooks/useDashboard";
import { useRealtimeConnection } from "@/hooks/useRealtime";
import { useTestRun } from "@/hooks/useTestRun";
import { DASHBOARD_KEY } from "@/lib/queryKeys";
import { SIDEBAR_ROW_LIMIT } from "@/config/limits";
import { colorHex, colorName } from "@/lib/domain/color";
import {
  describeHangerRow,
  isBlankRow,
  mergeHangerMeta,
  rowClassName,
} from "@/lib/domain/dashboardRow";
import { buildTestRows, type TestMode } from "@/lib/domain/simRows";
import { emptyRun, waitingRows } from "@/lib/domain/testRun";
import { photoUrl } from "@/lib/domain/photo";
import { profileText } from "@/lib/domain/profile";
import { parseRecentPaths, pathHint, rememberRecentPath } from "@/lib/domain/recentPaths";
import type { Profile } from "@/types/profile";
import { formatClock, formatLocalized } from "@/lib/domain/time";
import { BathForecast } from "@/components/BathForecastTable";
import { dashboardApi } from "@/api/dashboard";
import type { HangerData, ProfileInfo } from "@/types/dashboard";
import { useFullscreen } from "@/App";

const FILTERS_KEY = "ekranchik_filters";
const RECENT_PATHS_KEY = "ekranchik_excel_paths";

/** Рамка тестового режима: баннер убрали, подставные строки помечает заливка. */
const TEST_FRAME = "border-purple-500/40 bg-purple-500/5";

/** Пустой прогон для витринных режимов: карточек нет, линия не подмешивается. */
const EMPTY_RUN = emptyRun();
interface Filters {
  loadingLimit: number;
  realtimeLimit: number;
  showLoading: boolean;
  showRealtime: boolean;
  showForecast: boolean;
  showTime: boolean;
}

const defaultFilters: Filters = {
  loadingLimit: 6,
  realtimeLimit: 15,
  showLoading: true,
  showRealtime: true,
  showForecast: true,
  showTime: true,
};

function loadFilters(): Filters {
  try {
    const saved = localStorage.getItem(FILTERS_KEY);
    if (saved) {
      const parsed = JSON.parse(saved);
      return {
        ...defaultFilters,
        ...parsed,
        // Ensure limits are valid (min 1)
        loadingLimit: Math.max(1, parsed.loadingLimit || defaultFilters.loadingLimit),
        realtimeLimit: Math.max(1, parsed.realtimeLimit || defaultFilters.realtimeLimit),
      };
    }
  } catch {
    /* ignore */
  }
  return defaultFilters;
}

function saveFilters(filters: Filters) {
  localStorage.setItem(FILTERS_KEY, JSON.stringify(filters));
}

function loadRecentPaths(): string[] {
  try {
    return parseRecentPaths(localStorage.getItem(RECENT_PATHS_KEY));
  } catch {
    // localStorage недоступен (приватный режим) — памяти просто не будет.
    return [];
  }
}

function saveRecentPath(path: string): string[] {
  const next = rememberRecentPath(loadRecentPaths(), path);
  try {
    localStorage.setItem(RECENT_PATHS_KEY, JSON.stringify(next));
  } catch {
    /* ignore */
  }
  return next;
}

function RecentPathChips({
  paths,
  active,
  tone,
  onPick,
}: {
  paths: string[];
  active: string;
  tone: "main" | "reserve";
  onPick: (path: string) => void;
}) {
  if (paths.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5">
      <span className="text-[10px] text-muted-foreground">Последние:</span>
      {paths.map((path) => (
        <button
          key={path}
          type="button"
          onClick={() => onPick(path)}
          title={path}
          className={`max-w-[160px] truncate rounded-full border px-2 py-0.5 font-mono text-[10px] transition-colors ${
            path === active.trim()
              ? tone === "main"
                ? "border-emerald-500 bg-emerald-50 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-200"
                : "border-amber-500 bg-amber-50 text-amber-800 dark:bg-amber-500/15 dark:text-amber-200"
              : "border-border text-slate-600 hover:bg-muted dark:text-slate-300"
          }`}
        >
          {pathHint(path)}
        </button>
      ))}
    </div>
  );
}

// Format date with year 2026 (DD.MM.YY -> DD.MM.2026). null — строка книги
// не подобрана к этому проходу, показываем прочерк.
function formatDate(date: string | null | undefined): string {
  if (!date) return "—";
  // Handle formats like "28.10.26" or "29.11.2026"
  const parts = date.split(".");
  if (parts.length === 3) {
    const year = parts[2].length === 2 ? `20${parts[2]}` : parts[2];
    return `${parts[0]}.${parts[1]}.${year}`;
  }
  return date;
}

// Profile data type from catalog
interface ProfileData {
  id: number;
  name: string;
  quantity_per_hanger: number | null;
  length: number | null;
  notes: string | null;
}

// Photo Modal - with fullscreen support
function PhotoModal({
  open,
  onClose,
  photoUrl,
  profileName,
}: {
  open: boolean;
  onClose: () => void;
  photoUrl: string | null;
  profileName: string;
}) {
  const [imageSize, setImageSize] = useState<{ width: number; height: number } | null>(null);
  const [profileData, setProfileData] = useState<ProfileData | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Load image dimensions
  useEffect(() => {
    setImageSize(null);
    if (!photoUrl) return;

    const img = new window.Image();
    img.onload = () => {
      setImageSize({ width: img.naturalWidth, height: img.naturalHeight });
    };
    img.src = photoUrl;

    return () => {
      img.onload = null;
    };
  }, [photoUrl]);

  // Load profile data from catalog API
  useEffect(() => {
    setProfileData(null);
    if (!open || !profileName) return;

    fetch(`/api/catalog/${encodeURIComponent(profileName)}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => setProfileData(data))
      .catch(() => setProfileData(null));
  }, [open, profileName]);

  // Reset fullscreen when dialog closes
  useEffect(() => {
    if (!open) {
      setIsFullscreen(false);
    }
  }, [open]);

  // Handle ESC key
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (isFullscreen) {
          setIsFullscreen(false);
        } else {
          onClose();
        }
      }
    };

    if (open) {
      window.addEventListener("keydown", handleEsc);
      return () => window.removeEventListener("keydown", handleEsc);
    }
  }, [open, isFullscreen, onClose]);

  // Fullscreen API management
  useEffect(() => {
    if (!isFullscreen) return;

    const handleFullscreenChange = () => {
      if (!document.fullscreenElement) {
        setIsFullscreen(false);
      }
    };

    const handleEscFullscreen = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setIsFullscreen(false);
      }
    };

    document.addEventListener("fullscreenchange", handleFullscreenChange);
    window.addEventListener("keydown", handleEscFullscreen);

    return () => {
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
      window.removeEventListener("keydown", handleEscFullscreen);
    };
  }, [isFullscreen]);

  // Request fullscreen when isFullscreen becomes true
  useEffect(() => {
    if (!isFullscreen) return;

    const fullscreenElement = document.getElementById("fullscreen-photo-container");
    if (fullscreenElement && !document.fullscreenElement) {
      fullscreenElement.requestFullscreen().catch(() => {
        console.log("Fullscreen not supported");
      });
    }
  }, [isFullscreen]);

  // Calculate dialog size based on actual image pixels (like Catalog)
  const dialogSize = useMemo(() => {
    const rightPanelWidth = 280;
    const maxDialogHeight = typeof window !== "undefined" ? window.innerHeight - 100 : 800;
    const maxDialogWidth = typeof window !== "undefined" ? window.innerWidth - 100 : 1200;
    const minHeight = 400;

    if (!imageSize) {
      return { width: Math.min(900, maxDialogWidth), height: minHeight };
    }

    let imgDisplayWidth = imageSize.width;
    let imgDisplayHeight = imageSize.height;

    // Scale down if image is too tall
    if (imgDisplayHeight > maxDialogHeight) {
      const scale = maxDialogHeight / imgDisplayHeight;
      imgDisplayWidth = imgDisplayWidth * scale;
      imgDisplayHeight = maxDialogHeight;
    }

    // Scale down if dialog would be too wide
    const dialogWidth = imgDisplayWidth + rightPanelWidth;
    if (dialogWidth > maxDialogWidth) {
      const scale = (maxDialogWidth - rightPanelWidth) / imgDisplayWidth;
      imgDisplayWidth = imgDisplayWidth * scale;
      imgDisplayHeight = imgDisplayHeight * scale;
    }

    return {
      width: Math.max(600, imgDisplayWidth + rightPanelWidth),
      height: Math.max(minHeight, imgDisplayHeight),
    };
  }, [imageSize]);

  if (!photoUrl) return null;

  // Fullscreen mode - using browser fullscreen API (rendered at end of component)

  return (
    <>
      <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
        <DialogContent
          className="p-0 gap-0 top-[5%] translate-y-0"
          style={{
            width: `${dialogSize.width}px`,
            height: `${dialogSize.height}px`,
            maxWidth: "calc(100vw - 100px)",
          }}
          onOpenAutoFocus={(e) => e.preventDefault()}
        >
          <div className="flex h-full">
            {/* Photo area - left side */}
            <div className="flex-1 bg-muted flex items-center justify-center overflow-auto relative">
              <Button
                variant="ghost"
                size="icon"
                className="absolute top-2 right-2 z-10"
                onClick={() => setIsFullscreen(true)}
                title="Развернуть на весь экран"
              >
                <Maximize2 className="h-5 w-5" />
              </Button>
              <div
                className="relative w-full h-full flex items-center justify-center select-none cursor-pointer"
                onClick={() => setIsFullscreen(true)}
              >
                <img
                  src={photoUrl}
                  alt={profileName}
                  className="max-w-full max-h-full object-contain pointer-events-none"
                />
              </div>
            </div>

            {/* Right panel - info (like Catalog view mode) */}
            <div className="border-l bg-background p-4 flex flex-col" style={{ width: "280px" }}>
              <div className="flex-1 space-y-4 overflow-y-auto">
                <h2 className="text-xl font-semibold">{profileName}</h2>
                <div className="space-y-3 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Кол-во на подвесе:</span>
                    <span className="font-medium">{profileData?.quantity_per_hanger ?? "—"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Длина:</span>
                    <span className="font-medium">
                      {profileData?.length ? `${profileData.length} мм` : "—"}
                    </span>
                  </div>
                </div>
                {profileData?.notes && (
                  <div className="pt-2 border-t">
                    <span className="text-sm text-muted-foreground">Примечания:</span>
                    <p className="mt-1 text-sm">{profileData.notes}</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Fullscreen overlay - desktop only */}
      {isFullscreen && photoUrl && typeof window !== "undefined" && window.innerWidth >= 768 && (
        <div
          id="fullscreen-photo-container"
          className="fixed inset-0 z-[100] bg-black flex items-center justify-center"
          onClick={() => setIsFullscreen(false)}
        >
          {/* Large close area for mobile - top-left corner */}
          {typeof window !== "undefined" && window.innerWidth < 768 && (
            <div
              className="absolute top-0 left-0 w-16 h-16 z-20 cursor-pointer"
              onClick={(e) => {
                e.stopPropagation();
                setIsFullscreen(false);
              }}
            />
          )}

          <Button
            variant="ghost"
            size="icon"
            className="absolute top-4 right-4 text-white hover:bg-white/20 z-10"
            onClick={(e) => {
              e.stopPropagation();
              setIsFullscreen(false);
            }}
          >
            <Minimize2 className="h-6 w-6" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="absolute top-4 right-16 text-white hover:bg-white/20 z-10"
            onClick={(e) => {
              e.stopPropagation();
              onClose();
              setIsFullscreen(false);
            }}
          >
            <X className="h-6 w-6" />
          </Button>
          <img
            src={photoUrl}
            alt={profileName}
            className="max-w-full max-h-full object-contain cursor-pointer"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </>
  );
}

// Photo cell - wrapping layout, max 700px width, photos wrap to new rows
function PhotoCell({
  hanger,
  onPhotoClick,
}: {
  hanger: HangerData;
  onPhotoClick: (url: string, name: string) => void;
}) {
  const profilesInfo = hanger.profiles_info || [];

  if (profilesInfo.length > 0) {
    return (
      <div
        className="flex flex-nowrap gap-2 items-center justify-start overflow-x-auto py-1 px-0.5 [&::-webkit-scrollbar]:h-1.5 [&::-webkit-scrollbar-thumb]:bg-slate-300 dark:[&::-webkit-scrollbar-thumb]:bg-slate-700 [&::-webkit-scrollbar-thumb]:rounded-full"
        style={{ maxWidth: "350px" }}
      >
        {profilesInfo.map((prof, idx) => (
          <ProfilePhoto key={idx} profile={prof} onPhotoClick={onPhotoClick} />
        ))}
      </div>
    );
  }

  // Helper to render profile name next to photo
  const ProfileName = () => (
    <div className="flex flex-col justify-center min-w-0 ml-2 text-left">
      <p className="text-xs font-bold text-foreground truncate max-w-[70px]">
        {hanger.canonical_name || hanger.profile}
      </p>
    </div>
  );

  const thumbUrl = photoUrl(hanger.profile_photo_thumb);
  if (thumbUrl) {
    return (
      <div className="flex items-center justify-center gap-1.5" style={{ maxWidth: "800px" }}>
        <div className="flex items-center">
          <img
            src={thumbUrl}
            alt={hanger.profile}
            className="w-auto h-auto max-h-[40px] max-w-[90px] object-contain rounded cursor-pointer hover:scale-105 transition-transform border border-border hover:border-primary"
            onClick={() =>
              onPhotoClick(
                photoUrl(hanger.profile_photo_full || hanger.profile_photo_thumb) || "",
                hanger.profile,
              )
            }
          />
          <ProfileName />
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center gap-1.5" style={{ maxWidth: "800px" }}>
      <div className="flex items-center">
        <div className="w-10 h-10 bg-muted rounded flex items-center justify-center flex-shrink-0">
          <Image className="w-5 h-5 text-muted-foreground" />
        </div>
        <ProfileName />
      </div>
    </div>
  );
}

function ProfilePhoto({
  profile,
  onPhotoClick,
  hideText = false,
}: {
  profile: ProfileInfo;
  onPhotoClick: (url: string, name: string) => void;
  hideText?: boolean;
}) {
  const thumbUrl = photoUrl(profile.photo_thumb, profile.updated_at);
  const fullUrl = photoUrl(profile.photo_full || profile.photo_thumb, profile.updated_at);
  const hasPhoto = profile.has_photo && thumbUrl;

  return (
    <div className="flex items-center gap-2">
      {hasPhoto ? (
        <img
          src={thumbUrl}
          alt={profile.name}
          className="w-auto h-auto max-h-[40px] max-w-[90px] object-contain rounded cursor-pointer hover:scale-105 transition-transform border border-border hover:border-primary flex-shrink-0"
          onClick={() => onPhotoClick(fullUrl || "", profile.canonical_name || profile.name)}
        />
      ) : (
        <div className="w-12 h-12 bg-muted rounded flex items-center justify-center flex-shrink-0">
          <Image className="w-5 h-5 text-muted-foreground" />
        </div>
      )}
      {!hideText && (
        <div className="flex flex-col justify-center min-w-0">
          <p className="text-xs font-bold text-foreground truncate max-w-[70px]">
            {profile.canonical_name || profile.name}
          </p>
          {profile.processing && profile.processing.length > 0 && (
            <div className="flex gap-1 mt-1 flex-wrap">
              {profile.processing.map((proc, i) => (
                <Badge
                  key={i}
                  className="text-[10px] px-1 py-0 bg-yellow-400 text-yellow-900 hover:bg-yellow-500"
                >
                  {proc}
                </Badge>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function StatusBar({ onOpenPathModal }: { onOpenPathModal: () => void }) {
  const { data: fileStatus } = useFileStatus();
  const { data: opcuaStatus } = useOPCUAStatus();
  const { isConnected, lastMessage } = useRealtimeConnection();

  const fileIsOpen = fileStatus?.is_open;
  const statusColor = fileStatus?.error
    ? "bg-yellow-500"
    : fileIsOpen
      ? "bg-green-500"
      : "bg-destructive";

  // Полный путь: имя файла его не содержит, а оператору нужен — по нему
  // видно, что сервер читает действительно тот файл и с сетевого диска.
  const filePath = fileStatus?.file_path;

  // Роль книги. Режим выключен — на пилюле так и написано: «основная» без
  // альтернативы ничего не сообщает, а оператор не узнает, что режим есть.
  const role = fileStatus?.role ?? null;
  const standbyEnabled = Boolean(fileStatus?.reserve_file_path);
  const activeName = fileStatus?.file_name || "—";
  const pillTone = !standbyEnabled
    ? "border-dashed border-amber-500 text-amber-800 hover:bg-amber-50 dark:text-amber-300 dark:hover:bg-amber-500/10"
    : role === "reserve"
      ? "border-amber-500 bg-amber-50 text-amber-900 hover:bg-amber-100 dark:bg-amber-500/15 dark:text-amber-200 dark:hover:bg-amber-500/20"
      : "border-border bg-background text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800";

  return (
    <Card>
      <CardContent className="py-3">
        <div className="flex flex-wrap items-center justify-between gap-6 text-sm">
          <div className="flex flex-wrap items-center gap-6">
            <div className="flex items-center gap-2">
              <FileSpreadsheet className="w-4 h-4 text-muted-foreground" />
              <div className={`w-2 h-2 rounded-full ${statusColor}`} />
              <span className="font-medium">{fileStatus?.status_text || "—"}</span>

              {/* Путь — кнопка: нажатие в любом месте открывает список книг. */}
              {filePath && (
                <button
                  type="button"
                  onClick={onOpenPathModal}
                  title="Изменить книги учёта"
                  className="group flex min-w-0 max-w-[380px] items-center gap-1 text-muted-foreground hover:text-foreground"
                >
                  <span className="truncate font-mono text-xs">{filePath}</span>
                  <Pencil className="w-3 h-3 shrink-0 opacity-40 group-hover:opacity-100" />
                </button>
              )}

              <button
                type="button"
                onClick={onOpenPathModal}
                title="Изменить книги учёта"
                className={`flex items-center gap-2 rounded-full border px-3 py-1 text-xs transition-colors ${pillTone}`}
              >
                <FileSpreadsheet className="w-3.5 h-3.5" />
                <span className="font-semibold">
                  {!standbyEnabled
                    ? "Запасная не настроена"
                    : role === "reserve"
                      ? "ЗАПАСНАЯ"
                      : "Основная"}
                </span>
                {standbyEnabled && (
                  <span className="max-w-[180px] truncate font-mono text-[11px] opacity-70">
                    {activeName}
                  </span>
                )}
                <Pencil className="w-3 h-3 opacity-50" />
              </button>

              {fileStatus?.last_modified && (
                <span className="text-muted-foreground text-xs">
                  ({new Date(fileStatus.last_modified).toLocaleString("ru")})
                </span>
              )}
            </div>

            <div className="w-px h-4 bg-border" />

            <div className="flex items-center gap-2">
              <Server className="w-4 h-4 text-muted-foreground" />
              <div
                className={`w-2 h-2 rounded-full ${opcuaStatus?.is_open ? "bg-green-500" : "bg-destructive"}`}
              />
              <span>OPC UA: {opcuaStatus?.is_open ? "OK" : "Откл"}</span>
              {opcuaStatus?.last_modified && (
                <span className="text-muted-foreground text-xs">
                  ({formatLocalized(opcuaStatus.last_modified)})
                </span>
              )}
            </div>

            <div className="w-px h-4 bg-border" />

            <div className="flex items-center gap-2">
              {isConnected ? (
                <Wifi className="w-4 h-4 text-green-500" />
              ) : (
                <WifiOff className="w-4 h-4 text-destructive" />
              )}
              <span>WS: {isConnected ? "Онлайн" : "Офлайн"}</span>
              {lastMessage?.timestamp && (
                <span className="text-muted-foreground text-xs">
                  ({formatLocalized(lastMessage.timestamp)})
                </span>
              )}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function ClockInline() {
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  return <span>{formatLocalized(time, "ru-RU")}</span>;
}

// Data table
function DataTable({
  data,
  onPhotoClick,
  isFullscreen = false,
  showEntryExit = false,
  ariaLabel,
}: {
  data: HangerData[];
  onPhotoClick: (url: string, name: string) => void;
  isFullscreen?: boolean;
  showEntryExit?: boolean;
  /** Имя таблицы: две таблицы дашборда различаются только содержимым. */
  ariaLabel?: string;
}) {
  const gridTemplateColumns = showEntryExit
    ? "[date] 70px [time] 50px [num] 25px [type] 70px [kpz] 50px [client] 100px [profile] fit-content(120px) [photo] minmax(120px, 1fr) [lamels] 45px [color] 65px"
    : "[date] 70px [num] 25px [type] 70px [kpz] 50px [client] 100px [profile] fit-content(120px) [photo] minmax(120px, 1fr) [lamels] 45px [color] 65px";

  return (
    <div
      className={`overflow-auto text-sm border border-slate-200 dark:border-slate-800 ${isFullscreen ? "max-h-screen rounded-none border-none" : "rounded-md max-h-[500px]"}`}
    >
      {/* Роли ARIA поверх grid-рисования: экранный диктор и e2e читают строку
          дашборда как таблицу, хотя раскладку задаёт grid. */}
      <div
        className="grid w-full text-sm"
        role="table"
        aria-label={ariaLabel}
        style={{ gridTemplateColumns }}
      >
        {/* Шапка таблицы */}
        <div
          role="row"
          className="sticky top-0 bg-muted z-20 text-[14px] font-semibold text-foreground/85 tracking-tight border-b border-slate-300 dark:border-slate-700 grid col-span-full"
          style={{ gridTemplateColumns, display: "grid" }}
        >
          <div
            role="columnheader"
            className="text-center py-1.5 flex items-center justify-center"
            style={{ gridColumn: "date" }}
          >
            Дата
          </div>
          {showEntryExit && (
            <div
              role="columnheader"
              className="text-center py-1.5 flex items-center justify-center"
              style={{ gridColumn: "time" }}
            >
              Время
            </div>
          )}
          <div
            role="columnheader"
            className="text-center py-1.5 flex items-center justify-center"
            style={{ gridColumn: "num" }}
          >
            №
          </div>
          <div
            role="columnheader"
            className="text-center py-1.5 flex items-center justify-center"
            style={{ gridColumn: "type" }}
          >
            Тип
          </div>
          <div
            role="columnheader"
            className="text-center py-1.5 flex items-center justify-center"
            style={{ gridColumn: "kpz" }}
          >
            № КПЗ
          </div>
          <div
            role="columnheader"
            className="text-left py-1.5 px-2 flex items-center justify-start"
            style={{ gridColumn: "client" }}
          >
            Клиент
          </div>
          <div
            role="columnheader"
            className="text-left py-1.5 px-2 flex items-center justify-start"
            style={{ gridColumn: "profile" }}
          >
            Профиль
          </div>
          <div
            role="columnheader"
            className="text-center py-1.5 flex items-center justify-center"
            style={{ gridColumn: "photo" }}
          >
            Фото
          </div>
          <div
            role="columnheader"
            className="text-center py-1.5 flex items-center justify-center"
            style={{ gridColumn: "lamels" }}
          >
            Ламели
          </div>
          <div
            role="columnheader"
            className="text-center py-1.5 flex items-center justify-center"
            style={{ gridColumn: "color" }}
          >
            Цвет
          </div>
        </div>

        {/* Тело таблицы */}
        {data.map((hanger, idx) => {
          const meaning = describeHangerRow(hanger, idx);
          const profilesInfo = hanger.profiles_info || [];

          return (
            <div
              key={`${hanger.number}-${idx}`}
              role="row"
              className={`grid col-span-full border-b border-slate-200 dark:border-slate-800 group ${meaning.className}`}
              style={{ gridTemplateColumns, display: "grid" }}
            >
              {/* Дата и Время (с вертикальным объединением) */}
              {showEntryExit ? (
                <>
                  <div
                    role="cell"
                    data-column="date"
                    className="text-center py-1 text-sm flex items-center justify-center"
                    style={{
                      gridColumn: "date",
                      gridRow: meaning.photosBelow ? "1" : `span ${meaning.rowSpan}`,
                    }}
                  >
                    {formatDate(hanger.entry_date) === formatDate(hanger.exit_date) ? (
                      <span>{formatDate(hanger.entry_date)}</span>
                    ) : (
                      <div className="flex flex-col">
                        <span className="text-blue-600">{formatDate(hanger.entry_date)}</span>
                        <span className="text-green-600">{formatDate(hanger.exit_date)}</span>
                      </div>
                    )}
                  </div>
                  <div
                    role="cell"
                    data-column="time"
                    className="text-center py-1 text-sm flex items-center justify-center"
                    style={{
                      gridColumn: "time",
                      gridRow: meaning.photosBelow ? "1" : `span ${meaning.rowSpan}`,
                    }}
                  >
                    <div className="flex flex-col">
                      <span className="text-blue-600">{formatClock(hanger.entry_time)}</span>
                      <span className="text-green-600">{formatClock(hanger.exit_time)}</span>
                    </div>
                  </div>
                </>
              ) : (
                <div
                  role="cell"
                  data-column="date"
                  className="text-center py-1 flex items-center justify-center"
                  style={{
                    gridColumn: "date",
                    gridRow: meaning.photosBelow ? "1" : `span ${meaning.rowSpan}`,
                  }}
                >
                  {hanger.date}
                </div>
              )}

              {/* Номер вешалки */}
              <div
                role="cell"
                data-column="num"
                className="text-center font-bold py-1 flex items-center justify-center"
                style={{
                  gridColumn: "num",
                  gridRow: meaning.photosBelow ? "1" : `span ${meaning.rowSpan}`,
                }}
              >
                {hanger.number}
              </div>

              {/* Основные параметры детали (Тип, КПЗ, Клиент) */}
              <div
                role="cell"
                data-column="type"
                className="text-center py-1 flex items-center justify-center"
                style={{ gridColumn: "type", gridRow: "1" }}
              >
                {hanger.material_type}
              </div>
              <div
                role="cell"
                data-column="kpz"
                className="text-center py-1 flex items-center justify-center"
                style={{ gridColumn: "kpz", gridRow: "1" }}
              >
                {hanger.kpz_number}
              </div>
              <div
                role="cell"
                data-column="client"
                className="text-left py-1 flex items-center justify-start truncate min-w-0 px-2"
                style={{ gridColumn: "client", gridRow: "1" }}
                title={hanger.client}
              >
                {hanger.client}
              </div>

              {/* Профиль и Фото: много профилей — фото уходят на второй ряд */}
              {meaning.photosBelow ? (
                <div
                  role="cell"
                  data-column="profile"
                  className="text-left py-1 flex items-center justify-start min-w-0 px-2"
                  style={{ gridColumn: "profile / lamels", gridRow: "1" }}
                  title={hanger.profile}
                >
                  <span className="truncate font-bold text-foreground">{meaning.profileLabel}</span>
                </div>
              ) : (
                <>
                  <div
                    role="cell"
                    data-column="profile"
                    className="text-left py-1 flex items-center justify-start min-w-0 px-2"
                    style={{ gridColumn: "profile", gridRow: "1" }}
                    title={hanger.profile}
                  >
                    <span className="truncate">{meaning.profileLabel}</span>
                  </div>
                  <div
                    role="cell"
                    data-column="photo"
                    className="py-1 flex items-center justify-center"
                    style={{
                      gridColumn: "photo",
                      gridRow: `span ${meaning.rowSpan}`,
                    }}
                  >
                    <PhotoCell hanger={hanger} onPhotoClick={onPhotoClick} />
                  </div>
                </>
              )}

              {/* Ламели */}
              <div
                role="cell"
                data-column="lamels"
                className="text-center font-bold py-1 flex items-center justify-center"
                style={{
                  gridColumn: "lamels",
                  gridRow: meaning.photosBelow ? "1" : `span ${meaning.rowSpan}`,
                }}
              >
                {hanger.lamels_qty}
              </div>

              {/* Цвет */}
              <div
                role="cell"
                data-column="color"
                className="text-center py-1 flex items-center justify-center"
                style={{
                  gridColumn: "color",
                  gridRow: meaning.photosBelow ? "1" : `span ${meaning.rowSpan}`,
                }}
              >
                <div className="inline-flex flex-col items-center max-w-[80px]">
                  <span className="text-sm leading-tight text-center break-words">
                    {colorName(hanger.color)}
                  </span>
                  <div
                    className="w-full h-1.5 rounded-full mt-0.5"
                    style={{ backgroundColor: colorHex(hanger.color), minWidth: "50px" }}
                  />
                </div>
              </div>

              {/* Вторая строка подвеса: пометки и фото профилей */}
              {meaning.detailRow && (
                <div
                  role="cell"
                  data-column="detail"
                  className="py-1.5 px-3 flex flex-wrap items-center justify-start gap-x-4 gap-y-1.5"
                  style={{
                    gridRow: "2",
                    gridColumn: meaning.photosBelow ? "1 / -1" : "type / photo",
                  }}
                >
                  {meaning.badges.length > 0 && (
                    <div className="flex items-center gap-1.5">
                      {meaning.badges.map((badge) => (
                        <span
                          key={badge.code}
                          className={`${badge.className} font-bold text-[10px] px-2 py-0.5 rounded whitespace-nowrap inline-block border`}
                          title={
                            badge.code === "DEFECT" ? undefined : (hanger.time_warning ?? undefined)
                          }
                        >
                          {badge.label}
                        </span>
                      ))}
                    </div>
                  )}
                  {meaning.photosBelow && (
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
                      {profilesInfo.map((prof, pIdx) => (
                        <ProfilePhoto
                          key={pIdx}
                          profile={prof}
                          onPhotoClick={onPhotoClick}
                          hideText={false}
                        />
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SidebarQueueTable({
  data,
  isLoading,
  isFullscreen = false,
}: {
  data?: HangerData[];
  isLoading: boolean;
  isFullscreen?: boolean;
}) {
  const filteredData = useMemo(() => {
    const nonEmpty = data?.filter((hanger) => !isBlankRow(hanger)) || [];

    const withoutTime = nonEmpty.filter(
      (h) => !h.time || h.time.trim() === "—" || h.time.trim() === "",
    );
    const withTime = nonEmpty.filter(
      (h) => h.time && h.time.trim() !== "—" && h.time.trim() !== "",
    );

    // Ограничиваем планируемые/активные (без времени) до 6 ближайших к выгрузке
    const recentWithoutTime = withoutTime.slice(-6);

    // Выгруженные (со временем) оставляем полностью
    return [...recentWithoutTime, ...withTime];
  }, [data]);

  return (
    <Card
      className={`border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col w-full ${isFullscreen ? "max-h-screen h-screen rounded-none border-none" : "max-h-[500px] xl:max-h-[600px]"}`}
    >
      <CardContent className="p-0 overflow-hidden flex flex-col flex-1">
        {isLoading ? (
          <div className="space-y-1.5 p-3">
            {[...Array(6)].map((_, i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        ) : filteredData.length > 0 ? (
          <div className="overflow-auto text-[11px] flex-1 min-h-0 h-full">
            <Table>
              <TableHeader className="sticky top-0 bg-muted z-10 text-[12px] font-semibold text-foreground/85 tracking-tight">
                <TableRow>
                  <TableHead className="w-12 text-center py-1.5 px-2">Время</TableHead>
                  <TableHead className="w-10 text-center py-1.5 px-2">№</TableHead>
                  <TableHead className="text-left py-1.5 px-2">Профиль</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredData.map((hanger, idx) => {
                  const meaning = describeHangerRow(hanger, idx);
                  // Боковая очередь узкая: «Клюшки» уже короткие, остальное
                  // сжимаем до цифр книги, как и раньше.
                  const cleanedProfile = meaning.sticks
                    ? meaning.profileLabel
                    : profileText(hanger.profile);
                  const displayProfile =
                    cleanedProfile.length > 8 ? cleanedProfile.slice(0, 8) + ".." : cleanedProfile;
                  return (
                    <TableRow
                      key={`sidebar-${hanger.number}-${idx}`}
                      className={rowClassName(hanger, idx)}
                    >
                      <TableCell className="text-center py-1.5 px-2 font-mono whitespace-nowrap">
                        {hanger.time || "—"}
                      </TableCell>
                      <TableCell className="text-center py-1.5 px-2 font-bold font-mono">
                        {hanger.number || "—"}
                      </TableCell>
                      <TableCell
                        className="text-left py-1.5 px-2 font-semibold truncate max-w-[120px]"
                        title={hanger.profile}
                      >
                        <div className="flex items-center gap-1.5">
                          {hanger.color &&
                            hanger.color.trim() !== "—" &&
                            hanger.color.trim() !== "" && (
                              <span
                                className="w-2.5 h-2.5 rounded-full inline-block shrink-0 border border-black/15 dark:border-white/15"
                                style={{ backgroundColor: colorHex(hanger.color) }}
                                title={colorName(hanger.color)}
                              />
                            )}
                          <span className="truncate">{displayProfile}</span>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-8 text-center text-muted-foreground text-xs">
            <span>Очередь пуста</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function TableSkeleton() {
  return (
    <div className="space-y-2 p-4">
      {[...Array(5)].map((_, i) => (
        <Skeleton key={i} className="h-16 w-full" />
      ))}
    </div>
  );
}

// Filters
function FiltersPanel({
  filters,
  onChange,
  onApply,
  onReset,
  onToggleLast100,
  isLast100Mode,
  onToggleTestMode,
  testMode,
  testError,
}: {
  filters: Filters;
  onChange: (filters: Filters) => void;
  onApply: () => void;
  onReset: () => void;
  onToggleLast100: () => void;
  isLast100Mode: boolean;
  onToggleTestMode: (mode: TestMode) => void;
  testMode: TestMode | null;
  testError: string | null;
}) {
  // В режиме симуляции фильтры остаются живыми: окно загрузки и выгрузки
  // берётся из них. В режимах «Все профили» и «Все цвета» витрина показывает
  // весь круг, поэтому потолок «Загрузка» к нему не относится и число гасится;
  // галка остаётся живой — она включает и выключает саму таблицу.
  const otherFiltersDisabled = isLast100Mode;
  const loadingLimitDisabled =
    otherFiltersDisabled || testMode === "catalog" || testMode === "colors";

  return (
    <Card>
      <CardContent className="py-4">
        <div className="space-y-4">
          {/* Top row - Filters */}
          <div className="flex items-center gap-4">
            {/* Loading */}
            <div
              className={`flex items-center gap-2 border rounded-md px-2 py-1.5 ${otherFiltersDisabled ? "opacity-50" : "border-blue-500/50 bg-blue-500/10"}`}
            >
              <Checkbox
                id="show-loading"
                className="h-3.5 w-3.5"
                checked={filters.showLoading}
                onCheckedChange={(c) => onChange({ ...filters, showLoading: !!c })}
                disabled={otherFiltersDisabled}
              />
              <Label
                htmlFor="show-loading"
                className={`text-sm cursor-pointer whitespace-nowrap ${otherFiltersDisabled ? "cursor-not-allowed" : ""}`}
              >
                Загрузка:
              </Label>
              <Input
                type="number"
                value={filters.loadingLimit}
                onChange={(e) => {
                  const val = e.target.value;
                  onChange({ ...filters, loadingLimit: val === "" ? ("" as any) : Number(val) });
                }}
                onBlur={(e) => {
                  const val = e.target.value;
                  if (val === "" || Number(val) < 1) {
                    onChange({ ...filters, loadingLimit: 1 });
                  }
                }}
                className="w-12 h-7 text-center text-xs px-1"
                min={1}
                max={500}
                disabled={loadingLimitDisabled}
              />
            </div>

            {/* Realtime */}
            <div
              className={`flex items-center gap-2 border rounded-md px-2 py-1.5 ${otherFiltersDisabled ? "opacity-50" : "border-green-500/50 bg-green-500/10"}`}
            >
              <Checkbox
                id="show-realtime"
                className="h-3.5 w-3.5"
                checked={filters.showRealtime}
                onCheckedChange={(c) => onChange({ ...filters, showRealtime: !!c })}
                disabled={otherFiltersDisabled}
              />
              <Label
                htmlFor="show-realtime"
                className={`text-sm cursor-pointer whitespace-nowrap ${otherFiltersDisabled ? "cursor-not-allowed" : ""}`}
              >
                Выгрузка:
              </Label>
              <Input
                type="number"
                value={filters.realtimeLimit}
                onChange={(e) => {
                  const val = e.target.value;
                  onChange({ ...filters, realtimeLimit: val === "" ? ("" as any) : Number(val) });
                }}
                onBlur={(e) => {
                  const val = e.target.value;
                  if (val === "" || Number(val) < 1) {
                    onChange({ ...filters, realtimeLimit: 1 });
                  }
                }}
                className="w-12 h-7 text-center text-xs px-1"
                min={1}
                max={500}
                disabled={otherFiltersDisabled}
              />
            </div>

            {/* Forecast */}
            <div className="flex items-center gap-2 border rounded-md px-2 py-1.5 border-purple-500/50 bg-purple-500/10">
              <Checkbox
                id="show-forecast"
                className="h-3.5 w-3.5"
                checked={filters.showForecast}
                onCheckedChange={(c) => onChange({ ...filters, showForecast: !!c })}
              />
              <Label htmlFor="show-forecast" className="text-sm cursor-pointer whitespace-nowrap">
                Прогноз выхода
              </Label>
            </div>
          </div>

          {/* Bottom row - Buttons */}
          <div className="flex flex-wrap gap-4 items-center justify-between">
            <div className="flex gap-4">
              <Button variant={isLast100Mode ? "default" : "outline"} onClick={onToggleLast100}>
                Последние 100
              </Button>

              <Button
                variant={testMode === "catalog" ? "default" : "outline"}
                onClick={() => onToggleTestMode("catalog")}
                className={testMode === "catalog" ? "bg-purple-600 hover:bg-purple-700" : ""}
              >
                Все профили
              </Button>

              <Button
                variant={testMode === "colors" ? "default" : "outline"}
                onClick={() => onToggleTestMode("colors")}
                className={testMode === "colors" ? "bg-purple-600 hover:bg-purple-700" : ""}
              >
                Все цвета
              </Button>

              <Button
                variant={testMode === "sim" ? "default" : "outline"}
                onClick={() => onToggleTestMode("sim")}
                className={testMode === "sim" ? "bg-purple-600 hover:bg-purple-700" : ""}
              >
                Симуляция дашборда
              </Button>
            </div>

            {testError && (
              <span className="text-sm text-red-600 dark:text-red-400">{testError}</span>
            )}

            <div className="flex gap-2">
              <Button onClick={onApply} disabled={otherFiltersDisabled}>
                Применить
              </Button>
              <Button variant="outline" onClick={onReset} disabled={otherFiltersDisabled}>
                Сбросить
              </Button>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

const formatLastModified = (isoString?: string) => {
  if (!isoString) return "—";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    const day = String(d.getDate()).padStart(2, "0");
    const month = String(d.getMonth() + 1).padStart(2, "0");
    const year = d.getFullYear();
    const hours = String(d.getHours()).padStart(2, "0");
    const minutes = String(d.getMinutes()).padStart(2, "0");
    const seconds = String(d.getSeconds()).padStart(2, "0");
    return `${day}.${month}.${year}, ${hours}:${minutes}:${seconds}`;
  } catch {
    return isoString;
  }
};
// Текст ошибки API: detail от FastAPI (HTTPException) либо message транспорта.
function apiErrorMessage(err: unknown, fallback: string): string {
  if (typeof err === "object" && err !== null) {
    if ("response" in err && typeof err.response === "object" && err.response !== null) {
      const response = err.response;
      if ("data" in response && typeof response.data === "object" && response.data !== null) {
        const data = response.data;
        if ("detail" in data && typeof data.detail === "string") return data.detail;
      }
    }
    if ("message" in err && typeof err.message === "string") return err.message;
  }
  return fallback;
}

// Время последнего роста основной книги для баннера: оператору нужны часы и
// минуты, а formatLocalized отдаёт HH:MM:SS.
function growthClock(value?: string | null): string | null {
  const localized = formatLocalized(value);
  if (localized === "—") return null;
  const [hours, minutes] = localized.split(":");
  return hours && minutes ? `${hours}:${minutes}` : localized;
}

// Main
export default function Dashboard() {
  const [filters, setFilters] = useState<Filters>(loadFilters);
  const { isFullscreen, setIsFullscreen } = useFullscreen();
  const [photoModal, setPhotoModal] = useState<{ url: string; name: string } | null>(null);
  const [isPathModalOpen, setIsPathModalOpen] = useState(false);
  // Две книги: основная и запасная. Какую читать сейчас, решает сервер по
  // росту строк (ADR 0009), поэтому здесь только пути, без выбора источника.
  const [mainPathInput, setMainPathInput] = useState("");
  const [reservePathInput, setReservePathInput] = useState("");
  const [pathError, setPathError] = useState<string | null>(null);
  // Последние введённые пути: чипы под каждым полем, чтобы не набирать заново.
  const [recentPaths, setRecentPaths] = useState<string[]>(loadRecentPaths);
  const [hasNewRows, setHasNewRows] = useState(false);
  const [hasNewUnloadEvents, setHasNewUnloadEvents] = useState(false);
  const lastModifiedRef = useRef<string | null>(null);
  const prevDataRef = useRef<HangerData[]>([]);
  const prevUnloadDataRef = useRef<any[]>([]);
  const prevSimLoadingKeyRef = useRef("");
  const prevSimUnloadKeyRef = useRef("");

  // Таймер автовозврата в fullscreen
  const [autoReturnCountdown, setAutoReturnCountdown] = useState<number | null>(null);
  const autoReturnTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const countdownIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // State for "Последние 100" toggle
  const [isLast100Mode, setIsLast100Mode] = useState(false);
  const [preLast100Filters, setPreLast100Filters] = useState<Filters | null>(null);

  // Режим витрины: null — боевые данные, остальные три подменяют таблицы дашборда.
  const [testMode, setTestMode] = useState<TestMode | null>(null);
  const [testRows, setTestRows] = useState<HangerData[]>([]);
  const [testError, setTestError] = useState<string | null>(null);

  // Тестовый прогон витрины: подвесы идут по ваннам и уходят в выгрузку
  const run = useTestRun(testMode === "sim" ? testRows : undefined, filters.realtimeLimit);

  // Determine if the API should filter for loading_only rows
  const loadingOnly = !isLast100Mode;

  const queryClient = useQueryClient();
  const { data, isLoading, refetch, isFetching } = useDashboard(
    7,
    filters.loadingLimit,
    loadingOnly,
  );
  const {
    data: recentAllData,
    isLoading: isLoadingAll,
    refetch: refetchRecentAll,
    isFetching: isRecentAllFetching,
  } = useDashboard(7, SIDEBAR_ROW_LIMIT, false);
  const { data: fileStatus } = useFileStatus();
  const { data: matchedEvents } = useOPCUAMatchedUnloadEvents(filters.realtimeLimit);

  // Роли книг — единственное, что задаёт оператор: какую книгу читать сейчас,
  // решает правило `standby_book` по росту строк.
  const handleSaveBookRoles = async (
    mainPath: string,
    reservePath: string | null,
  ): Promise<boolean> => {
    try {
      setPathError(null);
      const res = await dashboardApi.saveBookRoles(mainPath, reservePath);
      if (res.success) {
        // Строка статуса берёт имя книги из /status/file: тот же префикс ключа.
        queryClient.invalidateQueries({ queryKey: DASHBOARD_KEY });
      }
      return res.success;
    } catch (err: unknown) {
      console.error("Ошибка сохранения ролей книг:", err);
      // Диалог не закрываем: оператор поправит путь здесь же. Ошибку держим
      // в диалоге, потому что alert поверх киоска оператор часто не читает.
      setPathError(apiErrorMessage(err, "Ошибка сохранения ролей книг"));
      return false;
    }
  };

  // Открытие диалога: поля заполнены текущими книгами, иначе последним
  // введённым путём. Путь в поле правится на месте (ClickableBookPath).
  const openPathModal = () => {
    const remembered = loadRecentPaths();
    setRecentPaths(remembered);
    setMainPathInput(fileStatus?.main_file_path || fileStatus?.file_path || remembered[0] || "");
    setReservePathInput(fileStatus?.reserve_file_path || "");
    setPathError(null);
    setIsPathModalOpen(true);
  };

  // Сохранить пути: основная обязательна, пустая запасная выключает режим.
  const applyBookPaths = async () => {
    const main = mainPathInput.trim();
    if (!main) return;
    const reserve = reservePathInput.trim();
    const accepted = await handleSaveBookRoles(main, reserve || null);
    if (!accepted) return;

    // Память путей: запасная сохраняется раньше, основная — последней,
    // поэтому в чипах она окажется первой.
    if (reserve) saveRecentPath(reserve);
    setRecentPaths(saveRecentPath(main));

    setIsPathModalOpen(false);
    setMainPathInput("");
    setReservePathInput("");
  };

  const [now, setNow] = useState(new Date());

  // Обновление текущего времени каждые 10 секунд для актуализации разницы времени
  useEffect(() => {
    const timer = setInterval(() => {
      setNow(new Date());
    }, 10000);
    return () => clearInterval(timer);
  }, []);

  const isDataOutdated = useMemo(() => {
    if (!fileStatus) return false;

    // 1. Если бэкенд возвращает seconds_since_modified (безопасно к таймзонам)
    if (
      fileStatus.seconds_since_modified !== undefined &&
      fileStatus.seconds_since_modified !== null
    ) {
      return fileStatus.seconds_since_modified > 1800; // 30 минут
    }

    // 2. Резервный расчет на клиенте
    if (!fileStatus.last_modified) return false;
    const lastMod = new Date(fileStatus.last_modified).getTime();
    if (isNaN(lastMod)) return false;
    const diffMin = (now.getTime() - lastMod) / (1000 * 60);
    return diffMin > 30;
  }, [fileStatus, now]);

  const renderWarning = () => {
    if (!isDataOutdated) return null;
    return (
      <div className="bg-gradient-to-r from-red-600 via-rose-600 to-red-600 border border-red-500 text-white p-3 rounded-lg flex items-center justify-center gap-3 animate-pulse shadow-md">
        <AlertTriangle className="w-5 h-5 text-white shrink-0 animate-bounce" />
        <div className="text-xs md:text-sm text-center font-medium">
          <strong>Внимание!</strong> Файл не сохранялся более 30 минут. Отображаемые данные могут
          быть неверными! (Последнее сохранение: {formatLastModified(fileStatus?.last_modified)}).
          Настройте сохранение файла либо выберите другую книгу учёта.
        </div>
      </div>
    );
  };

  // Баннер режима запасной книги (ADR 0009). Отдельно от предупреждения об
  // устаревании файла: то про mtime, это про наполненность основной книги.
  const renderStandbyBanner = () => {
    if (fileStatus?.role !== "reserve") return null;
    const growth = growthClock(fileStatus.main_last_growth);

    return (
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-amber-500/60 bg-amber-500/10 px-4 py-2.5 text-sm text-amber-900 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-200">
        <AlertTriangle className="w-4 h-4 shrink-0 text-amber-600 dark:text-amber-400" />
        <span className="font-semibold">Читается запасная книга.</span>
        <span>
          {growth
            ? `Основная не пополняется с ${growth}.`
            : "Основная не пополняется: нет данных о росте."}
        </span>
        {fileStatus.main_file_path && (
          <span
            className="font-mono text-xs text-amber-800/90 dark:text-amber-300/80 truncate max-w-[520px]"
            title={fileStatus.main_file_path}
          >
            {fileStatus.main_file_path}
          </span>
        )}
      </div>
    );
  };

  const hangerMetaByNumber = useMemo(
    () => mergeHangerMeta(data?.products ?? [], matchedEvents ?? []),
    [data?.products, matchedEvents],
  );

  // Выгрузка: события линии, а в режиме симуляции — подвесы, сошедшие с линии по прогону.
  const unloadRows = useMemo<HangerData[]>(() => {
    if (testMode) return testMode === "sim" ? run.unloaded : [];

    return (matchedEvents ?? []).map((event) => ({
      number: String(event.hanger),
      date: event.exit_date,
      time: event.exit_time,
      client: event.client,
      profile: event.profile,
      profiles_info: event.profiles_info,
      color: event.color,
      lamels_qty: event.lamels_qty,
      kpz_number: event.kpz_number,
      material_type: event.material_type,
      entry_date: event.entry_date,
      entry_time: event.entry_time,
      exit_date: event.exit_date,
      exit_time: event.exit_time,
      current_bath: event.current_bath,
      bath_entry_time: event.bath_entry_time,
      bath_processing_time: event.bath_processing_time,
      time_warning: event.time_warning,
      time_warning_code: event.time_warning_code,
      is_defect: event.is_defect,
    }));
  }, [testMode, run.unloaded, matchedEvents]);

  const leaveTestMode = () => {
    setTestMode(null);
    setTestRows([]);
    setTestError(null);
    prevSimLoadingKeyRef.current = "";
    prevSimUnloadKeyRef.current = "";
  };

  const handleToggleLast100 = () => {
    // Тестовые режимы не смешиваются с «последними 100»
    if (testMode) leaveTestMode();

    if (isLast100Mode) {
      // Turn OFF: Restore previous filters
      if (preLast100Filters) {
        setFilters(preLast100Filters);
      }
      setIsLast100Mode(false);
      setPreLast100Filters(null);
    } else {
      // Turn ON: Save current filters and apply "Last 100"
      setPreLast100Filters(filters);
      setFilters({
        ...defaultFilters,
        showLoading: true,
        loadingLimit: 100,
      });
      setIsLast100Mode(true);
    }
  };

  const loadTestRows = async (mode: TestMode) => {
    // Turn off "Last 100" if active
    if (isLast100Mode) {
      setIsLast100Mode(false);
      if (preLast100Filters) setFilters(preLast100Filters);
    }

    setTestError(null);

    try {
      const res = await fetch("/api/catalog/all?limit=1000");
      if (!res.ok) throw new Error("Failed to fetch catalog");
      const profiles: Profile[] = await res.json();

      const rows = buildTestRows(profiles, mode);
      if (rows.length === 0) {
        setTestRows([]);
        setTestMode(null);
        setTestError("В каталоге нет профилей — витрине нечего показывать");
        return;
      }

      setTestRows(rows);
      setTestMode(mode);
    } catch (e) {
      console.error("Error loading catalog for test mode:", e);
      setTestRows([]);
      setTestMode(null);
      setTestError("Каталог не загрузился — витрина недоступна");
    }
  };

  const handleToggleTestMode = async (mode: TestMode) => {
    if (testMode === mode) {
      leaveTestMode();
      return;
    }
    await loadTestRows(mode);
  };

  // Track file changes and auto-refresh
  useEffect(() => {
    if (testMode) return;
    if (fileStatus?.last_modified) {
      const newModified = fileStatus.last_modified;
      if (lastModifiedRef.current && lastModifiedRef.current !== newModified) {
        // File was modified - refetch data
        refetchRecentAll();
        refetch().then((result) => {
          const newData = result.data?.products ?? [];
          const prevData = prevDataRef.current;

          // Deep compare function for rows
          const rowsEqual = (r1: HangerData, r2: HangerData): boolean => {
            return (
              r1.number === r2.number &&
              r1.date === r2.date &&
              r1.time === r2.time &&
              r1.profile === r2.profile &&
              r1.color === r2.color &&
              r1.client === r2.client &&
              r1.kpz_number === r2.kpz_number &&
              r1.material_type === r2.material_type &&
              r1.lamels_qty === r2.lamels_qty
            );
          };

          // Check if there are actual changes in rows
          const hasActualChanges =
            newData.length !== prevData.length ||
            newData.some((newRow, idx) => {
              const prevRow = prevData[idx];
              return !prevRow || !rowsEqual(newRow, prevRow);
            });

          if (hasActualChanges) {
            // Show blue highlight only if there are actual changes
            setHasNewRows(true);
            prevDataRef.current = newData;
            // Auto-hide highlight after 3 seconds
            setTimeout(() => setHasNewRows(false), 3000);
          }
        });
      }
      lastModifiedRef.current = newModified;
    }
  }, [fileStatus?.last_modified, refetch]);

  // Track unload events changes
  useEffect(() => {
    if (testMode) return;
    if (matchedEvents && matchedEvents.length > 0) {
      const prevUnloadData = prevUnloadDataRef.current;

      // Deep compare function for unload events
      const eventsEqual = (e1: any, e2: any): boolean => {
        return (
          e1.hanger === e2.hanger &&
          e1.exit_date === e2.exit_date &&
          e1.exit_time === e2.exit_time &&
          e1.entry_date === e2.entry_date &&
          e1.entry_time === e2.entry_time &&
          e1.profile === e2.profile &&
          e1.color === e2.color &&
          e1.client === e2.client
        );
      };

      // Check if there are actual changes
      const hasActualChanges =
        matchedEvents.length !== prevUnloadData.length ||
        matchedEvents.some((newEvent, idx) => {
          const prevEvent = prevUnloadData[idx];
          return !prevEvent || !eventsEqual(newEvent, prevEvent);
        });

      if (hasActualChanges) {
        setHasNewUnloadEvents(true);
        prevUnloadDataRef.current = matchedEvents;
        // Auto-hide highlight after 3 seconds
        setTimeout(() => setHasNewUnloadEvents(false), 3000);
      }
    }
  }, [matchedEvents]);

  // Очередь загрузки в режиме симуляции: окно фильтра, а не весь круг прогона.
  const simLoadingRows = useMemo(
    () => (testMode === "sim" ? waitingRows(run, filters.loadingLimit) : []),
    [testMode, run, filters.loadingLimit],
  );

  // Таблица загрузки: в симуляции — окно очереди прогона, в «Все профили» и
  // «Все цвета» — весь круг витрины. Потолок «Загрузка» к витрине не
  // относится: назначение этих кнопок — показать всё, иначе половина
  // справочника не попадает на экран.
  const loadingRows = useMemo(() => {
    if (testMode === "sim") return simLoadingRows;
    if (testMode) return testRows;
    return data?.products ?? [];
  }, [testMode, simLoadingRows, testRows, data?.products]);

  const onLineRows = useMemo(() => run.line.map((hanger) => hanger.row), [run]);

  // Боковая очередь — общий список подвесов, как последние строки книги учёта:
  // сверху очередь загрузки, ниже кто стоит на ваннах, ниже кто уже сошёл.
  const sidebarRows = useMemo(() => {
    if (!testMode) return recentAllData?.products;
    if (testMode !== "sim") return [];
    // Очередь загрузки в боковой очереди — без времени: на живой линии прочерк
    // значит «ещё не встал», и витрина показывает то же. В таблице загрузки
    // время остаётся — там витринные строки доигрывают роль строк книги.
    const queued = simLoadingRows.map((row) => ({ ...row, time: "" }));
    return [...queued, ...onLineRows, ...run.unloaded]
      .sort((a, b) => Number(b.number) - Number(a.number))
      .slice(0, SIDEBAR_ROW_LIMIT);
  }, [testMode, simLoadingRows, onLineRows, run.unloaded, recentAllData?.products]);

  // Плашки «Обновление» в режиме симуляции реагируют на прогон, а не на файл Excel.
  // Ключи — состав строк: эффект перезапускается только когда состав действительно
  // изменился, иначе гашение плашки каждый тик сбрасывалось бы.
  // Гашение короче боевого: строка в симуляции приходит каждые 5 секунд, и
  // полутора секунд хватает, чтобы плашка мигнула и не горела постоянно.
  const SIM_BLINK_MS = 1500;
  const simLoadingKey = simLoadingRows.map((row) => row.number).join(",");
  const simUnloadKey = run.unloaded.map((row) => row.number).join(",");

  useEffect(() => {
    if (testMode !== "sim" || simLoadingKey === prevSimLoadingKeyRef.current) return;
    prevSimLoadingKeyRef.current = simLoadingKey;

    setHasNewRows(true);
    setTimeout(() => setHasNewRows(false), SIM_BLINK_MS);
  }, [testMode, simLoadingKey]);

  useEffect(() => {
    if (testMode !== "sim" || simUnloadKey === prevSimUnloadKeyRef.current) return;
    prevSimUnloadKeyRef.current = simUnloadKey;

    setHasNewUnloadEvents(true);
    setTimeout(() => setHasNewUnloadEvents(false), SIM_BLINK_MS);
  }, [testMode, simUnloadKey]);

  // ESC обработчик удален - не закрываем окно по ESC, чтобы работники не могли случайно закрыть киоск

  // Автоматический псевдо-фуллскрин для киоска при загрузке
  useEffect(() => {
    // Проверяем, запущен ли дашборд в окне pywebview (наш киоск)
    // или размеры окна совпадают с экраном
    const isKioskMode =
      (window as any).pywebview ||
      (window.innerHeight === screen.height && window.innerWidth === screen.width);

    if (isKioskMode && !isFullscreen) {
      // Автоматически включаем псевдо-фуллскрин
      setIsFullscreen(true);
    }
  }, []);

  useEffect(() => {
    saveFilters(filters);
  }, [filters]);

  // Автовозврат в fullscreen через 30 секунд
  useEffect(() => {
    // Очищаем предыдущие таймеры
    if (autoReturnTimerRef.current) {
      clearTimeout(autoReturnTimerRef.current);
      autoReturnTimerRef.current = null;
    }
    if (countdownIntervalRef.current) {
      clearInterval(countdownIntervalRef.current);
      countdownIntervalRef.current = null;
    }

    // Если вышли из fullscreen, запускаем таймер
    if (!isFullscreen) {
      setAutoReturnCountdown(30);

      // Обратный отсчет каждую секунду
      countdownIntervalRef.current = setInterval(() => {
        setAutoReturnCountdown((prev) => {
          if (prev === null || prev <= 1) return null;
          return prev - 1;
        });
      }, 1000);

      // Автовозврат через 30 секунд
      autoReturnTimerRef.current = setTimeout(() => {
        setIsFullscreen(true);
        setAutoReturnCountdown(null);
      }, 30000);
    } else {
      setAutoReturnCountdown(null);
    }

    // Cleanup
    return () => {
      if (autoReturnTimerRef.current) {
        clearTimeout(autoReturnTimerRef.current);
      }
      if (countdownIntervalRef.current) {
        clearInterval(countdownIntervalRef.current);
      }
    };
  }, [isFullscreen, setIsFullscreen]);

  const handleCancelAutoReturn = useCallback(() => {
    if (autoReturnTimerRef.current) {
      clearTimeout(autoReturnTimerRef.current);
      autoReturnTimerRef.current = null;
    }
    if (countdownIntervalRef.current) {
      clearInterval(countdownIntervalRef.current);
      countdownIntervalRef.current = null;
    }
    setAutoReturnCountdown(null);
  }, []);

  // Псевдо-фуллскрин: просто переключаем состояние React без браузерного fullscreen API
  const toggleFullscreen = useCallback(() => {
    setIsFullscreen(!isFullscreen);
  }, [isFullscreen, setIsFullscreen]);

  // Обработчик применения фильтров - сбрасывает таймер автовозврата
  const handleApplyFilters = useCallback(() => {
    // Сбрасываем таймер
    handleCancelAutoReturn();

    // Применяем фильтры
    refetch();
    refetchRecentAll();
  }, [refetch, refetchRecentAll, handleCancelAutoReturn]);

  const handlePhotoClick = useCallback((url: string, name: string) => {
    setPhotoModal({ url, name });
  }, []);

  return (
    <div className={`${isFullscreen ? "p-0" : "container mx-auto p-6 space-y-4"}`}>
      {/* Header */}
      {!isFullscreen && (
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">📊 Учет КПЗ - Подвесы</h1>
          <div className="flex items-center gap-4">
            <Badge variant="secondary">Всего: {data?.total_all ?? "—"}</Badge>
            <Badge variant="outline">Показано: {data?.total ?? "—"}</Badge>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                refetch();
                refetchRecentAll();
              }}
              disabled={isFetching || isRecentAllFetching}
            >
              <RefreshCw
                className={`w-4 h-4 mr-2 ${isFetching || isRecentAllFetching ? "animate-spin" : ""}`}
              />
              Обновить
            </Button>
            <Button variant="outline" size="sm" onClick={toggleFullscreen}>
              {isFullscreen ? (
                <Minimize2 className="w-4 h-4 mr-1" />
              ) : (
                <Maximize2 className="w-4 h-4 mr-1" />
              )}
              {isFullscreen ? "Свернуть" : "На весь экран"}
            </Button>
          </div>
        </div>
      )}

      {isFullscreen && (
        <div className="fixed top-2 right-2 z-50">
          <Button variant="secondary" size="sm" onClick={toggleFullscreen}>
            <X className="w-4 h-4 mr-1" /> Выход
          </Button>
        </div>
      )}

      {/* Уведомление об автовозврате в fullscreen */}
      {!isFullscreen && autoReturnCountdown !== null && (
        <div className="fixed top-4 left-1/2 transform -translate-x-1/2 z-50">
          <Card className="bg-orange-500 border-orange-600 shadow-lg relative pr-10">
            <CardContent className="py-3 pl-6 pr-2">
              <div className="flex items-center gap-3 text-white">
                <div className="text-2xl font-bold">{autoReturnCountdown}</div>
                <div className="text-sm">
                  <div className="font-semibold">Автовозврат в полноэкранный режим</div>
                  <div className="text-xs opacity-90">Нажмите "Применить" чтобы остаться</div>
                </div>
              </div>
            </CardContent>
            <button
              onClick={handleCancelAutoReturn}
              className="absolute top-1/2 right-3 transform -translate-y-1/2 text-white/80 hover:text-white transition-colors"
              aria-label="Закрыть"
            >
              <X className="w-5 h-5" />
            </button>
          </Card>
        </div>
      )}

      {!isFullscreen && <StatusBar onOpenPathModal={openPathModal} />}

      {renderStandbyBanner()}

      {!isFullscreen && (
        <FiltersPanel
          filters={filters}
          onChange={setFilters}
          onApply={handleApplyFilters}
          onReset={() => setFilters(defaultFilters)}
          onToggleLast100={handleToggleLast100}
          isLast100Mode={isLast100Mode}
          onToggleTestMode={handleToggleTestMode}
          testMode={testMode}
          testError={testError}
        />
      )}

      <div
        className={`grid ${isFullscreen ? "grid-cols-5" : "grid-cols-1 xl:grid-cols-5"} gap-4 items-start relative`}
      >
        <div className={`${isFullscreen ? "col-span-4 space-y-4" : "xl:col-span-4 space-y-4"}`}>
          {filters.showLoading && (
            <div className="flex flex-col gap-0">
              {renderWarning()}
              <Card
                className={`border-8 relative ${testMode && testMode !== "sim" ? TEST_FRAME : "border-blue-500"}`}
              >
                {testMode === "sim" && (
                  <span className="absolute -top-3 right-3 z-50 rounded-full bg-purple-600 px-3 py-0.5 text-xs font-bold text-white shadow">
                    СИМУЛЯЦИЯ
                  </span>
                )}
                {hasNewRows && testMode !== "catalog" && testMode !== "colors" && (
                  <div className="absolute inset-0 bg-blue-500 z-50 rounded-md flex items-center justify-center">
                    <span className="text-white text-3xl font-bold">Обновление</span>
                  </div>
                )}
                <CardContent className="p-0">
                  {isLoading && !testMode ? (
                    <TableSkeleton />
                  ) : loadingRows?.length ? (
                    <DataTable
                      data={loadingRows}
                      onPhotoClick={handlePhotoClick}
                      isFullscreen={isFullscreen}
                      ariaLabel="Очередь загрузки"
                    />
                  ) : (
                    <div className="flex flex-col items-center justify-center py-8 text-center">
                      <Inbox className="w-8 h-8 text-muted-foreground/30 mb-2" />
                      <span className="text-sm text-muted-foreground">Очередь загрузки пуста</span>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          )}

          {filters.showRealtime && (
            <>
              {console.log("[Dashboard] matchedEvents:", matchedEvents)}
              {matchedEvents && matchedEvents.length > 0 && (
                <>
                  {console.log("[Dashboard] First event:", matchedEvents[0])}
                  {console.log("[Dashboard] Rendering table with", matchedEvents.length, "events")}
                </>
              )}

              {/* Forecast Row - Outside the green border */}
              {filters.showForecast && (
                <BathForecast
                  hangerMetaByNumber={hangerMetaByNumber}
                  testRun={testMode ? (testMode === "sim" ? run : EMPTY_RUN) : undefined}
                />
              )}

              <div className="flex flex-col gap-0">
                {renderWarning()}
                <Card
                  className={`border-8 relative ${testMode && testMode !== "sim" ? TEST_FRAME : "border-green-500"}`}
                >
                  {testMode === "sim" && (
                    <span className="absolute -top-3 right-3 z-50 rounded-full bg-purple-600 px-3 py-0.5 text-xs font-bold text-white shadow">
                      СИМУЛЯЦИЯ
                    </span>
                  )}
                  {hasNewUnloadEvents && testMode !== "catalog" && testMode !== "colors" && (
                    <div className="absolute inset-0 bg-green-500 z-50 rounded-md flex items-center justify-center">
                      <span className="text-white text-3xl font-bold">Обновление</span>
                    </div>
                  )}
                  <CardContent className="p-0">
                    {unloadRows.length > 0 ? (
                      <DataTable
                        data={unloadRows}
                        onPhotoClick={handlePhotoClick}
                        isFullscreen={isFullscreen}
                        showEntryExit
                        ariaLabel="Выгрузка"
                      />
                    ) : (
                      <div className="flex flex-col items-center justify-center py-8 text-center">
                        <Inbox className="w-8 h-8 text-muted-foreground/30 mb-2" />
                        <span className="text-sm text-muted-foreground">Нет событий выгрузки</span>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
            </>
          )}
        </div>

        <div className={`${isFullscreen ? "col-span-1" : "xl:col-span-1"} w-full`}>
          <SidebarQueueTable
            data={sidebarRows}
            isLoading={testMode ? false : isLoadingAll}
            isFullscreen={isFullscreen}
          />
        </div>
      </div>

      <PhotoModal
        open={!!photoModal}
        onClose={() => setPhotoModal(null)}
        photoUrl={photoModal?.url || null}
        profileName={photoModal?.name || ""}
      />

      <Dialog
        open={isPathModalOpen}
        onOpenChange={(open) => {
          if (!open) {
            setIsPathModalOpen(false);
            setMainPathInput("");
            setReservePathInput("");
            setPathError(null);
          }
        }}
      >
        <DialogContent className="max-w-2xl gap-0 overflow-hidden border-border bg-background p-0 text-foreground shadow-2xl">
          <DialogHeader className="space-y-1.5 px-6 pb-3 pt-6">
            <DialogTitle className="flex items-center gap-2 text-xl font-bold text-emerald-600">
              <FileSpreadsheet className="h-5 w-5" />
              Книги учёта
            </DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              Две книги: основная и запасная. Нажмите на путь, чтобы изменить его на месте.
            </DialogDescription>
          </DialogHeader>

          <div className="px-6">
            <div className="rounded-md border bg-muted/40 px-3 py-2 text-[11px]">
              <span className="text-muted-foreground">Читается сейчас: </span>
              <span className="font-medium text-slate-800 dark:text-slate-200">
                {fileStatus?.role === "reserve"
                  ? `запасная — основная не пополняется${
                      growthClock(fileStatus?.main_last_growth)
                        ? ` с ${growthClock(fileStatus?.main_last_growth)}`
                        : ""
                    }`
                  : fileStatus?.role === "main"
                    ? "основная — строки растут"
                    : "режим запасной выключен"}
              </span>
            </div>
          </div>

          <div className="grid gap-3 px-6 py-4 md:grid-cols-2">
            <section className="rounded-lg border border-emerald-500/50 p-3">
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-slate-800 dark:text-slate-200">
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                Основная книга
              </div>
              <ClickableBookPath
                value={mainPathInput}
                onChange={setMainPathInput}
                tone="main"
                placeholder="Нажмите, чтобы указать основную книгу"
              />
              <RecentPathChips
                paths={recentPaths}
                active={mainPathInput}
                tone="main"
                onPick={setMainPathInput}
              />
              <p className="mt-2 text-[10px] text-muted-foreground">
                Без основной книги сохранить нельзя.
              </p>
            </section>

            <section className="rounded-lg border border-amber-500/50 p-3">
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-slate-800 dark:text-slate-200">
                <span className="h-2 w-2 rounded-full bg-amber-500" />
                Запасная книга
              </div>
              <ClickableBookPath
                value={reservePathInput}
                onChange={setReservePathInput}
                tone="reserve"
                placeholder="Пусто — режим выключен"
              />
              <RecentPathChips
                paths={recentPaths}
                active={reservePathInput}
                tone="reserve"
                onPick={setReservePathInput}
              />
              <p className="mt-2 text-[10px] text-muted-foreground">
                Пустое поле выключает режим. Система перейдёт на запасную, если основная перестанет
                пополняться.
              </p>
            </section>
          </div>

          {pathError && (
            <div className="mx-6 flex items-start gap-2 rounded border border-red-300 bg-red-50 px-2 py-1.5 text-[11px] text-red-700 dark:border-red-500/40 dark:bg-red-500/10 dark:text-red-300">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span className="break-all">{pathError}</span>
            </div>
          )}

          <div className="mt-3 flex items-center justify-between gap-3 border-t px-6 py-3">
            <span className="truncate text-[11px] text-muted-foreground">
              {reservePathInput.trim()
                ? `запасная: ${pathHint(reservePathInput.trim())}`
                : "режим запасной выключен"}
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setIsPathModalOpen(false);
                  setMainPathInput("");
                  setReservePathInput("");
                  setPathError(null);
                }}
                className="h-9 text-xs"
              >
                <X className="mr-1 h-4 w-4" /> Отмена
              </Button>
              <Button
                onClick={applyBookPaths}
                disabled={isFetching || !mainPathInput.trim()}
                className="h-9 bg-emerald-600 px-5 text-sm font-semibold text-white hover:bg-emerald-700"
              >
                Сохранить
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Фиксированные часы в правом нижнем углу */}
      <div className="fixed bottom-4 right-4 z-50 bg-background/95 dark:bg-slate-900/95 backdrop-blur-sm border border-slate-200 dark:border-slate-800 rounded-lg px-4 py-2 shadow-lg flex items-center gap-2">
        <Clock className="w-5 h-5 text-slate-500" />
        <span className="font-mono text-2xl font-bold text-foreground tracking-wider">
          <ClockInline />
        </span>
      </div>
    </div>
  );
}
