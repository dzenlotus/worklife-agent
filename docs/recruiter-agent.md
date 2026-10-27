# Worklife Recruiter

Карьерный агент работает в вашем AI-клиенте и использует Worklife как инструменты и хранилище. Он собирает рынок, сопоставляет вакансии с опытом и условиями, готовит правдивые CV на нужном языке, ведёт отклики, переписку, интервью и офферы. Локальный браузер показывает результаты и настройки. Отдельный ключ модели для такого подключения не нужен.

## Установка

Короткая команда после публикации пакета в PyPI:

```sh
uvx --python 3.12 worklife-agent --target codex
```

Она подготавливает постоянное окружение Python, Worklife, Chromium, личное хранилище и выбранный
проектный адаптер. Выберите Codex, Claude Code, Cursor или OpenCode на лендинге — команда подстроится.
Для другого MCP-клиента `--target generic` создаёт JSON для импорта. После установки откройте
`~/worklife-career` в выбранном клиенте и включите агента. Runtime находится вне временного кеша uvx.

Из установленного проекта:

```sh
uv sync --extra browser
uv run worklife-recruiter targets
uv run worklife-recruiter install --target codex \
  --destination ../worklife-career --config config.toml --env-file .env --dry-run
uv run worklife-recruiter install --target codex \
  --destination ../worklife-career --config config.toml --env-file .env
```

`--config config.toml` подключает **ту же базу и те же адаптеры**, что и локальное приложение, запущенное с этим файлом. Путь `worklife.home` внутри него разрешается относительно файла. `--home` позволяет явно выбрать другую базу. Без `--config` и `--home` действуют обычные настройки Worklife: `WORKLIFE_CONFIG`, `WORKLIFE_HOME`, затем `~/.worklife`. Рабочая папка агента и база Worklife — разные папки.

`--env-file .env` необязателен. Укажите существующий файл, если доступы хранятся в нём. Конфигурация клиента получает только его абсолютный путь; значения секретов не копируются. Файл загружается при запуске MCP и не заменяет уже заданные клиентом переменные окружения. Установщик не ищет `.env` автоматически.

Откройте `../worklife-career` в выбранном клиенте и включите его обычное доверие к папке/MCP. Для клиента с нативными агентами выберите `worklife-recruiter`; в остальных попросите текущего агента вызвать `recruiter_start` у сервера `worklife_recruiter`. При повторном подключении он прочитает сохранённый профиль, воронку, действия и расписания.

Можно установить пакет отдельно от checkout:

```sh
uv tool install 'git+https://github.com/dzenlotus/worklife-agent.git'
worklife-recruiter install --target claude-code --destination ~/worklife-career
```

Генерируемая конфигурация использует Python установленного пакета. Если вы удалили его окружение или переместили checkout, повторите установку. Сама установка не запускает поиск, регистрации или отправку сообщений.

## Клиенты и область установки

Несколько клиентов в одной папке:

```sh
worklife-recruiter install --target codex --target claude-code --target cursor \
  --destination ~/worklife-career
worklife-recruiter install --all --destination ~/worklife-career
```

По умолчанию изменяется только указанная рабочая папка. `--all` применяет подтверждённые проектные адаптеры, а для клиентов с настройками только на уровне пользователя и для неподтверждённых адаптеров готовит экспорт в `.worklife/exports/<client>/`. **Экспорт не означает, что клиент подключён.** Результат команды различает `configured` и `exported` для каждого клиента.

Для явной установки в пользовательские настройки одного клиента:

```sh
worklife-recruiter install --target claude-desktop --scope user --destination ~/worklife-career
worklife-recruiter install --target goose --scope user --destination ~/worklife-career
```

Учитываются `CODEX_HOME`, `COPILOT_HOME`, `XDG_CONFIG_HOME`, `CLINE_MCP_SETTINGS_PATH`, `OPENCLAW_CONFIG_PATH` и Windows `APPDATA`, где они относятся к выбранному адаптеру. Установщик не меняет эти переменные. Нестандартный активный профиль можно указать явно:

