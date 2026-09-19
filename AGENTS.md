# AGENTS.md

Guidance for agents working in this repository.

## Project overview

`fofatoto` is a single-file, zero-dependency Python tool for querying the FOFA network-space search engine. CLI + built-in local Web UI, bulk export, batch queries, field customization, dedup, multi-format output (CSV/JSON/TXT). Compiled to native binaries via Nuitka.

**No third-party dependencies** — stdlib only. `pyproject.toml` declares `dependencies = []`. Requires Python ≥ 3.11.

## Commands

```bash
# Syntax check + unit tests (stdlib unittest, 77 tests, no network calls)
python -m py_compile fofatoto.py
python -m unittest test_fofatoto -v

# Run CLI
python fofatoto.py "domain=baidu.com" -l 10

# Run Web UI (auto-opens browser unless --host given; default listen 127.0.0.1, probes port from 17380)
python fofatoto.py -w

# Build binary (requires: pip install nuitka zstandard; Linux also needs patchelf + python3-dev)
python -m nuitka --onefile --lto=yes --static-libpython=yes --remove-output \
  --assume-yes-for-downloads --python-flag=no_site,no_docstrings \
  --noinclude-pytest-mode=nofollow --noinclude-setuptools-mode=nofollow \
  --noinclude-unittest-mode=nofollow --noinclude-pydoc-mode=nofollow \
  --output-filename=fofatoto fofatoto.py
```

Tests live in `test_fofatoto.py` (repo root, stdlib `unittest` only — the zero-dependency rule applies to tests too; FOFA API calls are mocked via `urllib.request.urlopen` patching, never hit the network). There is no linter or formatter config. CI runs `py_compile` + tests + a three-way version-sync check before every build.

## Architecture

Everything lives in `fofatoto.py` (~3050 lines) plus `test_fofatoto.py`. No package structure — designed as a self-contained Nuitka-compilable script.

**Data flow:** `config.json` → `ConfigManager` → `FofaClient` → `FofaResult` dataclass → `Exporter` (CSV/JSON/TXT)

**Key components (current line numbers):**

| Component | Lines | Notes |
|-----------|-------|-------|
| `APP_VERSION`, `DEFAULT_CONFIG`, `DEFAULT_FIELDS` | 33–48 | Module-level constants |
| `WEB_FIELD_CATEGORIES`, `WEB_HTML_TEMPLATE` | 92–512 | **The entire Web UI is an inline HTML/CSS/JS string** with `__APP_VERSION__`, `__GITHUB_URL__`, `__FIELD_CATEGORIES_JSON__`, `__DEFAULT_FIELDS_JSON__` placeholders substituted by `render_web_html()` (515); field-selector categories live in `WEB_FIELD_CATEGORIES` and are injected into the template |
| `ConfigManager` | 533–639 | `get_client()` (618) supports **hot-reload** — re-reads `config.json` each request, caches `FofaClient` by `(url, key, info_api)` signature; no restart needed |
| `FofaResult` dataclass | 641–691 | 28 FOFA fields; `_extra` dict captures unknown API fields |
| `ALL_FIELD_NAMES` / `KNOWN_FIELDS` / `CUSTOM_FIELDS` | 693–712 | **Single source of truth for the field list**, derived from `FofaResult`; `_validate_web_field_categories()` runs at import and fails fast if web categories drift from the field set. To add a FOFA field: extend `FofaResult` + categorize in `WEB_FIELD_CATEGORIES` (both in this file) |
| `FofaClient` | 833–1245 | `search()` for ≤10000 single-request; `search_all_efficient()` (979) for deep export via `before` time-cursor; both take `cancel_check` so Web UI cancel interrupts rate-limit/retry sleeps (`_sleep_interruptible`) |
| `build_url`, `dedup_results` | 1247, 1294 | URL assembly from host/port/protocol; dedup by field tuple, including `_extra` custom fields |
| `Exporter` | 1329–1446 | `export_csv`/`export_json`/`export_txt`; field filtering, `_extra` handling; default columns = `ALL_FIELD_NAMES` |
| Export task system | 1847–2161 | `ExportTask` + `_export_tasks` dict; background TTL cleanup thread (60s interval, TTL anchored to `finished_at`); terminal transitions go through `_finish_export_task`; task threads spawn via `_start_export_thread`, which finishes the task as error if `thread.start()` fails (no ghost running tasks); `_has_running_export_task()` (caller must hold `_export_lock`) is checked and the task registered in one critical section in `/api/export` & `/api/batch`; cancel flips `cancelled`/`discard` and raises `KeyboardInterrupt`; web export files go through `_write_web_exports` |
| `FofaWebHandler` | 2164–2754 | `http.server.BaseHTTPRequestHandler`; routes `/api/search`, `/api/export`, `/api/batch`, `/api/progress`, `/api/info`; threads via `ThreadingHTTPServer`; access log includes client source IP; batch accepts per-target `max_size` |
| `FofaWebServer` | 2756–2821 | Binds `--host` address (default `127.0.0.1`), auto-probes port from 17380; explicit `--host` disables browser auto-open. Helpers above it: `_find_available_port`, `_open_browser` (WSL/SSH/headless handling), `_lan_ips` |
| `main()` | 2824 | argparse; web mode when `--web` or no query + no batch file |

