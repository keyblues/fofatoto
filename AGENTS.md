# AGENTS.md

Guidance for agents working in this repository.

## Project overview

`fofatoto` is a single-file, zero-dependency Python tool for querying the FOFA network-space search engine. CLI + built-in local Web UI, bulk export, batch queries, field customization, dedup, icon-hash same-icon lookup (`--icon`), multi-format output (CSV/JSON/TXT). Compiled to native binaries via Nuitka.

**No third-party dependencies** — stdlib only. `pyproject.toml` declares `dependencies = []`. Requires Python ≥ 3.11.

## Commands

```bash
# Syntax check + unit tests (stdlib unittest, 277 tests, no network calls)
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

Everything lives in `fofatoto.py` (~4501 lines) plus `test_fofatoto.py`. No package structure — designed as a self-contained Nuitka-compilable script.

**Data flow:** `config.json` → `ConfigManager` → `FofaClient` → `FofaResult` dataclass → `Exporter` (CSV/JSON/TXT)

**Key components (current line numbers):**

| Component | Lines | Notes |
|-----------|-------|-------|
| `APP_VERSION`, `DEFAULT_CONFIG`, `DEFAULT_FIELDS` | 42–68 | Module-level constants; `DEFAULT_CONFIG` ships the `web_auth` block (`enabled`/`secret`, default off) so fresh `config.json` files and the Web UI config-guidance template carry it |
| `WEB_FIELD_CATEGORIES`, `WEB_HTML_TEMPLATE` | 109–540 | **The entire Web UI is an inline HTML/CSS/JS string** with `__APP_VERSION__`, `__GITHUB_URL__`, `__FIELD_CATEGORIES_JSON__`, `__DEFAULT_FIELDS_JSON__` placeholders substituted by `render_web_html()` (543); field-selector categories live in `WEB_FIELD_CATEGORIES` and are injected into the template |
| Browser preview cache | Inline JS: `openPreviewCache` through `initPreviewCache`, `doInstantSearch`; backend `_preview_cache_scope`, `GET /api/config` | IndexedDB `fofatoto_preview_cache` / `queries`; TTL 24h, 50 entries, 50 MiB total, 5 MiB per entry (UTF-8 JSON Blob + key bytes, excludes browser overhead). Key = exact trimmed query + field order + size + full + hashed `(base_url, key)` account scope. Startup / 60s expiry cleanup and expiry/LRU eviction before writes; metadata-only compound-index cursor avoids reading all result Blobs. Cache hit avoids `/api/search`; `/api/config` is local-only and auth-gated. Clear/toggle increments a generation so older in-flight responses cannot refill a cleared cache. Deep/batch exports never enter this store, and file downloads send `Cache-Control: no-store` |
| `ConfigManager` | 561–687 | `_app_config_dir()` (561) resolves the config dir (shared with `_update_cache_file`); `get_client()` (676) supports **hot-reload** — re-reads `config.json` via `load()` on each call and returns a new `FofaClient`; no restart needed. `load()` serializes concurrent reloads so config fields and the cache key cannot be published by different readers, and short-circuits on a `(path, mtime_ns, size)` cache key — Web requests call it constantly (auth gate, `get_client`, `public_status`, 1s progress polls), and only re-read when the file actually changed; parse failures never cache, so they retry next call. `_load_web_auth` parses the optional `web_auth` object (missing / non-dict → disabled); `public_status()` also reports `web_auth_enabled` (never the secret) and `official` (only `fofa.info` / `en.fofa.info` may show the account profile) |
| Update check | 689–1055 | `fetch_latest_release` (830) hits GitHub Releases; `announce_update` (1022) for CLI/Web startup; `snapshot_update` (1039) backs `GET /api/update`. Success cached 12h, failure 1h, in `.fofatoto_update.json` next to the executable (path via `_app_config_dir()`). `--no-update-check` / `FOFATOTO_NO_UPDATE_CHECK=1` disables it |
| `FofaResult` dataclass | 1057–1101 | 28 FOFA fields; `_extra` dict captures unknown API fields |
| `ALL_FIELD_NAMES` / `KNOWN_FIELDS` / `CUSTOM_FIELDS` | 1109–1258 | **Single source of truth for the field list**, derived from `FofaResult`; `_validate_web_field_categories()` runs at import and fails fast if web categories drift from the field set. To add a FOFA field: extend `FofaResult` + categorize in `WEB_FIELD_CATEGORIES` (both in this file) |
| 进度事件常量 | 1138–1147 | `EVENT_*` names shared by the producer (`search_all_efficient`) and all three consumers (console callback, web export/batch callbacks) — don't spell event names as bare strings |
| Icon 提取与 icon_hash | 1262–1906 | `IconExtractError`, `_murmur3_32` (1280, pure-Python MurmurHash3 x86_32 — keep zero-dependency), `favicon_hash` (1318, Shodan/FOFA convention: mmh3 of newline-wrapped base64), `build_icon_query` (1327), `_IconLinkParser` (1336), `_fetch_url` (1706). Icon fetch allows only `http`/`https` on the initial URL and every redirect hop; resolves the host before each connect and refuses non-global addresses (loopback, private, link-local, reserved, unspecified, multicast, and `not is_global`, including `169.254.169.254` and IPv6 equivalents, plus 6to4 / Teredo / NAT64). Connects to the checked IP (no second DNS lookup) and ignores `HTTP(S)_PROXY`. TLS certificates and hostnames are verified. CLI `--icon` and `POST /api/icon` only see `图标抓取失败` for every fetch failure — blocked address, timeout, refusal, HTTP status, empty body, HTML parse failure, no usable icon, a non-http(s) initial URL, and a body over either size cap — with no final or redirect URL in the message. stderr logs scheme, host, port, and a reason label. `resolve_icon` (1823, targets: URL / local file / raw hash), `resolve_icon_cached` (1892, backs Web `/api/icon`, `allow_file=False`; HTML 2MB / icon 5MB caps unchanged) |
| `FofaClient` | 1909–2268 | `search()` (1950) for ≤10000 single-request; `search_all_efficient()` (2031) for deep export via `before` time-cursor; both take `cancel_check` so Web UI cancel interrupts rate-limit/retry sleeps (`_sleep_interruptible`); progress events are emitted with the `EVENT_*` constants; every successful `search()` feeds the local quota ledger via `_note_quota_used` (see 账户信息缓存 row) |
| `build_url`, `dedup_results` | 2271, 2318 | URL assembly from host/port/protocol; dedup by field tuple, including `_extra` custom fields |
| `Exporter` | 2353–2467 | `export_csv`/`export_json`/`export_txt`; field filtering, `_extra` handling; default columns = `ALL_FIELD_NAMES`. CSV/JSON stream row-by-row via `_iter_dict_data` (2375) — never materialize the full dict list; JSON output is byte-identical to `json.dumps(list, indent=2)`; `_extra` dynamic columns are ordered by first appearance |
| Export task system + web access log | 2884–3313 | `ExportTask` (2989) + `_export_tasks` dict; background TTL cleanup thread `start_export_cleanup_timer` (2927, 60s interval, TTL anchored to `finished_at`); terminal transitions go through `_finish_export_task` (2958); task threads spawn via `_start_export_thread` (2973), which finishes the task as error if `thread.start()` fails (no ghost running tasks); `_has_running_export_task()` (2943, caller must hold `_export_lock`) is checked and the task registered in one critical section in `/api/export` & `/api/batch`; cancel flips `cancelled`/`discard` and raises `KeyboardInterrupt`; web export files go through `_write_web_exports` (3170); `_redact_sensitive` (3015), `_request_body_length` (3137) and the aligned `[web]` access-log helpers live here too |
| 账户信息缓存与本地计次 | 3315–3435 | `/api/info` no longer hits the FOFA account API per request (it shares the search rate limit, so bursts made the top-right status fail constantly). Process cache of the last successful `get_usage` (success TTL 10 min, failure backoff 1 min); `_note_quota_used` accepts returned rows only when the query client matches the cached `(base_url, key)` (queries finishing for a previous account are ignored) and `_account_cached_payload` decrements relay `remain_api_query` by returned rows; official monthly query/data limits and F-point balances keep the account API values (`local_used`, `info_age_seconds` remain in the payload); when the cache is stale AND idle (`_web_idle_for_account_refresh` = no running export/batch task) a background thread refreshes (`_start_account_info_refresh`, inflight-guarded) and the response carries `pending_refresh` — the frontend re-polls every 2s until refresh completes; only the latest account fetch request may publish success/failure to the cache (its request ID is reserved before starting a background thread); switching accounts (base_url/key change) invalidates the cache and refetches synchronously; the response is built from the pre-refresh snapshot so the new value never leaks into the same response. First-ever fetch is synchronous |
| Web 访问鉴权 | 3437–3564 | Optional Web UI auth driven by `config.json` `web_auth`. `WEB_AUTH_COOKIE_NAME` (3442) + `WEB_AUTH_TOKEN_TTL` (3443, 30 days); `generate_web_auth_token` (3446) / `verify_web_auth_token` = `{issued}.{HMAC-SHA256(secret, issued)}` — no server-side session store, **rotating `secret` instantly revokes every issued cookie** (config hot-reload). `WEB_LOGIN_HTML` (3526) is a standalone inline login page (Chinese UI, **no `__` placeholders**, never passed through `render_web_html()`). `enabled=true` with empty `secret` is fail-closed: no key can log in, login page guides the user to config. **Login rate limiting**: global sliding-window counter (`_login_cooldown_remaining` 3505: 5 fails per 60s window → 60s cooldown) — throttled requests answer 429 fast (no per-request sleep in cooldown, so parallel connections neither bypass the throttle nor hold threads); successful login resets the counter |
| `FofaWebHandler` | 3566–4336 | `http.server.BaseHTTPRequestHandler`; routing via class-level tables `_GET_ROUTES` / `_POST_ROUTES` (3573) that dispatch **by method name** (`getattr`) so instance-level replacement/mocks keep working; `_AUTH_EXEMPT_POST` (3589) centralizes the POST auth bypass (login/logout). **`_web_auth_check` (3734) gates every request** — enabled + unauthenticated: `GET /` serves `WEB_LOGIN_HTML`, everything else 401 JSON; `do_GET` (3833) / `do_POST` (3846) call it first (POST before route lookup, so unknown paths still get 401 when unauthenticated), then dispatch `/api/auth/login` (`_handle_login`, 3754 — constant-time bytes compare, 1s delay per failed key, global cooldown 429), `/api/auth/logout` (`_handle_logout`, 3818 — clears cookie), `/api/search`, `/api/icon` (`_handle_icon`), `/api/export`, `/api/batch`, `/api/progress` (GET, task state), `/api/info` (GET, cached account info — see 账户信息缓存 row), `/api/update`, `GET /api/export/download` (streams via `_send_file` in 64KB chunks), `POST /api/progress/cancel`; threads via `_FofaHTTPServer` (4399). Access log (helpers in 2884–3313 block): aligned `[web] time method path status ip` line, status column padded to width 7 so `dropped` keeps the IP aligned; omits successful `/api/progress` polls, browser probes, and repeated `GET /` from the same client within 30s; auth login/logout attempts are logged with client IP; batch accepts per-target `max_size`. `/api/batch` runs targets through `normalize_batch_targets` before expand. An all-`FofaAPIError` batch with no rows finishes `error`; a mix of failures and rows sets `partial`. Client disconnects (`ConnectionError` in `handle_one_request`, 3621) log one `dropped` line — skipped when the request already recorded a status (flag set in `log_request`, 3591) so served requests aren't logged twice |
| `FofaWebServer` | 4418–4492 | Binds `--host` address (default `127.0.0.1`), auto-probes port from 17380; explicit `--host` disables browser auto-open. Startup prints auth status (enabled → key source hint; enabled without secret → yellow warning) and keeps the non-loopback warning only when auth is not effectively active. Helpers above it: `_find_available_port` (4338), `_open_browser` (4357, WSL/SSH/headless handling), `_lan_ips` (4386). Calls `announce_update(blocking=False)` after the startup banner |
| `main()` | 4498 | argparse; first switches non-TTY stdout to line buffering (docker logs / 重定向下横幅与启动信息即时落盘); web mode when `--web` or no query + no batch file + no `-c`/`--check` + no `--icon`; CLI calls `announce_update(blocking=True)` after the banner unless `--no-update-check` |
| `build_parser`, `handle_single_mode`, `handle_batch_mode`, `handle_icon_mode`, `normalize_batch_targets`, `load_batch_targets`, `run_batch_search`, `export_results` | — | CLI path: parse args, run single / batch / icon mode, load the batch file, run the batch, write the export. `normalize_batch_targets` (4581) trims lines and drops blanks and `#` comments for both the CLI file and Web `/api/batch` |

