// Свой хук фуллскрина вместо `useFullscreen` из `@siberiacancode/reactuse`.
//
// Пакетный хук (1.0.20) не отдаёт промис из `enter()` и `exit()`: отказ браузера
// (`NotAllowedError` после потери user gesture) некуда показать, а `exit()`
// выходит из любого фуллскрина, а не только из своего. Здесь `enter()`/`exit()`/
// `toggle()` возвращают промисы, ошибка уходит в `onError` и пробрасывается
// дальше, а выход адресный — только для своего элемента.
//
// Апстрим: https://github.com/siberiacancode/reactuse/issues/516
// Когда хук пакета научится этому — заменить на него и удалить этот файл.

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type RefCallback,
} from "react";

interface FullscreenElementOptions {
  /** Браузер вошёл в фуллскрин нашего элемента. */
  onEnter?: () => void;
  /** Браузер вышел из фуллскрина (Esc, F11, закрытие вкладки). */
  onExit?: () => void;
  /** `enter()`/`exit()`/`toggle()` получили отказ — например, без user gesture. */
  onError?: (error: unknown) => void;
}

/** Webkit-префиксы Fullscreen API: Safari и старые сборки Chromium. */
interface WebkitFullscreenElement extends Element {
  webkitRequestFullscreen?: () => Promise<void> | void;
}

interface WebkitFullscreenDocument extends Document {
  webkitFullscreenElement?: Element | null;
  webkitExitFullscreen?: () => Promise<void> | void;
}

interface FullscreenElementHandle<T extends Element> {
  /**
   * Callback-ref, а не `useRef`: Radix монтирует портал после первого эффекта,
   * и только рендер по появлению узла включает подписку и запрос.
   */
  ref: RefCallback<T>;
  /** Смонтированный узел — чтобы обработчики читали актуальную цель. */
  element: T | null;
  /** Наш элемент сейчас в фуллскрине. Чужой фуллскрин (киоск) — `false`. */
  value: boolean;
  /** Запросить фуллскрин; отказ уходит в `onError` и в reject промиса. */
  enter: () => Promise<void>;
  /** Выйти, только если в фуллскрине именно наш элемент. */
  exit: () => Promise<void>;
  toggle: () => Promise<void>;
}

const FULLSCREEN_EVENTS = ["fullscreenchange", "webkitfullscreenchange"] as const;

/** Текущий фуллскрин-элемент с учётом webkit-префикса. */
export function currentFullscreenElement(): Element | null {
  if (typeof document === "undefined") return null;
  const doc = document as WebkitFullscreenDocument;
  return doc.fullscreenElement ?? doc.webkitFullscreenElement ?? null;
}

function requestFullscreen(target: Element): Promise<void> | void {
  if (typeof target.requestFullscreen === "function") {
    return target.requestFullscreen(); // reactuse-ok: обёртка Fullscreen API — enter() ReactUse не возвращает промис (upstream #516)
  }
  const webkit = target as WebkitFullscreenElement;
  if (typeof webkit.webkitRequestFullscreen === "function") {
    return webkit.webkitRequestFullscreen(); // reactuse-ok: обёртка Fullscreen API — enter() ReactUse не возвращает промис (upstream #516)
  }
  throw new Error("Браузер не поддерживает Fullscreen API");
}

function exitFullscreen(): Promise<void> | void {
  const doc = document as WebkitFullscreenDocument;
  if (typeof doc.exitFullscreen === "function") {
    return doc.exitFullscreen(); // reactuse-ok: обёртка Fullscreen API — exit() ReactUse не возвращает промис (upstream #516)
  }
  if (typeof doc.webkitExitFullscreen === "function") {
    return doc.webkitExitFullscreen(); // reactuse-ok: обёртка Fullscreen API — exit() ReactUse не возвращает промис (upstream #516)
  }
}

export function useFullscreenElement<T extends Element = HTMLElement>(
  options: FullscreenElementOptions = {},
): FullscreenElementHandle<T> {
  const [element, setElement] = useState<T | null>(null);
  // Цель запросов — не состояние, а ref: enter/exit зовут из обработчиков и
  // cleanup, где важна актуальная ссылка, а не значение прошлого рендера.
  const nodeRef = useRef<T | null>(null);
  // Последний смонтированный узел: при размонтировании callback-ref получает
  // `null`, но выйти из фуллскрина всё равно нужно из старого элемента.
  const lastNodeRef = useRef<T | null>(null);
  // Колбэки обновляем эффектом, чтобы не писать в ref во время рендера и не
  // переподписываться на каждое новое замыкание `onError`.
  const optionsRef = useRef(options);

  useEffect(() => {
    optionsRef.current = options;
  });

  const ref = useCallback((node: T | null) => {
    nodeRef.current = node;
    if (node) lastNodeRef.current = node;
    setElement(node);
  }, []);

  const subscribe = useCallback(
    (onChange: () => void) => {
      if (!element || typeof document === "undefined") return () => {};
      const doc = document as WebkitFullscreenDocument;
      for (const event of FULLSCREEN_EVENTS) doc.addEventListener(event, onChange);
      return () => {
        for (const event of FULLSCREEN_EVENTS) doc.removeEventListener(event, onChange);
      };
    },
    [element],
  );

  const getSnapshot = useCallback(
    () => element !== null && currentFullscreenElement() === element,
    [element],
  );

  // Подписка на оба события сразу — Safari до сих пор шлёт только webkit-вариант.
  const value = useSyncExternalStore(subscribe, getSnapshot, () => false);

  const previousValue = useRef(value);
  useEffect(() => {
    if (previousValue.current === value) return;
    previousValue.current = value;
    if (value) optionsRef.current.onEnter?.();
    else optionsRef.current.onExit?.();
  }, [value]);

  const enter = useCallback(async () => {
    const target = nodeRef.current;
    if (!target || currentFullscreenElement() === target) return;
    try {
      await requestFullscreen(target);
    } catch (error) {
      optionsRef.current.onError?.(error);
      throw error;
    }
  }, []);

  const exit = useCallback(async () => {
    const target = nodeRef.current ?? lastNodeRef.current;
    if (!target || currentFullscreenElement() !== target) return;
    try {
      await exitFullscreen();
    } catch (error) {
      optionsRef.current.onError?.(error);
      throw error;
    }
  }, []);

  const toggle = useCallback(async () => {
    const target = nodeRef.current;
    if (target && currentFullscreenElement() === target) await exit();
    else await enter();
  }, [enter, exit]);

  return { ref, element, value, enter, exit, toggle };
}