**Time-cursor strategy (`search_all_efficient`):** probe with `size=1` → loop querying `before="<lastupdatetime>"` in 10000-result windows → dedup by host → stop when batch <10000 or fill_percent reached.

## Editing the Web UI

The Web UI HTML/CSS/JS is a single raw string literal (`WEB_HTML_TEMPLATE`, lines 108–512). This has important consequences:

- **No syntax highlighting or editor support** — validate JS by running `py_compile` then testing in browser.
- **No external assets** — all CSS and JS inline, zero dependencies, Chinese UI.
- **Placeholders** `__APP_VERSION__` / `__GITHUB_URL__` / `__FIELD_CATEGORIES_JSON__` / `__DEFAULT_FIELDS_JSON__` are replaced by `render_web_html()` — don't use double-underscore IDs elsewhere in the template (collision risk).
- **All `onclick` handlers use `&quot;`** for quotes inside the Python string, not escaped single quotes.
- Frontend state lives in JS module-level vars (`currentMode`, `currentResults`, `excludedFilters`, `exportPollTimer`, etc.) — there is no framework.

## Config and secrets

- `config.json` (gitignored) lives next to the script/exe. In Nuitka onefile mode, located via `NUITKA_ONEFILE_DIRECTORY` env var (NOT `NUITKA_ONEFILE_PARENT`, which is a PID, not a path — v1.2.1 had this bug).
- `config.example.json` is the tracked template (whitelisted in `.gitignore` via `!config.example.json`).
- **Never commit real API keys.** A real key leaked into git history previously — always verify `config.json` is not staged before committing.
- Web UI hot-reloads config: editing `config.json` takes effect on next request, no server restart needed (`ConfigManager.get_client()`).

## Version sync

`APP_VERSION` (fofatoto.py:33) is the source of truth and always reflects the last **released** version. Unreleased changes go under a `## Unreleased` heading in `CHANGELOG.md` — never invent a version number for unpublished work. Only at release time: pick the version, rename the heading to `## vX.Y.Z - YYYY-MM-DD`, and update all three together:
- `APP_VERSION` in fofatoto.py
- `pyproject.toml` `version` field
- `uv.lock` package version

Currently all three are synced at `1.6.0` (last release: v1.6.0, 2026-09-19).

## Branch and changelog rules

- **Always work on `main`.** Do not create or switch branches.
- **Keep `CHANGELOG.md` updated.** Release-log style: version headings (`## vX.Y.Z - YYYY-MM-DD`), categorized changes (新增/修复/优化/文档/其他).
- Don't bump the version number for every minor edit — batch related changes into one version entry.

## CI/CD

`.github/workflows/build.yml` triggers on tag push (`v*`) or manual dispatch:
- `check` job runs first: `py_compile` + `test_fofatoto` unittest suite + version-sync check (`APP_VERSION` = `pyproject.toml` = `uv.lock`); on tag pushes it also verifies the tag matches `v$APP_VERSION`. All build jobs `needs: check`.
- Windows amd64; Linux amd64 (`ubuntu-latest`) and arm64 (`ubuntu-24.04-arm`), both inside a Debian bookworm container so the image follows the runner architecture; macOS arm64 only (Apple Silicon / M 系列, `macos-latest`, job asserts `platform.machine()=="arm64"`)
- All built via Nuitka `--onefile --lto=yes`
- Release job runs only on tag push (`v*`), not on manual dispatch — dispatch still builds and uploads artifacts, but does not create a tag. Artifact names: `fofatoto.exe`, `fofatoto`, `fofatoto_arm64`, `fofatoto_mac_arm64`
