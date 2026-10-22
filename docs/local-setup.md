# Локальный запуск на Windows без Docker

Нужны Python 3.12, Node.js 22+, pnpm 11.25.0 и Visual Studio Build Tools с компонентом C++ desktop development. Бинарники и данные создаются в игнорируемом `.local`; системные службы не устанавливаются.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe scripts/configure.py
.\.venv\Scripts\python.exe scripts/bootstrap_windows.py
```

В `.env` задайте свободный PostgreSQL-порт, например `55432`, в DATABASE_URL. Пароли генерируются configure.py; не заменяйте их примером `change-me`.

```powershell
.\.venv\Scripts\python.exe scripts/start_native.py
.\.venv\Scripts\python.exe -m vmerger.initialize
pnpm --dir web install --frozen-lockfile
pnpm --dir web run build
.\.venv\Scripts\python.exe -m uvicorn vmerger.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

В другом терминале запустите worker:

```powershell
.\.venv\Scripts\python.exe -m vmerger.worker
```

Откройте http://127.0.0.1:8000 и введите APP_TOKEN из `.env`. Без GEMINI_API_KEY интерфейс честно показывает недоступность AI; загрузка продолжает работать. Ключ модели можно добавить позже, после чего нужно перезапустить API/worker и запустить анализ ранее загруженных материалов.

Для разработчика с Vite: задайте `APP_ORIGIN=http://127.0.0.1:5173`, перезапустите API и выполните `pnpm --dir web run dev`. API остаётся на порту 8000; Vite проксирует `/api`. Для возврата к собранной версии восстановите APP_ORIGIN на 8000.

## Проверки

```powershell
.\.venv\Scripts\python.exe -m pytest --integration --cov=vmerger --cov-report=json:.local/coverage.json
.\.venv\Scripts\python.exe scripts/check_coverage.py
pnpm --dir web run test
$env:PLAYWRIGHT_CHANNEL='chrome'
pnpm --dir web exec playwright test
```

Последняя проверка использует установленный Chrome и запущенный API с отключённым Gemini. Она создаёт пустой проект «Локальная проверка»; скриншоты в docs/images показывают настоящий интерфейс. Медиатесты используют явно тестовые цветовые клипы/сигнал, а не выдуманные результаты AI.

## Остановка

Остановите API и worker через Ctrl+C в их терминалах. PostgreSQL:

```powershell
& .local/tools/postgres/pgsql/bin/pg_ctl.exe -D .local/pgdata stop -m fast
```

SeaweedFS запущен как фоновый процесс; PID записан в `.local/seaweed.pid`. Перед остановкой проверьте, что процесс с этим PID — именно `.local/tools/weed/weed.exe`, и завершите его. Не удаляйте `.local/seaweed` или `.local/pgdata`: там постоянные данные, а не кэш.

Скачиваемые версии и SHA-256 зафиксированы в bootstrap_windows.py. Источники: [EDB PostgreSQL binaries](https://www.enterprisedb.com/download-postgresql-binaries), [pgvector](https://github.com/pgvector/pgvector), [SeaweedFS releases](https://github.com/seaweedfs/seaweedfs/releases), [Gyan FFmpeg builds](https://www.gyan.dev/ffmpeg/builds/). Это сторонние зависимости; исполняемые файлы не включены в Git.
