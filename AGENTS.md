# AGENTS.md

Guidance for agents working in this repository.

## Project overview

`fofatoto` is a single-file, zero-dependency Python tool for querying the FOFA network-space search engine. CLI + built-in local Web UI, bulk export, batch queries, field customization, dedup, icon-hash same-icon lookup (`--icon`), multi-format output (CSV/JSON/TXT). Compiled to native binaries via Nuitka.

**No third-party dependencies** — stdlib only. `pyproject.toml` declares `dependencies = []`. Requires Python ≥ 3.11.

## Commands

```bash
# Syntax check + unit tests (stdlib unittest, 206 tests, no network calls)
python -m py_compile fofatoto.py
python -m unittest test_fofatoto -v

# Run CLI
python fofatoto.py "domain=baidu.com" -l 10

# Run Web UI (auto-opens browser unless --host given; default listen 127.0.0.1, probes port from 17380)
python fofatoto.py -w

# Build binary (nuitka + zstandard: venv, or pip install --break-system-packages on externally managed Python; Linux also needs gcc, python3-dev, patchelf)
# Linux / macOS. Windows omits --static-libpython=yes. Same flags as CI.
python -m nuitka --onefile --lto=yes --static-libpython=yes --remove-output \
  --assume-yes-for-downloads --python-flag=no_site,no_docstrings \
  --noinclude-default-mode=nofollow \
  --output-dir=dist --output-filename=fofatoto fofatoto.py
```

Tests live in `test_fofatoto.py` (repo root, stdlib `unittest` only — the zero-dependency rule applies to tests too; FOFA API calls are mocked via `urllib.request.urlopen` patching, never hit the network). There is no linter or formatter config. CI runs `py_compile` + tests before every build.

## Architecture

Everything lives in `fofatoto.py` (~4024 lines) plus `test_fofatoto.py`. No package structure — designed as a self-contained Nuitka-compilable script.

**Data flow:** `config.json` → `ConfigManager` → `FofaClient` → `FofaResult` dataclass → `Exporter` (CSV/JSON/TXT)

**Key components (current line numbers):**

