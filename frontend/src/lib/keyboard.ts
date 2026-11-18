// Клавиатурные события в полях ввода.

/**
 * Enter во время набора через IME (китайская, японская, корейская раскладка)
 * подтверждает иероглиф, а не действие экрана. Браузер помечает такое нажатие
 * `isComposing` (в старых — `keyCode 229`), и обработчик обязан его пропустить:
 * иначе Enter закроет фильтр или сохранит путь на середине слова.
 */
export function isComposing(event: {
  nativeEvent: { isComposing: boolean };
  keyCode: number;
}): boolean {
  return event.nativeEvent.isComposing || event.keyCode === 229;
}