```sh
worklife-recruiter install --target zed --destination ~/worklife-career \
  --config-path /absolute/path/to/active/settings.json
```

`--config-path` — файл **AI-клиента**, `--config` — файл **Worklife**. Если одновременно найдены поддерживаемые варианты вроде `opencode.json` и `opencode.jsonc`, установщик попросит выбрать точный файл через `--config-path`, а не создаст конкурирующую конфигурацию.

## Что устанавливается

- MCP `worklife_recruiter`: отдельный профиль карьерных инструментов без инструментов администрирования сети. Полный MCP Worklife остаётся доступен отдельным обычным запуском.
- Инструкции и семь скиллов: начало поиска; рынок; оценка вакансий и CV; отклики и переписка; интервью и офферы; тактика и эксперименты; сведения о работодателях.
- Нативный файл агента и скиллы в документированных каталогах клиента, когда такие форматы подтверждены. Наличие файла не заменяет выбор/включение агента в клиенте.
- Переносимый пакет `.worklife/recruiter`, инструкция `WORKLIFE-START.md`, общий пример MCP и отчёт `.worklife/installation.json`.

В клиенте без нативных скиллов агент получает ту же инструкцию через `recruiter_skill`. Некоторые клиенты не поддерживают MCP Resources; основной рабочий путь использует инструменты и не зависит от Resources.

Установщик заменяет только собственную запись сервера. Чужие серверы, модель, провайдер и разрешения клиента сохраняются. JSONC/JSON5, TOML и YAML редактируются с сохранением комментариев. Перед изменением существующего файла создаётся соседняя копия `*.worklife-backup-<time>` с доступом только владельца. Повторная установка с теми же параметрами не меняет файлы и не создаёт новые копии. `--dry-run` ничего не записывает. Неверная конфигурация проверяется до начала записи.

Нативные определения агента сохраняют заданные пользователем дополнительные поля, например модель. Текст самого Worklife-агента обновляется из пакета. Корневые `AGENTS.md`, `CLAUDE.md` и другие общие инструкции проекта не заменяются.

## Проверка

```sh
worklife-recruiter doctor --destination ~/worklife-career
```

`doctor` проверяет наличие файлов и Python, **не подключение к реальному клиенту**. Перезапустите выбранный клиент, откройте папку и вызовите `recruiter_start`. В ответе должны быть Worklife Recruiter, список скиллов, профиль, действия, воронка и доступные каналы. Без профиля агент уточняет цели; это не повод подставлять демонстрационные вакансии или CV.

Для прямого запуска MCP:

```sh
worklife-recruiter mcp --config /absolute/path/config.toml --env-file /absolute/path/.env
```

Этот процесс использует stdio для MCP. Он не является интерактивным чатом. После закрытия AI-клиента новые рассуждения требуют запущенного агента/автоматизации хоста; детерминированные расписания выполняет оставленное работающим приложение или `worklife worker`.

## Матрица совместимости

Каталог проверен по официальным источникам 27 октября 2026 года. Проверены генерация файлов, сохранение настроек и запуск нашего MCP; это не означает, что установлены и проверены все перечисленные клиенты. Названия и пути относятся к указанным версиям/продуктам; список не претендует на все существующие AI-продукты.

`Нативный` означает подтверждённый формат отдельного агента/режима; иногда это субагент. `MCP` — тот же карьерный процесс через инструкции и инструменты. `Экспорт` требует импорта через интерфейс или отдельного адаптера.

