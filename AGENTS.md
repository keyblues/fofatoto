# AGENTS.md

Guidance for agents working in this repository.

## Project overview

`fofatoto` is a single-file, zero-dependency Python tool for querying the FOFA network-space search engine. CLI + built-in local Web UI, bulk export, batch queries, field customization, dedup, icon-hash same-icon lookup (`--icon`), multi-format output (CSV/JSON/TXT). Compiled to native binaries via Nuitka.

**No third-party dependencies** — stdlib only. `pyproject.toml` declares `dependencies = []`. Requires Python ≥ 3.11.

## Commands

```bash
# Syntax check + unit tests (stdlib unittest, 142 tests, no network calls)
python -m py_compile fofatoto.py
python -m unittest test_fofatoto -v

# Run CLI
python fofatoto.py "domain=baidu.com" -l 10

# Run Web UI (auto-opens browser unless --host given; default listen 127.0.0.1, probes port from 17380)
python fofatoto.py -w

# Build binary (requires: pip install nuitka zstandard; Linux also needs patchelf + python3-dev)
# Linux / macOS. Windows omits --static-libpython=yes. Same flags as CI.
python -m nuitka --onefile --lto=yes --static-libpython=yes --remove-output \
  --assume-yes-for-downloads --python-flag=no_site,no_docstrings \
  --noinclude-default-mode=nofollow \
  --output-dir=dist --output-filename=fofatoto fofatoto.py
```

Tests live in `test_fofatoto.py` (repo root, stdlib `unittest` only — the zero-dependency rule applies to tests too; FOFA API calls are mocked via `urllib.request.urlopen` patching, never hit the network). There is no linter or formatter config. CI runs `py_compile` + tests before every build.

## Architecture

Everything lives in `fofatoto.py` (~3900 lines) plus `test_fofatoto.py`. No package structure — designed as a self-contained Nuitka-compilable script.

**Data flow:** `config.json` → `ConfigManager` → `FofaClient` → `FofaResult` dataclass → `Exporter` (CSV/JSON/TXT)

**Key components (current line numbers):**

| Component | Lines | Notes |
|-----------|-------|-------|
| `APP_VERSION`, `DEFAULT_CONFIG`, `DEFAULT_FIELDS` | 37–52 | Module-level constants |
| `WEB_FIELD_CATEGORIES`, `WEB_HTML_TEMPLATE` | 100–529 | **The entire Web UI is an inline HTML/CSS/JS string** with `__APP_VERSION__`, `__GITHUB_URL__`, `__FIELD_CATEGORIES_JSON__`, `__DEFAULT_FIELDS_JSON__` placeholders substituted by `render_web_html()` (532); field-selector categories live in `WEB_FIELD_CATEGORIES` and are injected into the template |
| `ConfigManager` | 550–648 | `get_client()` (631) supports **hot-reload** — re-reads `config.json` each request, caches `FofaClient` by `(url, key, info_api)` signature; no restart needed |
| Update check | 650–1016 | `fetch_latest_release` hits GitHub Releases; `announce_update` (983) for CLI/Web startup; `snapshot_update` (1000) backs `GET /api/update`. Success cached 12h, failure 1h, in `.fofatoto_update.json` next to the executable. `--no-update-check` / `FOFATOTO_NO_UPDATE_CHECK=1` disables it |
| `FofaResult` dataclass | 1018–1063 | 28 FOFA fields; `_extra` dict captures unknown API fields |
| `ALL_FIELD_NAMES` / `KNOWN_FIELDS` / `CUSTOM_FIELDS` | 1070–1093 | **Single source of truth for the field list**, derived from `FofaResult`; `_validate_web_field_categories()` runs at import and fails fast if web categories drift from the field set. To add a FOFA field: extend `FofaResult` + categorize in `WEB_FIELD_CATEGORIES` (both in this file) |
| Icon 提取与 icon_hash | 1212–1541 | `IconExtractError`, `_murmur3_32` (pure-Python MurmurHash3 x86_32 — keep zero-dependency), `favicon_hash` (Shodan/FOFA convention: mmh3 of newline-wrapped base64), `build_icon_query`, `_IconLinkParser`, `resolve_icon` (1458, targets: URL / local file / raw hash), `resolve_icon_cached` (1526, backs Web `/api/icon`, file input disabled) |
| `FofaClient` | 1543–1912 | `search()` (1585) for ≤10000 single-request; `search_all_efficient()` (1664) for deep export via `before` time-cursor; both take `cancel_check` so Web UI cancel interrupts rate-limit/retry sleeps (`_sleep_interruptible`) |
| `build_url`, `dedup_results` | 1914, 1961 | URL assembly from host/port/protocol; dedup by field tuple, including `_extra` custom fields |
| `Exporter` | 1996–2112 | `export_csv`/`export_json`/`export_txt`; field filtering, `_extra` handling; default columns = `ALL_FIELD_NAMES` |
| Export task system | 2535–2850 | `ExportTask` + `_export_tasks` dict; background TTL cleanup thread (60s interval, TTL anchored to `finished_at`); terminal transitions go through `_finish_export_task` (2609); task threads spawn via `_start_export_thread` (2624), which finishes the task as error if `thread.start()` fails (no ghost running tasks); `_has_running_export_task()` (2594, caller must hold `_export_lock`) is checked and the task registered in one critical section in `/api/export` & `/api/batch`; cancel flips `cancelled`/`discard` and raises `KeyboardInterrupt`; web export files go through `_write_web_exports` (2838) |
| `FofaWebHandler` | 2979–3565 | `http.server.BaseHTTPRequestHandler`; routes `/api/search`, `/api/icon` (`_handle_icon`), `/api/export`, `/api/batch`, `/api/progress`, `/api/info`, `/api/update`, `GET /api/export/download`, `POST /api/progress/cancel`; threads via `ThreadingHTTPServer`; access log helpers just above the class format an aligned `[web] time method path status ip` line (method and status colored). It omits successful `/api/progress` polls, browser probes (`favicon.ico`, `/json/version` and other DevTools discovery paths), and repeated `GET /` from the same client within 30s; `/api/info` and `/api/update` are logged; every line includes the client IP, including loopback; batch accepts per-target `max_size` |
| `FofaWebServer` | 3628–3693 | Binds `--host` address (default `127.0.0.1`), auto-probes port from 17380; explicit `--host` disables browser auto-open. Helpers above it: `_find_available_port` (3567), `_open_browser` (3586, WSL/SSH/headless handling), `_lan_ips` (3615). Calls `announce_update(blocking=False)` after the startup banner |
| `main()` | 3698 | argparse; web mode when `--web` or no query + no batch file + no `--icon`; CLI calls `announce_update(blocking=True)` after the banner unless `--no-update-check` |

