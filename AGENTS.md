# AGENTS.md

Guidance for agents working in this repository.

## Project overview

`fofatoto` is a single-file, zero-dependency Python tool for querying the FOFA network-space search engine. CLI + built-in local Web UI, bulk export, batch queries, field customization, dedup, multi-format output (CSV/JSON/TXT). Compiled to native binaries via Nuitka.

**No third-party dependencies** — stdlib only. `pyproject.toml` declares `dependencies = []`. Requires Python ≥ 3.11.

## Commands

```bash
# Syntax check — the ONLY validation available (no test suite exists)
python -m py_compile fofatoto.py

# Run CLI
python fofatoto.py "domain=baidu.com" -l 10

# Run Web UI (auto-opens browser, listens on 127.0.0.1, probes from port 17380)
python fofatoto.py -w

# Build binary (requires: pip install nuitka zstandard; Linux also needs patchelf + python3-dev)
python -m nuitka --onefile --lto=yes --static-libpython=yes --remove-output \
  --assume-yes-for-downloads --python-flag=no_site,no_docstrings \
  --noinclude-pytest-mode=nofollow --noinclude-setuptools-mode=nofollow \
  --noinclude-unittest-mode=nofollow --noinclude-pydoc-mode=nofollow \
  --output-filename=fofatoto fofatoto.py
```

There is no test framework, no linter config, no formatter config. `py_compile` is the only verification step.

## Architecture

Everything lives in `fofatoto.py` (~2750 lines). No package structure — designed as a self-contained Nuitka-compilable script.

**Data flow:** `config.json` → `ConfigManager` → `FofaClient` → `FofaResult` dataclass → `Exporter` (CSV/JSON/TXT)

**Key components (current line numbers):**

| Component | Lines | Notes |
|-----------|-------|-------|
| `APP_VERSION`, `DEFAULT_CONFIG`, `DEFAULT_FIELDS` | 33–48 | Module-level constants |
| `WEB_HTML_TEMPLATE` | 85–470 | **The entire Web UI is an inline HTML/CSS/JS string** with `__APP_VERSION__`, `__GITHUB_URL__`, `__DEFAULT_FIELDS_JSON__` placeholders substituted by `render_web_html()` (473) |
| `ConfigManager` | 487–575 | `get_client()` (552) supports **hot-reload** — re-reads `config.json` each request, caches `FofaClient` by `(url, key)` signature; no restart needed |
| `FofaResult` dataclass | 590–635 | 25+ FOFA fields; `_extra` dict captures unknown API fields |
| `FofaClient` | 704–875 | `search()` for ≤10000 single-request; `search_all_efficient()` for deep export via `before` time-cursor |
| `build_url`, `dedup_results` | 1123, 1170 | URL assembly from host/port/protocol; dedup by field tuple |
| `Exporter` | 1210–1340 | `export_csv`/`export_json`/`export_txt`; field filtering, `_extra` handling |
| `FofaWebHandler` | 1910–2475 | `http.server.BaseHTTPRequestHandler`; routes `/api/search`, `/api/export`, `/api/batch`, `/api/progress`, `/api/info`; threads via `ThreadingMixIn` |
| `FofaWebServer` | 2492–2530 | Binds 127.0.0.1, auto-probes port from 17380 |
| `main()` | 2534 | argparse; web mode when `--web` or no query + no batch file |

**Time-cursor strategy (`search_all_efficient`):** probe with `size=1` → loop querying `before="<lastupdatetime>"` in 10000-result windows → dedup by host → stop when batch <10000 or fill_percent reached.

## Editing the Web UI

The Web UI HTML/CSS/JS is a single raw string literal (`WEB_HTML_TEMPLATE`, lines 85–470). This has important consequences:

- **No syntax highlighting or editor support** — validate JS by running `py_compile` then testing in browser.
- **No external assets** — all CSS and JS inline, zero dependencies, Chinese UI.
- **Placeholders** `__APP_VERSION__` / `__GITHUB_URL__` / `__DEFAULT_FIELDS_JSON__` are replaced by `render_web_html()` — don't use double-underscore IDs elsewhere in the template (collision risk).
- **All `onclick` handlers use `&quot;`** for quotes inside the Python string, not escaped single quotes.
- Frontend state lives in JS module-level vars (`currentMode`, `currentResults`, `excludedFilters`, `exportPollTimer`, etc.) — there is no framework.

## Config and secrets

- `config.json` (gitignored) lives next to the script/exe. In Nuitka onefile mode, located via `NUITKA_ONEFILE_DIRECTORY` env var (NOT `NUITKA_ONEFILE_PARENT`, which is a PID, not a path — v1.2.1 had this bug).
- `config.example.json` is the tracked template (whitelisted in `.gitignore` via `!config.example.json`).
- **Never commit real API keys.** A real key leaked into git history previously — always verify `config.json` is not staged before committing.
- Web UI hot-reloads config: editing `config.json` takes effect on next request, no server restart needed (`ConfigManager.get_client()`).

## `gan-harness/`

A design-iteration harness (GAN-style generator/evaluator workflow) used to polish the Web UI field selector. Contains `spec.md`, `eval-rubric.md`, `eval-iteration-*.md`. Gitignored. The current chip-based field selector in the Web UI originated from this process. Safe to ignore for functional changes; useful context if touching the field selector UX.

## Version sync

`APP_VERSION` (fofatoto.py:33) is the source of truth. When bumping versions, also update:
- `pyproject.toml` `version` field
- `uv.lock` package version
- `CHANGELOG.md` (add new version heading)

These are currently out of sync (`pyproject.toml`/`uv.lock` stuck at `1.2.1` while `APP_VERSION` is `1.3.0`).

## Branch and changelog rules

- **Always work on `main`.** Do not create or switch branches.
- **Keep `CHANGELOG.md` updated.** Release-log style: version headings (`## vX.Y.Z - YYYY-MM-DD`), categorized changes (新增/修复/优化/文档/其他).
- Don't bump the version number for every minor edit — batch related changes into one version entry.

## CI/CD

`.github/workflows/build.yml` triggers on tag push (`v*`) or manual dispatch:
- Windows amd64, Linux amd64/arm64 (Debian bookworm container), macOS amd64/arm64
- All built via Nuitka `--onefile --lto=yes`
- Release job (`softprops/action-gh-release`) collects artifacts, names per platform: `fofatoto.exe`, `fofatoto`, `fofatoto_arm64`, `fofatoto_mac`, `fofatoto_mac_arm64`
