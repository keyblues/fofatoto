# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project overview

`fofatoto` is a single-file, zero-dependency Python tool for querying the FOFA network-space search engine. It supports CLI usage, local Web UI, bulk export, batch queries, field customization, deduplication, and multi-format output (CSV/JSON/TXT). It is compiled to native binaries via Nuitka for distribution.

## Commands

```bash
# Syntax check (only validation available — no test suite)
python3 -m py_compile fofatoto.py

# Run locally
python fofatoto.py "domain=baidu.com" -l 10

# Run with custom config
NUITKA_ONEFILE_PARENT=/path/to/config_dir python fofatoto.py "domain=baidu.com"

# Build binaries (requires nuitka, zstandard; Linux needs patchelf + python3-dev)
python3 -m nuitka --onefile --lto=yes --static-libpython=yes --remove-output \
  --assume-yes-for-downloads --python-flag=no_site,no_docstrings \
  --noinclude-pytest-mode=nofollow --noinclude-setuptools-mode=nofollow \
  --noinclude-unittest-mode=nofollow --noinclude-pydoc-mode=nofollow \
  --output-filename=fofatoto fofatoto.py
```

## Architecture

The entire tool is in `fofatoto.py`. There is no package structure — it's designed as a self-contained script compilable by Nuitka.

**Data flow:** `Config` → `FofaClient` (API calls) → `FofaResult` (dataclass) → export functions (CSV/JSON/TXT)

**Key components (in file order):**

| Section | Lines | Purpose |
|---------|-------|---------|
| Config + `get_config_dir()` | 49–119 | Loads `config.json`; Nuitka onefile-aware path resolution via `NUITKA_ONEFILE_PARENT` env var |
| `FofaResult` dataclass | 124–169 | Maps all 25+ FOFA fields; `_extra` dict captures unknown API fields |
| `FofaClient` | - | Two modes: `search()` for single-request queries (≤10000) and `search_all_efficient()` for deep export using a `before` time-cursor strategy |
| Export functions | 456–643 | `export_csv`, `export_json`, `export_txt` — each handles dedup, field filtering, and URL construction |
| `main()` + CLI/Web | - | argparse-based CLI and built-in Web UI server |

**Time-cursor strategy (`search_all_efficient`):**
1. Probe with `size=1` to get total count
2. Loop: query with `before="<lastupdatetime>"` to fetch the next 10000-result window
3. Deduplicate by host across batches
4. Stop when a batch returns <10000 results or target fill percentage is reached

**`config.json` location**: Same directory as the script/executable. In Nuitka onefile mode, set `NUITKA_ONEFILE_PARENT` to point at the config directory.

## Branch and changelog rules

- **Always work on `main` branch.** Do not create or switch to other branches.
- **Keep `CHANGELOG.md` updated.** It follows a release-log style with version headings, dates, and categorized changes (新增/修复/优化/文档/其他).

## CI/CD

GitHub Actions (`.github/workflows/build.yml`) builds on tag push (`v*`) or manual dispatch:
- Windows amd64, Linux amd64/arm64, macOS amd64/arm64
- All compiled via Nuitka `--onefile --lto=yes`
- Release job collects artifacts and creates a GitHub Release via `softprops/action-gh-release`