**Time-cursor strategy (`search_all_efficient`):** probe with `size=1` → loop querying `before` in windows of at most 10000 rows (1000-row tail floor when the target is above 10000); the next cursor is `min(lastupdatetime) - 1s` → dedup by host → stop when a page is short of the requested size, or the fill/max target is met.

## Editing the Web UI

The Web UI HTML/CSS/JS is a single raw string literal (`WEB_HTML_TEMPLATE`, lines 113–529). This has important consequences:

- **No syntax highlighting or editor support** — validate JS by running `py_compile` then testing in browser.
- **No external assets** — all CSS and JS inline, zero dependencies, Chinese UI.
- **Placeholders** `__APP_VERSION__` / `__GITHUB_URL__` / `__FIELD_CATEGORIES_JSON__` / `__DEFAULT_FIELDS_JSON__` are replaced by `render_web_html()` — don't use double-underscore IDs elsewhere in the template (collision risk). The update-badge script intentionally contains `__GITHUB_URL__/releases/` so the link prefix stays tied to `GITHUB_URL`.
- **All `onclick` handlers use `&quot;`** for quotes inside the Python string, not escaped single quotes.
- Frontend state lives in JS module-level vars (`currentMode`, `currentResults`, `excludedFilters`, `exportPollTimer`, etc.) — there is no framework.

## Config and secrets

- `config.json` (gitignored) lives next to the script/exe. In Nuitka onefile mode, located via `NUITKA_ONEFILE_DIRECTORY` env var (NOT `NUITKA_ONEFILE_PARENT`, which is a PID, not a path — v1.2.1 had this bug).
- `config.example.json` is the tracked template (whitelisted in `.gitignore` via `!config.example.json`).
- **Never commit real API keys.** A real key leaked into git history previously — always verify `config.json` is not staged before committing.
- Web UI hot-reloads config: editing `config.json` takes effect on next request, no server restart needed (`ConfigManager.get_client()`).

## Version sync

`APP_VERSION` (fofatoto.py:37) is the source of truth and always reflects the last **released** version. Unreleased changes go under a `## Unreleased` heading in `CHANGELOG.md` — never invent a version number for unpublished work. Only at release time: pick the version, rename the heading to `## vX.Y.Z - YYYY-MM-DD`, and update all three together:
- `APP_VERSION` in fofatoto.py
- `pyproject.toml` `version` field
- `uv.lock` package version

Currently all three are synced at `1.8.0` (last release: v1.8.0, 2026-10-09).

## Branch and changelog rules

- **Always work on `main`.** Do not create or switch branches.
- **Keep `CHANGELOG.md` updated.** Release-log style: version headings (`## vX.Y.Z - YYYY-MM-DD`), categorized changes (新增/修复/优化/文档/其他).
- Don't bump the version number for every minor edit — batch related changes into one version entry.

## CI/CD

`.github/workflows/build.yml` triggers on tag push (`v*`) or manual dispatch:
- `check` job runs first: `py_compile` + `test_fofatoto` unittest suite (asserts `APP_VERSION` = `pyproject.toml` = `uv.lock`); on tag pushes it also verifies the tag matches `v$APP_VERSION`. All build jobs `needs: check`.
- Windows amd64; Linux amd64 (`ubuntu-latest`) and arm64 (`ubuntu-24.04-arm`), both inside a Debian bookworm container so the image follows the runner architecture; macOS arm64 only (Apple Silicon / M 系列, `macos-latest`, job asserts `platform.machine()=="arm64"`)
- All built via Nuitka `--onefile --lto=yes`
- Release job runs only on tag push (`v*`). It attaches GitHub Release assets named `fofatoto.exe`, `fofatoto`, `fofatoto_arm64`, and `fofatoto_mac_arm64`. Manual dispatch still builds and uploads Actions artifacts (`fofatoto-windows_amd64`, `fofatoto-linux_amd64`, `fofatoto-linux_arm64`, `fofatoto-macos_arm64`) and does not create a tag or Release assets.