| Component | Lines | Notes |
|-----------|-------|-------|
| `APP_VERSION`, `DEFAULT_CONFIG`, `DEFAULT_FIELDS` | 40–66 | Module-level constants; `DEFAULT_CONFIG` ships the `web_auth` block (`enabled`/`secret`, default off) so fresh `config.json` files and the Web UI config-guidance template carry it |
| `WEB_FIELD_CATEGORIES`, `WEB_HTML_TEMPLATE` | 107–533 | **The entire Web UI is an inline HTML/CSS/JS string** with `__APP_VERSION__`, `__GITHUB_URL__`, `__FIELD_CATEGORIES_JSON__`, `__DEFAULT_FIELDS_JSON__` placeholders substituted by `render_web_html()` (541); field-selector categories live in `WEB_FIELD_CATEGORIES` and are injected into the template |
| `ConfigManager` | 559–660 | `get_client()` (649) supports **hot-reload** — re-reads `config.json` via `load()` on each call and returns a new `FofaClient`; no restart needed. `_load_web_auth` parses the optional `web_auth` object (missing / non-dict → disabled); `public_status()` also reports `web_auth_enabled` (never the secret) |
| Update check | 662–1024 | `fetch_latest_release` (803) hits GitHub Releases; `announce_update` (995) for CLI/Web startup; `snapshot_update` (1012) backs `GET /api/update`. Success cached 12h, failure 1h, in `.fofatoto_update.json` next to the executable. `--no-update-check` / `FOFATOTO_NO_UPDATE_CHECK=1` disables it |
| `FofaResult` dataclass | 1030–1075 | 28 FOFA fields; `_extra` dict captures unknown API fields |
| `ALL_FIELD_NAMES` / `KNOWN_FIELDS` / `CUSTOM_FIELDS` | 1082–1219 | **Single source of truth for the field list**, derived from `FofaResult`; `_validate_web_field_categories()` runs at import and fails fast if web categories drift from the field set. To add a FOFA field: extend `FofaResult` + categorize in `WEB_FIELD_CATEGORIES` (both in this file) |
| Icon 提取与 icon_hash | 1221–1551 | `IconExtractError`, `_murmur3_32` (1239, pure-Python MurmurHash3 x86_32 — keep zero-dependency), `favicon_hash` (1277, Shodan/FOFA convention: mmh3 of newline-wrapped base64), `build_icon_query` (1286), `_IconLinkParser` (1295), `resolve_icon` (1469, targets: URL / local file / raw hash), `resolve_icon_cached` (1535, backs Web `/api/icon`, file input disabled) |
| `FofaClient` | 1552–1906 | `search()` (1593) for ≤10000 single-request; `search_all_efficient()` (1672) for deep export via `before` time-cursor; both take `cancel_check` so Web UI cancel interrupts rate-limit/retry sleeps (`_sleep_interruptible`) |
| `build_url`, `dedup_results` | 1912, 1959 | URL assembly from host/port/protocol; dedup by field tuple, including `_extra` custom fields |
| `Exporter` | 1994–2108 | `export_csv`/`export_json`/`export_txt`; field filtering, `_extra` handling; default columns = `ALL_FIELD_NAMES` |
| Export task system + web access log | 2524–2953 | `ExportTask` (2629) + `_export_tasks` dict; background TTL cleanup thread `start_export_cleanup_timer` (2567, 60s interval, TTL anchored to `finished_at`); terminal transitions go through `_finish_export_task` (2598); task threads spawn via `_start_export_thread` (2613), which finishes the task as error if `thread.start()` fails (no ghost running tasks); `_has_running_export_task()` (2583, caller must hold `_export_lock`) is checked and the task registered in one critical section in `/api/export` & `/api/batch`; cancel flips `cancelled`/`discard` and raises `KeyboardInterrupt`; web export files go through `_write_web_exports` (2810); `_redact_sensitive` (2655), `_request_body_length` (2777) and the aligned `[web]` access-log helpers live here too |
| Web 访问鉴权 | 2955–3082 | Optional Web UI auth driven by `config.json` `web_auth`. `WEB_AUTH_COOKIE_NAME` (2960) + `WEB_AUTH_TOKEN_TTL` (2961, 30 days); `generate_web_auth_token` (2964) / `verify_web_auth_token` = `{issued}.{HMAC-SHA256(secret, issued)}` — no server-side session store, **rotating `secret` instantly revokes every issued cookie** (config hot-reload). `WEB_LOGIN_HTML` (3044) is a standalone inline login page (Chinese UI, **no `__` placeholders**, never passed through `render_web_html()`). `enabled=true` with empty `secret` is fail-closed: no key can log in, login page guides the user to config. **Login rate limiting**: global sliding-window counter (`_login_cooldown_remaining` 3023: 5 fails per 60s window → 60s cooldown) — throttled requests answer 429 fast (no per-request sleep in cooldown, so parallel connections neither bypass the throttle nor hold threads); successful login resets the counter |
| `FofaWebHandler` | 3084–3807 | `http.server.BaseHTTPRequestHandler`; **`_web_auth_check` (3221) gates every request** — enabled + unauthenticated: `GET /` serves `WEB_LOGIN_HTML`, everything else 401 JSON; `do_GET` (3317) / `do_POST` (3337) call it first, POST allowlist: `/api/auth/login` (`_handle_login`, 3241 — constant-time bytes compare, 1s delay per failed key, global cooldown 429), `/api/auth/logout` (`_handle_logout`, 3305 — clears cookie). Routes `/api/search`, `/api/icon` (`_handle_icon`), `/api/export`, `/api/batch`, `/api/progress`, `/api/info`, `/api/update`, `GET /api/export/download`, `POST /api/progress/cancel`; threads via `_FofaHTTPServer` (3871). Access log (helpers in 2524–2953 block): aligned `[web] time method path status ip` line, status column padded to width 7 so `dropped` keeps the IP aligned; omits successful `/api/progress` polls, browser probes, and repeated `GET /` from the same client within 30s; auth login/logout attempts are logged with client IP; batch accepts per-target `max_size`. `/api/batch` runs targets through `normalize_batch_targets` before expand. An all-`FofaAPIError` batch with no rows finishes `error`; a mix of failures and rows sets `partial`. Client disconnects (`ConnectionError` in `handle_one_request`, 3119) log one `dropped` line — skipped when the request already recorded a status (flag set in `log_request`, 3089) so served requests aren't logged twice |
| `FofaWebServer` | 3890–3964 | Binds `--host` address (default `127.0.0.1`), auto-probes port from 17380; explicit `--host` disables browser auto-open. Startup prints auth status (enabled → key source hint; enabled without secret → yellow warning) and keeps the non-loopback warning only when auth is not effectively active. Helpers above it: `_find_available_port` (3810), `_open_browser` (3829, WSL/SSH/headless handling), `_lan_ips` (3858). Calls `announce_update(blocking=False)` after the startup banner |
| `main()` | 3970 | argparse; first switches non-TTY stdout to line buffering (docker logs / 重定向下横幅与启动信息即时落盘); web mode when `--web` or no query + no batch file + no `-c`/`--check` + no `--icon`; CLI calls `announce_update(blocking=True)` after the banner unless `--no-update-check` |
| `build_parser`, `handle_single_mode`, `handle_batch_mode`, `handle_icon_mode`, `normalize_batch_targets`, `load_batch_targets`, `run_batch_search`, `export_results` | — | CLI path: parse args, run single / batch / icon mode, load the batch file, run the batch, write the export. `normalize_batch_targets` (4053) trims lines and drops blanks and `#` comments for both the CLI file and Web `/api/batch` |