| Клиент | Агент | Автоматическая настройка | Источник |
| --- | --- | --- | --- |
| Codex CLI / desktop / IDE (`codex`) | Нативный | проект, пользователь | [документация](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) |
| Claude Code (`claude-code`) | Нативный | проект, пользователь | [документация](https://code.claude.com/docs/en/mcp) |
| Claude Desktop (`claude-desktop`) | MCP | пользователь | [документация](https://modelcontextprotocol.io/docs/develop/connect-local-servers) |
| Cursor IDE / CLI (`cursor`) | Нативный | проект, пользователь | [документация](https://cursor.com/docs/mcp) |
| Windsurf legacy Cascade (`windsurf`) | MCP | пользователь | [документация](https://code.visualstudio.com/docs/agents/reference/mcp-configuration) |
| Devin Desktop legacy Cascade (`devin-cascade`) | MCP | пользователь | [документация](https://docs.devin.ai/desktop/cascade/mcp) |
| VS Code Copilot (VS Code format) (`vscode`) | Нативный | проект | [документация](https://code.visualstudio.com/docs/agents/reference/mcp-configuration) |
| GitHub Copilot portable format (`copilot`) | Нативный | проект, пользователь | [документация](https://code.visualstudio.com/docs/agents/reference/mcp-configuration) |
| Gemini CLI (`gemini`) | Нативный | проект, пользователь | [документация](https://geminicli.com/docs/tools/mcp-server/) |
| OpenCode (`opencode`) | Нативный | проект, пользователь | [документация](https://opencode.ai/docs/config/) |
| Cline CLI / extensions (`cline`) | MCP | пользователь | [документация](https://docs.cline.bot/mcp/mcp-overview) |
| Roo Code (`roo`) | Нативный | проект | [документация](https://roocodeinc.github.io/Roo-Code/features/mcp/using-mcp-in-roo/) |
| Kilo current CLI / extension (`kilo`) | MCP | проект, пользователь | [документация](https://github.com/Kilo-Org/kilocode/blob/main/packages/kilo-docs/pages/automate/mcp/using-in-cli.md) |
| Kilo Code legacy IDE extension (`kilo-legacy`) | Экспорт | экспорт | [документация](https://github.com/Kilo-Org/kilocode-legacy/blob/main/docs/legacy-ides/automate/tools/use-mcp-tool.md) |
| Continue (`continue`) | MCP | проект | [документация](https://docs.continue.dev/customize/deep-dives/mcp) |
| Amp (`amp`) | MCP | проект, пользователь | [документация](https://ampcode.com/docs/customize/mcp) |
| Factory Droid (`factory`) | Нативный | проект, пользователь | [документация](https://docs.factory.com/harness/mcp) |
| Goose (`goose`) | MCP | пользователь | [документация](https://github.com/aaif-goose/goose/blob/main/documentation/docs/guides/config-files.md) |
| Qwen Code (`qwen`) | MCP | проект, пользователь | [документация](https://qwenlm.github.io/qwen-code-docs/en/users/configuration/settings/) |
| Kiro IDE / CLI (`kiro`) | Нативный | проект, пользователь | [документация](https://kiro.dev/docs/mcp/configuration/) |
| Zed (`zed`) | MCP | точный файл | [документация](https://zed.dev/docs/ai/mcp) |
| Google Antigravity App / IDE / CLI (`antigravity`) | MCP | проект, пользователь | [документация](https://antigravity.google/docs/mcp) |
| Mistral Vibe (`mistral-vibe`) | Нативный | проект, пользователь | [документация](https://github.com/mistralai/mistral-vibe) |
| OpenClaw (`openclaw`) | MCP | пользователь | [документация](https://docs.openclaw.ai/gateway/config-extensions) |
| Pi (`pi`) | MCP | проект, пользователь | [документация](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/mcp.md) |
| OpenHands (`openhands`) | Экспорт | экспорт | [документация](https://docs.openhands.dev/overview/model-context-protocol) |
| TRAE (`trae`) | Экспорт | экспорт | [документация](https://docs.trae.ai/ide/model-context-protocol) |
| Other MCP / Agent Skills host (`generic`) | Экспорт | экспорт | [документация](https://modelcontextprotocol.io/docs/develop/connect-local-servers) |

Для каждого клиента подробные оговорки и остальные источники есть в выводе `targets` и в [каталоге пакета](../src/worklife/agent_bundle/harnesses.json).

Особые случаи: Zed требует точного файла активного профиля; OpenHands настраивает MCP через собственный интерфейс и зашифрованное хранилище; пути Windsurf legacy и Devin Cascade различаются; текущий Kilo и старое расширение Kilo Code имеют разные схемы. Generic экспорт подходит как исходный stdio-пример для другого MCP-клиента, но не обещает совместимость его установщика.
