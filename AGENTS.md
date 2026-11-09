# AGENTS.md — ekranchik-modern

Инструкции для ИИ-агентов. Детали проекта — в [`CONTEXT.md`](CONTEXT.md) и `docs/`.

## Команды

```bash
npm run install-all     # node-зависимости + фронтенд
npm run setup:python    # backend/.venv на Python 3.12: системный python и pip не использовать
npm run dev             # бэкенд :8013 + фронтенд :5173, рабочий режим (реальный PLC и книга)
npm run dev:sim         # то же + OPC UA симулятор и SIMULATION_ENABLED=true
npm run dev:sim:fast    # то же, но симулятор в профиле fast: ~70 с на проход вместо ~25 мин
npm run dev:kill        # освободить порты
```

### mise

Версии toolchain (Node, ruff, hk, линтеры) — только в корневом `mise.toml`;
`mise.lock` фиксирует их для CI. Python 3.12 живёт в `backend/.venv`, и mise
активирует его директивой `_.python.venv` — поэтому `python` в задачах не
зависит от системного PATH.

```bash
mise trust && mise install   # один раз на клон: инструменты из mise.toml/mise.lock
mise run install             # npm ci + frontend ci + backend/.venv
mise run dev                 # локальный стенд :8013 + :5173
mise run test                # pytest + vitest
mise run check               # полный гейт, ровно как в CI
```

Проверка изменения — бэкенд:

```bash
mise run test                                                    # все backend+frontend тесты
cd backend && mise exec -- python -m pytest tests/test_hanger_journal.py -k day_change
```

`uvicorn` поднят без `--reload`: после правки в `backend/app/` стенд надо
перезапустить, иначе тесты зелёные, а стенд отдаёт старый код.

E2E (`npm run test:e2e`) требует запуска фронтенда и Chrome с CDP на 9222 —
сначала `npm run chrome:debug`; `live_demo.spec.mts` рассчитывает на быстрый
симулятор, то есть на `npm run dev:sim:fast`. На штатном `npm run dev:sim`
проход занимает ~25 минут (10 ванн × 120 с + 9 переходов × 30 с) и в таймаут
теста не укладывается: это ограничение симулятора, а не теста. Таймаут теста
задаётся `E2E_LIVE_TIMEOUT` (мс), по умолчанию 180000. Быстрый профиль пишет
журнал в `journal-e2e/`, чтобы короткие проходы не попадали в калибровку
`journal-dev/`.

## Проверки перед сдачей

```bash
mise run check     # полный гейт; то же запускает CI (.github/workflows/check.yml)
mise run fix       # безопасные автофиксы, затем перечитать дифф
mise run hooks     # один раз на клон: git-хуки pre-commit/pre-push/commit-msg
```

`mise run check` должен быть зелёным до конца работы — это условие «изменение
готово», а не пожелание. Детали, бейзлайны и исключения — в
[`docs/quality-gates.md`](docs/quality-gates.md).

- Правила линтеров **не отключаются**, чтобы изменение прошло. Исключение —
  один файл и одно правило, с причиной; для рисков ещё и с датой ревизии, и
  это решение человека, а не агента.
- Сгенерированные файлы не правятся руками: `.mise/locks/` (обновляется
  `mise lock`), `dist-exe/`, `dist-full/`, `frontend/dist/`, `journal*/`,
  `static/` (данные стенда).
- Сообщения коммитов — Conventional Commits: `commitlint` проверяет их в
  `commit-msg` и в CI.

## Зависимости и зелёность CI

`main` всегда зелёный; красный PR не мержится, включая Dependabot. Полный
playbook — [`docs/dependabot.md`](docs/dependabot.md), коротко:

- зелёные PR мержатся `gh pr merge <N> --squash --delete-branch`, после
  каждого — дождаться зелёного прогона в `main`;
- устаревшие ветки Dependabot — `@dependabot rebase`;
- связанные пакеты (react + типы, vite + plugin-react, pandas + dateutil,
  pytest + pytest-asyncio, pydantic + pydantic-settings, typescript + tsconfig,
  tailwind + postcss) обновляются одной веткой, а не по одному PR;
- после обновлений локально: `mise run check`, backend pytest, frontend
  `npx vitest run` и `npm run build`;