**Time-cursor strategy (`search_all_efficient`):** probe with `size=1` → loop querying `before` in windows of at most 10000 rows (1000-row tail floor when the target is above 10000); the next cursor is `min(lastupdatetime) - 1s` → dedup by host → stop when a page is short of the requested size, the fill/max target is met, or the batch has no parseable `lastupdatetime`. When the probed total is greater than 0, the target after the fill/max math is at least 1 (`int(1 * 0.8)` no longer skips the fetch).

## Editing the Web UI

The Web UI HTML/CSS/JS is a single raw string literal (`WEB_HTML_TEMPLATE`, lines 120–533). This has important consequences:

- **No syntax highlighting or editor support** — validate JS by running `py_compile` then testing in browser.
- **No external assets** — all CSS and JS inline, zero dependencies, Chinese UI.
- **Placeholders** `__APP_VERSION__` / `__GITHUB_URL__` / `__FIELD_CATEGORIES_JSON__` / `__DEFAULT_FIELDS_JSON__` are replaced by `render_web_html()` — don't use double-underscore IDs elsewhere in the template (collision risk). The update-badge script intentionally contains `__GITHUB_URL__/releases/` so the link prefix stays tied to `GITHUB_URL`. The separate `WEB_LOGIN_HTML` login page deliberately uses **no placeholders** it is served verbatim.
- **All `onclick` handlers use `&quot;`** for quotes inside the Python string, not escaped single quotes.
- Frontend state lives in JS module-level vars (`currentMode`, `currentResults`, `currentTotal`, `excludedFilters`, `exportPollTimer`, etc.) — there is no framework. `currentTotal` is the FOFA total from the search payload; sort and exclude re-render with it instead of `currentResults.length`.

## Config and secrets

- `config.json` (gitignored) lives next to the script/exe. In Nuitka onefile mode, located via `NUITKA_ONEFILE_DIRECTORY` env var (NOT `NUITKA_ONEFILE_PARENT`, which is a PID, not a path — v1.2.1 had this bug).
- `config.example.json` is the tracked template (whitelisted in `.gitignore` via `!config.example.json`).
- **Never commit real API keys.** A real key leaked into git history previously — always verify `config.json` is not staged before committing.
- Web UI hot-reloads config: editing `config.json` takes effect on next request, no server restart needed (`ConfigManager.get_client()`). This includes `web_auth` — flipping `enabled`, rotating `secret` (revokes all issued cookies instantly), or fixing an empty `secret` all take effect on the next request.

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
