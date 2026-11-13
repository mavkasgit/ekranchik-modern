import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  Search,
  Image as ImageIcon,
  X,
  Grid,
  List,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Check,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useToast } from "@/hooks/use-toast";
import { useCatalogAll, useUpdateNotes } from "@/hooks/useCatalog";
import type { Profile } from "@/types/profile";
import { photoUrl } from "@/lib/domain/photo";
import {
  activeFilterCount,
  EMPTY_FILTERS,
  lengthOptions,
  matchesFilters,
  matchesQuery,
  parseStoredFilters,
  parseStoredSort,
  serializeFilters,
  sortProfiles,
  toggleSort,
  type CatalogFilters,
  type CatalogSort,
  type SortDirection,
  type SortField,
} from "@/lib/domain/catalogView";
import { ALL_FILTER_FIELDS, CatalogFilterChips, FilterPopover } from "@/components/CatalogFilters";

type ViewMode = "grid" | "table";

// Ключи с префиксом каталога: режим, сортировка и фильтры переживают
// перезагрузку киоска. Старые записи (два ключа сортировки) читаются.
const STORAGE_KEYS = {
  viewMode: "catalog_view_mode",
  sort: "catalog_sort",
  filters: "catalog_filters",
};

const LEGACY_SORT_KEYS = {
  field: "catalog_sort_field",
  direction: "catalog_sort_direction",
};

const SORT_LABELS: Record<SortField, string> = {
  name: "Артикул",
  description: "Наименование",
  quantity_per_hanger: "Количество",
  length: "Длина",
  notes: "Примечания",
  updated_at: "Изменён",
  has_photo: "Фото",
};

const SORT_FIELD_ORDER: SortField[] = [
  "name",
  "description",
  "quantity_per_hanger",
  "length",
  "notes",
  "updated_at",
  "has_photo",
];

function readViewMode(): ViewMode {
  return localStorage.getItem(STORAGE_KEYS.viewMode) === "table" ? "table" : "grid";
}

function readSort(): CatalogSort {
  const stored = localStorage.getItem(STORAGE_KEYS.sort);
  if (stored) return parseStoredSort(stored);

  const field = localStorage.getItem(LEGACY_SORT_KEYS.field);
  const direction = localStorage.getItem(LEGACY_SORT_KEYS.direction);
  if (field || direction) return parseStoredSort(JSON.stringify({ field, direction }));

  return parseStoredSort(null);
}

function readFilters(): CatalogFilters {
  return parseStoredFilters(localStorage.getItem(STORAGE_KEYS.filters));
}

/** Счётчик в заголовке: «1 артикул», «2 артикула», «5 артикулов». */
function articlesLabel(count: number): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return "артикул";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "артикула";
  return "артикулов";
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString("ru");
}

function SortIcon({ active, direction }: { active: boolean; direction: SortDirection }) {
  if (!active) return <ArrowUpDown className="ml-1 h-3.5 w-3.5 opacity-50" />;
  return direction === "asc" ? (
    <ArrowUp className="ml-1 h-3.5 w-3.5" />
  ) : (
    <ArrowDown className="ml-1 h-3.5 w-3.5" />
  );
}

/**
 * Заголовок колонки таблицы: клик по названию сортирует, кнопка фильтра
 * открывает поповер этой колонки.
 */
function SortableHead({
  label,
  field,
  sort,
  onSort,
  className,
  children,
}: {
  label: string;
  field: SortField;
  sort: CatalogSort;
  onSort: (field: SortField) => void;
  className?: string;
  children?: ReactNode;
}) {
  return (
    <TableHead className={className}>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => onSort(field)}
          className="flex items-center rounded-sm hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          title={`Сортировать: ${label}`}
        >
          {label}
          <SortIcon active={sort.field === field} direction={sort.direction} />
        </button>
        {children}
      </div>
    </TableHead>
  );
}