**Time-cursor strategy (`search_all_efficient`):** probe with `size=1` → loop querying `before` in windows of at most 10000 rows (1000-row tail floor when the target is above 10000); the next cursor is `min(lastupdatetime) - 1s` → dedup by host → stop when a page is short of the requested size, the fill/max target is met, or the batch has no parseable `lastupdatetime`. When the probed total is greater than 0, the target after the fill/max math is at least 1 (`int(1 * 0.8)` no longer skips the fetch).

## Editing the Web UI

The Web UI HTML/CSS/JS is a single raw string literal (`WEB_HTML_TEMPLATE`, lines 122–540). This has important consequences:

- **No syntax highlighting or editor support** — validate JS by running `py_compile` then testing in browser.
- **No external assets** — all CSS and JS inline, zero dependencies, Chinese UI.
- **Placeholders** `__APP_VERSION__` / `__GITHUB_URL__` / `__FIELD_CATEGORIES_JSON__` / `__DEFAULT_FIELDS_JSON__` are replaced by `render_web_html()` — don't use double-underscore IDs elsewhere in the template (collision risk). The update-badge script intentionally contains `__GITHUB_URL__/releases/` so the link prefix stays tied to `GITHUB_URL`. The separate `WEB_LOGIN_HTML` login page deliberately uses **no placeholders** it is served verbatim.
- **All `onclick` handlers use `&quot;`** for quotes inside the Python string, not escaped single quotes.
- Frontend state lives in JS module-level vars (`currentMode`, `currentResults`, `currentTotal`, `instantSearchRequestId`, `excludedFilters`, `exportPollTimer`, etc.) — there is no framework. `currentTotal` is the FOFA total from the search payload; sort and exclude re-render with it instead of `currentResults.length`. Instant-search responses and errors update the result area only when their request ID is current. Successful searches (including superseded responses) and terminal export/batch polls refresh the cached account display.
- Browser query cache stores only successful instant-preview payloads (including zero rows). Settings allow disabling/clearing it; clear preserves the current table, query history, and cumulative hit statistics. `重新查询` appears only after a cache hit, immediately after `缓存已命中，命中率 xx%`; it removes the matching entry and bypasses lookup, then hides. Hits / ordinary cache lookups are persisted in localStorage `fofa_preview_cache_stats`, displayed in settings, and rounded to one decimal at most. Forced refreshes, disabled-cache queries, and superseded lookups do not affect the statistics. The scope in a successful `/api/search` payload belongs to its actual query client, so a config change after `/api/config` does not save results under the wrong account. Oversized entries or unavailable storage leave query results visible. IndexedDB is scoped to the browser origin; a different Web port has a separate cache.
- **Keep the pending-query box in its original position below the results area.** `queryLoading` shows the blue `查询中...` box only during instant queries and hides when they finish. `showMessage` routes `info` to this box and errors to plain-text `queryFeedback` next to the query input; `clearMessage` hides both. Do not put cache-clear or other success notifications in the bottom query box. Cache clear is silent and only updates the settings summary; it preserves cumulative hits and lookup counts.