- CI смотреть через `gh run watch <id> --exit-status`, а не «на глаз».

## Dev-стенд в соседнем терминале (Orca)

Перед финальным ответом (пользователь проверяет сразу после него) агент
убеждается, что dev-стенд жив. Работать **только с уже открытым соседним
терминалом через Orca**: новых терминалов не создавать и стек из своей оболочки
не запускать.

1. `orca terminal list` — найти обычный shell-терминал этого worktree (не
   Qoder-терминал агента); состояние — `orca terminal read --terminal <handle> --screen`.
2. Проверить стенд: backend `http://127.0.0.1:8013/health` и frontend
   `http://127.0.0.1:5173/`.
3. Если в ответе менялись файлы backend/frontend или стенд не отвечает —
   отправить в тот же терминал `npm run dev:kill; npm run dev`
   (`orca terminal send --terminal <handle> --text "npm run dev:kill; npm run dev" --enter`)
   и дождаться health. Для режима с симулятором — `npm run dev:sim`.
4. Если открытого терминала нет — не поднимать стек самому: попросить
   пользователя открыть терминал в Orca одной строкой.
5. Отвечать только после зелёных чеков. Если код не менялся и стенд жив — не
   трогать.

## Логи контейнеров

Каждый сервис в `infra/compose/docker-compose.prod.yml` объявляет потолок лога:

```yaml
logging:
  driver: json-file
  options:
    max-size: "20m"
    max-file: "3"
```

Потолок — около 60 МБ на контейнер. Без него json-лог растёт неограниченно: 28.09.2026
так налило 15 ГБ в access-лог `ekranchik-nginx-prod`, корневой раздел прод-сервера
заполнился под ноль (209 МБ свободно из 38 ГБ), и сборка соседнего проекта падала на
`apt-get`. Новый сервис в compose — сразу с этим блоком.

У `nginx` в `infra/nginx/default.conf` стоит `access_log off` в `location /static/`:
киоск-дашборд круглосуточно перебирает превью, и этот поток давал основную массу строк,
ничего не диагностируя. Логи `/api/` и `/ws` остаются на месте.

`docker logs` отдаёт и ротированные файлы, поэтому его вывод больше текущего файла —
это не протечка потолка.

На прод-сервере дополнительно лежит `/etc/logrotate.d/docker-containers`
(`size 200M`, `rotate 3`, `compress`, `copytruncate`) — сетка для контейнеров, созданных
мимо compose. Файл хостовый, в git не хранится.

## Журнал подвесов — не лог контейнера

Историю проходов пишет файл `journal/hanger-passes-YYYY-MM-DD.jsonl`, а не
stdout. Он лежит на своём томе `../../journal` и НЕ проходит через потолок
json-лога: 30 суток × 32 МБ на файл держит приложение само
(`app/services/hanger_journal.py`, срок и потолок — `JOURNAL_RETENTION_DAYS`,
`JOURNAL_MAX_FILE_BYTES`).

Каталог задаётся переменной `JOURNAL_DIR`, и у среды он свой: прод-контейнер
пишет в `/app/journal` (bind `../../journal`, перекрывает `.env`), dev-хост — в
`../journal-dev` (`backend/.env`). Общего файла у сред нет: dev смотрит ту же
линию по тому же OPC UA, но разбор проходов ведёт в свой каталог.

Каталог по умолчанию — `<каталог данных>/journal`, а каталог данных dev-хоста —
это `static/`, который прод-nginx раздаёт наружу (`/static/`). Поэтому для
dev-хоста `JOURNAL_DIR` задан явно: в `static/journal` внутренний разбор
проходов был виден всем, кто открывает `http://<хост>/static/journal/…`.

Правила, за которыми журнал дописывается (`app/services/journal_writer.py`):

- пишет фоновая задача `journal_writer.run_forever`, а не роут: проход попадает
  в файл при закрытом дашборде (на боевой машине он закрыт почти всегда);
- дедупликация по `cycle_id`, при старте ключи последних суток читаются из
  самого журнала — иначе после перезапуска проходы записались бы повторно;
- книга учёта недоступна — проход откладывается, а не записывается с
  выдуманным вердиктом;
- удаление старых файлов идёт с записью в лог списком: файл, исчезнувший без
  следа, неотличим от файла, которого не было.