/** Плитка витрины: фото, артикул, наименование, бейджи и примечание. */
function ProfileCard({
  profile,
  onSelect,
}: {
  profile: Profile;
  onSelect: (profile: Profile) => void;
}) {
  const photoSrc = photoUrl(profile.photo_thumb, profile.photo_thumb_version);

  return (
    <Card
      className="cursor-pointer transition-shadow hover:shadow-md"
      onClick={() => onSelect(profile)}
    >
      <CardContent className="flex gap-3 p-3 md:gap-4 md:p-4">
        <div className="flex h-20 w-20 flex-shrink-0 items-center justify-center overflow-hidden rounded-md bg-muted">
          {photoSrc ? (
            <img
              src={photoSrc}
              alt={profile.name}
              loading="lazy"
              decoding="async"
              className="max-h-full max-w-full object-contain"
            />
          ) : (
            <ImageIcon className="h-8 w-8 text-muted-foreground" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted-foreground">Артикул</p>
          <h3 className="truncate font-medium">{profile.name}</h3>
          {profile.description && (
            <p className="truncate text-sm text-muted-foreground">{profile.description}</p>
          )}
          <div className="mt-1 flex flex-wrap gap-2">
            {profile.quantity_per_hanger !== null && (
              <Badge variant="secondary">{profile.quantity_per_hanger} шт/подв</Badge>
            )}
            {profile.length !== null && <Badge variant="outline">{profile.length} мм</Badge>}
          </div>
          {profile.notes && (
            <p className="mt-2 line-clamp-2 text-xs text-muted-foreground">{profile.notes}</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Карточка артикула: данные показываются текстом, редактируется только
 * примечание — автосохранение по потере фокуса, без кнопки «Сохранить».
 */
function ProfileDialog({ profile, onClose }: { profile: Profile; onClose: () => void }) {
  const { toast } = useToast();
  const updateNotes = useUpdateNotes();
  const [notes, setNotes] = useState(profile.notes ?? "");
  const [photoOpen, setPhotoOpen] = useState(false);
  const photoSrc =
    photoUrl(profile.photo_full, profile.photo_full_version) ??
    photoUrl(profile.photo_thumb, profile.photo_thumb_version);

  const saveNotes = async () => {
    const saved = profile.notes ?? "";
    if (notes === saved) return;

    try {
      await updateNotes.mutateAsync({ id: profile.id, notes });
      toast({ title: "Сохранено" });
    } catch {
      setNotes(saved);
      toast({ title: "Не удалось сохранить", variant: "destructive" });
    }
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        className="max-md:left-0 max-md:top-0 max-md:h-dvh max-md:max-h-none max-md:w-screen max-md:max-w-none max-md:translate-x-0 max-md:translate-y-0 max-md:rounded-none max-md:border-0 gap-0 p-0 md:h-[min(90vh,42rem)] md:max-w-4xl"
        onOpenAutoFocus={(event) => event.preventDefault()}
      >
        <DialogHeader className="sr-only">
          <DialogTitle>{profile.name}</DialogTitle>
          <DialogDescription>Карточка артикула</DialogDescription>
        </DialogHeader>

        <div className="flex h-full flex-col md:flex-row">
          {/* Фото: слева на десктопе, сверху на телефоне */}
          <div className="flex flex-shrink-0 items-center justify-center bg-muted p-2 max-md:h-[45dvh] md:min-w-0 md:flex-1 md:p-4">
            {photoSrc ? (
              <button
                type="button"
                onClick={() => setPhotoOpen(true)}
                className="flex h-full w-full cursor-zoom-in items-center justify-center"
                title="Открыть фото"
              >
                <img
                  src={photoSrc}
                  alt={profile.name}
                  loading="lazy"
                  decoding="async"
                  className="max-h-full max-w-full object-contain"
                />
              </button>
            ) : (
              <div className="flex flex-col items-center justify-center text-muted-foreground">
                <ImageIcon className="mb-2 h-12 w-12" />
                <p>Нет фото</p>
              </div>
            )}
          </div>

          {/* Данные и примечание: справа на десктопе, снизу на телефоне */}
          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4 md:w-80 md:flex-none md:border-l">
            <dl className="space-y-3 text-sm">
              <div>
                <dt className="text-muted-foreground">Артикул</dt>
                <dd className="font-medium">{profile.name}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Наименование</dt>
                <dd>{profile.description ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Длина</dt>
                <dd>{profile.length !== null ? `${profile.length} мм` : "—"}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Количество на подвесе</dt>
                <dd>{profile.quantity_per_hanger ?? "—"}</dd>
              </div>
            </dl>

            <div className="mt-4 border-t pt-4">
              <Label htmlFor="catalog-notes">Примечания</Label>
              <Textarea
                id="catalog-notes"
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                onBlur={saveNotes}
                placeholder="Дополнительная информация..."
                rows={4}
                className="mt-2"
              />
              <p className="mt-1 text-xs text-muted-foreground">
                Сохраняется автоматически при потере фокуса
              </p>
            </div>
          </div>
        </div>
      </DialogContent>

      {/* Полное фото: вписывается в экран, 0018 заменит это на просмотрщик */}
      <Dialog open={photoOpen} onOpenChange={setPhotoOpen}>
        <DialogContent className="max-h-[95dvh] w-auto max-w-[95vw] gap-0 border-0 bg-black p-0">
          <DialogHeader className="sr-only">
            <DialogTitle>{profile.name}</DialogTitle>
            <DialogDescription>Фото артикула</DialogDescription>
          </DialogHeader>
          {photoSrc && (
            <img
              src={photoSrc}
              alt={profile.name}
              className="max-h-[92dvh] max-w-[95vw] object-contain"
            />
          )}
        </DialogContent>
      </Dialog>
    </Dialog>
  );
}

function CatalogSkeleton() {
  return (
    <div className="grid gap-3 md:grid-cols-2 md:gap-4 lg:grid-cols-3">
      {[...Array(6)].map((_, index) => (
        <Card key={index}>
          <CardContent className="flex gap-4 p-4">
            <Skeleton className="h-20 w-20 rounded-md" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-5 w-3/4" />
              <Skeleton className="h-4 w-1/2" />
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export default function Catalog() {
  // Поиск клиентский: 200 мс после последнего нажатия, без сетевых запросов.
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const queryTimer = useRef<number | undefined>(undefined);

  const [viewMode, setViewMode] = useState<ViewMode>(readViewMode);
  const [sort, setSort] = useState<CatalogSort>(readSort);
  const [filters, setFilters] = useState<CatalogFilters>(readFilters);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const { data: profiles, isLoading, isError, isFetching, refetch } = useCatalogAll();

  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.viewMode, viewMode);
  }, [viewMode]);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.sort, JSON.stringify(sort));
  }, [sort]);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.filters, serializeFilters(filters));
  }, [filters]);

  useEffect(() => () => window.clearTimeout(queryTimer.current), []);

  const changeQuery = (value: string) => {
    setQueryInput(value);
    window.clearTimeout(queryTimer.current);
    queryTimer.current = window.setTimeout(() => setQuery(value), 200);
  };

  const updateFilters = (patch: Partial<CatalogFilters>) => {
    setFilters((current) => ({ ...current, ...patch }));
  };

  const resetFilters = () => setFilters(EMPTY_FILTERS);

  const displayData = useMemo(() => {
    const matched = (profiles ?? []).filter(
      (profile) => matchesQuery(profile, query) && matchesFilters(profile, filters),
    );
    return sortProfiles(matched, sort);
  }, [profiles, query, filters, sort]);

  const lengths = useMemo(() => lengthOptions(profiles ?? []), [profiles]);
  const filterCount = activeFilterCount(filters);
  const hasSearch = query.trim() !== "";

  const selectedProfile = profiles?.find((profile) => profile.id === selectedId) ?? null;

  const handleSort = (field: SortField) => setSort((current) => toggleSort(current, field));

  return (
    <div className="container mx-auto max-w-6xl p-4 md:p-6">
      <div className="mb-4 md:mb-6">
        <div className="mb-4 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 md:gap-4">
            <h1 className="text-xl font-bold md:text-2xl">Каталог артикулов</h1>
            {!isLoading && !isError && (
              <Badge variant="secondary" className="hidden sm:inline-flex">
                {displayData.length} {articlesLabel(displayData.length)}
              </Badge>
            )}
          </div>
          <div className="hidden items-center gap-2 md:flex">
            <Button
              variant="outline"
              size="icon"
              onClick={() => setViewMode("grid")}
              className={viewMode === "grid" ? "bg-accent" : ""}
              title="Плитка"
            >
              <Grid className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              onClick={() => setViewMode("table")}
              className={viewMode === "table" ? "bg-accent" : ""}
              title="Таблица"
            >
              <List className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 md:flex-nowrap md:gap-4">
          <div className="relative min-w-0 flex-1 basis-full md:basis-auto">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Поиск по артикулу, наименованию и примечанию..."
              value={queryInput}
              onChange={(event) => changeQuery(event.target.value)}
              className="pl-10 pr-10"
            />
            {queryInput && (
              <Button
                variant="ghost"
                size="sm"
                className="absolute right-1 top-1/2 h-7 w-7 -translate-y-1/2 p-0"
                onClick={() => changeQuery("")}
                title="Очистить поиск"
              >
                <X className="h-4 w-4" />
              </Button>
            )}
          </div>

          {/* В таблице фильтры открываются из заголовков колонок; кнопка нужна
              плитке, а на телефоне плитка — единственный режим. */}
          <div className={viewMode === "table" ? "md:hidden" : undefined}>
            <FilterPopover
              label="Фильтры"
              fields={ALL_FILTER_FIELDS}
              filters={filters}
              lengths={lengths}
              onChange={updateFilters}
              onReset={resetFilters}
            />
          </div>

          <div className="flex">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" className="rounded-r-none border-r-0">
                  <ArrowUpDown className="h-4 w-4 md:mr-2" />
                  <span className="hidden md:inline">Сортировка</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {SORT_FIELD_ORDER.map((field) => (
                  <DropdownMenuItem key={field} onClick={() => handleSort(field)}>
                    <Check
                      className={`mr-2 h-4 w-4 ${sort.field === field ? "opacity-100" : "opacity-0"}`}
                    />
                    {SORT_LABELS[field]}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
            <Button
              variant="outline"
              size="icon"
              className="rounded-l-none"
              onClick={() =>
                setSort((current) => ({
                  ...current,
                  direction: current.direction === "asc" ? "desc" : "asc",
                }))
              }
              title={sort.direction === "asc" ? "По возрастанию" : "По убыванию"}
            >
              {sort.direction === "asc" ? (
                <ArrowUp className="h-4 w-4" />
              ) : (
                <ArrowDown className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>

        {filterCount > 0 && (
          <div className="mt-3">
            <CatalogFilterChips filters={filters} onChange={updateFilters} onReset={resetFilters} />
          </div>
        )}
      </div>

      {isLoading && <CatalogSkeleton />}

      {!isLoading && isError && (
        <div className="py-12 text-center text-muted-foreground">
          <p className="mb-4">Не удалось загрузить каталог</p>
          <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
            Повторить
          </Button>
        </div>
      )}

      {!isLoading && !isError && displayData.length === 0 && (
        <div className="py-12 text-center text-muted-foreground">
          <Search className="mx-auto mb-4 h-12 w-12 opacity-50" />
          <p>{hasSearch || filterCount > 0 ? "Ничего не найдено" : "Каталог пуст"}</p>
        </div>
      )}

      {!isLoading && !isError && displayData.length > 0 && (
        <>
          <div
            className={`grid grid-cols-1 gap-3 sm:grid-cols-2 md:gap-4 lg:grid-cols-3 ${
              viewMode === "table" ? "md:hidden" : ""
            }`}
          >
            {displayData.map((profile) => (
              <ProfileCard
                key={profile.id}
                profile={profile}
                onSelect={() => setSelectedId(profile.id)}
              />
            ))}
          </div>

          {viewMode === "table" && (
            <div className="hidden rounded-lg border md:block">
              <Table>
                <TableHeader>
                  <TableRow>
                    <SortableHead
                      label="Фото"
                      field="has_photo"
                      sort={sort}
                      onSort={handleSort}
                      className="w-24"
                    >
                      <FilterPopover
                        fields={["has_photo"]}
                        filters={filters}
                        lengths={lengths}
                        onChange={updateFilters}
                        onReset={resetFilters}
                      />
                    </SortableHead>
                    <SortableHead label="Артикул" field="name" sort={sort} onSort={handleSort}>
                      <FilterPopover
                        fields={["name"]}
                        filters={filters}
                        lengths={lengths}
                        onChange={updateFilters}
                        onReset={resetFilters}
                      />
                    </SortableHead>
                    <SortableHead
                      label="Наименование"
                      field="description"
                      sort={sort}
                      onSort={handleSort}
                    >
                      <FilterPopover
                        fields={["description"]}
                        filters={filters}
                        lengths={lengths}
                        onChange={updateFilters}
                        onReset={resetFilters}
                      />
                    </SortableHead>
                    <SortableHead
                      label="Кол-во"
                      field="quantity_per_hanger"
                      sort={sort}
                      onSort={handleSort}
                    >
                      <FilterPopover
                        fields={["quantity"]}
                        filters={filters}
                        lengths={lengths}
                        onChange={updateFilters}
                        onReset={resetFilters}
                      />
                    </SortableHead>
                    <SortableHead label="Длина" field="length" sort={sort} onSort={handleSort}>
                      <FilterPopover
                        fields={["length"]}
                        filters={filters}
                        lengths={lengths}
                        onChange={updateFilters}
                        onReset={resetFilters}
                      />
                    </SortableHead>
                    <SortableHead label="Примечания" field="notes" sort={sort} onSort={handleSort}>
                      <FilterPopover
                        fields={["notes"]}
                        filters={filters}
                        lengths={lengths}
                        onChange={updateFilters}
                        onReset={resetFilters}
                      />
                    </SortableHead>
                    <SortableHead
                      label="Изменён"
                      field="updated_at"
                      sort={sort}
                      onSort={handleSort}
                    >
                      <FilterPopover
                        fields={["updated_at"]}
                        filters={filters}
                        lengths={lengths}
                        onChange={updateFilters}
                        onReset={resetFilters}
                      />
                    </SortableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {displayData.map((profile) => (
                    <TableRow
                      key={profile.id}
                      className="cursor-pointer"
                      onClick={() => setSelectedId(profile.id)}
                    >
                      <TableCell>
                        <div className="flex h-10 w-10 items-center justify-center overflow-hidden rounded bg-muted">
                          {profile.photo_thumb ? (
                            <img
                              src={photoUrl(profile.photo_thumb, profile.photo_thumb_version)!}
                              alt={profile.name}
                              loading="lazy"
                              decoding="async"
                              className="h-full w-full object-cover"
                            />
                          ) : (
                            <ImageIcon className="h-4 w-4 text-muted-foreground" />
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="font-medium">{profile.name}</TableCell>
                      <TableCell className="max-w-xs truncate">
                        {profile.description ?? "—"}
                      </TableCell>
                      <TableCell>{profile.quantity_per_hanger ?? "—"}</TableCell>
                      <TableCell>
                        {profile.length !== null ? `${profile.length} мм` : "—"}
                      </TableCell>
                      <TableCell className="max-w-xs truncate">{profile.notes ?? "—"}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {formatDate(profile.updated_at)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </>
      )}

      {selectedProfile && (
        <ProfileDialog
          key={selectedProfile.id}
          profile={selectedProfile}
          onClose={() => setSelectedId(null)}
        />
      )}
    </div>
  );
}