Account quota units remain distinct: `_local_quota_used` counts returned rows for relay total-balance estimates, while `_local_query_count` counts successful `search()` calls for relay `today_remaining` (including probes and zero-row successes; a successful retry counts once). Both marks reset on a successful account fetch, and both counters ignore queries from a different cached account. `SearchStats.total_quota_used` reports returned rows for single searches; deep searches include probe quota. Web batch progress adds the completed targets' quota to the current target, and final quota sums all completed targets.

## Config and secrets

- By default, `config.json` (gitignored) lives next to the script/exe. `--config FILE` selects another file for CLI or Web UI; relative paths use the working directory, and Web hot-reload follows the selected file. In Nuitka onefile mode, the default directory comes from `NUITKA_ONEFILE_DIRECTORY` (NOT `NUITKA_ONEFILE_PARENT`, which is a PID, not a path — v1.2.1 had this bug).
- `config.example.json` is the tracked template (whitelisted in `.gitignore` via `!config.example.json`).
- **Never commit real API keys.** A real key leaked into git history previously — always verify `config.json` is not staged before committing.
- Web UI hot-reloads config: editing `config.json` takes effect on next request, no server restart needed (`ConfigManager.get_client()`). This includes `web_auth` — flipping `enabled`, rotating `secret` (revokes all issued cookies instantly), or fixing an empty `secret` all take effect on the next request.

## Version sync

`APP_VERSION` (fofatoto.py:42) is the source of truth and always reflects the last **released** version. Unreleased changes go under a `## Unreleased` heading in `CHANGELOG.md` — never invent a version number for unpublished work. Only at release time: pick the version, rename the heading to `## vX.Y.Z - YYYY-MM-DD`, and update all three together:
- `APP_VERSION` in fofatoto.py
- `pyproject.toml` `version` field
- `uv.lock` package version

Currently all three are synced at `1.10.0` for release preparation (`CHANGELOG.md`: v1.10.0, 2026-11-05). The latest published release remains v1.9.0 (2026-10-16) until v1.10.0 is tagged.

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
