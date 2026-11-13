/**
 * Фото артикула в буфер обмена и в файл.
 *
 * Копирование идёт двумя путями. В secure context (`https` или `localhost`)
 * работает `navigator.clipboard.write` с PNG-блобом. Стенд в локальной сети
 * открыт по HTTP — там Clipboard API нет, поэтому остаётся
 * `document.execCommand("copy")` по выделенной картинке: тот же путь, которым
 * ходит браузерное «Копировать изображение» из контекстного меню.
 */

const MIME_EXTENSIONS: Record<string, string> = {
  "image/png": "png",
  "image/jpeg": "jpg",
  "image/webp": "webp",
  "image/gif": "gif",
  "image/bmp": "bmp",
};

/** Последний сегмент URL без строки запроса: `/static/images/035.png?v=1` → `035.png`. */
function sourceFileName(src: string): string | null {
  const path = src.split("?")[0].split("#")[0];
  const segment = path.split("/").pop() ?? "";
  try {
    return decodeURIComponent(segment) || null;
  } catch {
    return segment || null;
  }
}

function extensionFor(src: string, blob: Blob): string {
  const match = /\.([a-z0-9]{2,5})$/i.exec(sourceFileName(src) ?? "");
  if (match) return match[1].toLowerCase();
  return MIME_EXTENSIONS[blob.type] ?? "png";
}

/** Запрещённые в именах файлов Windows символы. */
const FORBIDDEN_FILE_CHARS = '\\/:*?"<>|';

function sanitizeArticle(article: string): string {
  return [...article]
    .map((char) => (char.charCodeAt(0) < 32 || FORBIDDEN_FILE_CHARS.includes(char) ? "_" : char))
    .join("")
    .replace(/\s+/g, " ")
    .replace(/[. ]+$/, "")
    .trim();
}

/**
 * Имя файла — артикул: оператор ищет файл по нему, а не по имени картинки на
 * сервере. Запрещённые в Windows символы заменяются, пустой артикул
 * откатывается к имени исходника.
 */
function photoFileName(article: string, src: string, blob: Blob): string {
  const safe = sanitizeArticle(article);
  const base = safe || (sourceFileName(src) ?? "photo").replace(/\.[^.]+$/, "");
  return `${base}.${extensionFor(src, blob)}`;
}

async function fetchPhotoBlob(src: string): Promise<Blob> {
  const response = await fetch(src);
  if (!response.ok) {
    throw new Error(`Не удалось получить фото: ${response.status}`);
  }
  return response.blob();
}

function saveBlobAsFile(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Отзыв сразу после click: файл уже отдан браузеру, а blob-URL не течёт.
  URL.revokeObjectURL(url);
}

/** Скачать фото под именем артикула. Возвращает имя файла для сообщения. */
export async function downloadPhoto(src: string, article: string): Promise<string> {
  const blob = await fetchPhotoBlob(src);
  const fileName = photoFileName(article, src, blob);
  saveBlobAsFile(blob, fileName);
  return fileName;
}

async function toPng(blob: Blob): Promise<Blob> {
  if (blob.type === "image/png") return blob;
  const bitmap = await createImageBitmap(blob);
  try {
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Не удалось подготовить изображение");
    context.drawImage(bitmap, 0, 0);
    return await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob(
        (png) => (png ? resolve(png) : reject(new Error("Не удалось подготовить изображение"))),
        "image/png",
      );
    });
  } finally {
    bitmap.close();
  }
}

function clipboardSupports(type: string): boolean {
  if (typeof ClipboardItem !== "undefined" && typeof ClipboardItem.supports === "function") {
    return ClipboardItem.supports(type);
  }
  // Без `ClipboardItem.supports` браузеры (Chromium) принимают только PNG.
  return type === "image/png";
}

async function copyViaClipboardApi(blob: Blob): Promise<boolean> {
  if (typeof ClipboardItem === "undefined" || !navigator.clipboard?.write) return false;
  try {
    const clipboardBlob = clipboardSupports(blob.type) ? blob : await toPng(blob);
    await navigator.clipboard.write([new ClipboardItem({ [clipboardBlob.type]: clipboardBlob })]);
    return true;
  } catch {
    return false;
  }
}

/**
 * Запасной путь для HTTP: выделить картинку и отдать `execCommand("copy")`.
 * В просмотрщике стоит `select-none`, поэтому на время выделения оно снимается
 * с самой картинки; если элемента под рукой нет, картинка грузится во
 * временный узел.
 */
async function copyViaSelection(src: string, image?: HTMLImageElement | null): Promise<boolean> {
  let target: HTMLImageElement;
  let holder: HTMLDivElement | null = null;

  if (image?.isConnected) {
    target = image;
  } else {
    holder = document.createElement("div");
    holder.setAttribute("aria-hidden", "true");
    holder.style.cssText = "position:fixed;left:-10000px;top:0;user-select:text;";
    target = document.createElement("img");
    target.src = src;
    holder.appendChild(target);
    document.body.appendChild(holder);
    if (typeof target.decode === "function") {
      await target.decode().catch(() => {});
    }
  }

  const previousUserSelect = target.style.userSelect;
  target.style.userSelect = "text";
  try {
    const selection = window.getSelection();
    if (!selection) return false;
    const range = document.createRange();
    range.selectNode(target);
    selection.removeAllRanges();
    selection.addRange(range);
    try {
      return document.execCommand("copy");
    } finally {
      selection.removeAllRanges();
    }
  } catch {
    return false;
  } finally {
    target.style.userSelect = previousUserSelect;
    holder?.remove();
  }
}

/**
 * Скопировать фото в буфер обмена. Бросает исключение, если браузер не дал
 * ни один из путей, — вызывающий показывает пользователю причину.
 *
 * `image` — уже показанная картинка: по ней работает запасной путь через
 * выделение, и она точно отрисована внутри просмотрщика.
 */
export async function copyPhoto(src: string, image?: HTMLImageElement | null): Promise<void> {
  const blob = await fetchPhotoBlob(src);
  if (await copyViaClipboardApi(blob)) return;
  if (await copyViaSelection(src, image)) return;
  throw new Error("Браузер не разрешил скопировать изображение");
}
