#!/usr/bin/env python3
"""
FOFA 查询工具 - 单文件
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import http.server
import ipaddress
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import parse_qs, quote, unquote_to_bytes, urljoin, urlparse

# ============ Banner ============

APP_VERSION = "1.6.0"
GITHUB_URL = "https://github.com/keyblues/fofatoto"
DEFAULT_CONFIG = {"url": "https://fofa.info", "key": "your-fofa-key-here"}
DEFAULT_WEB_PORT = 17380
DEFAULT_FIELD_LIST = [
    "host",
    "ip",
    "port",
    "protocol",
    "domain",
    "title",
    "server",
    "country",
    "city",
]
DEFAULT_FIELDS = ",".join(DEFAULT_FIELD_LIST)

# 已知第三方 FOFA 中转站的账户信息查询 API
# 键为域名（后缀匹配），值为 URL 模板（{base_url} / {key} 占位符）
# 未匹配时回退到标准 FOFA /api/v1/info/my 接口。
RELAY_INFO_APIS = {
    "fafaapi.info": "{base_url}/fofaapi/v1/validate-key?key={key}",
}

BANNER = rf"""  _____ ___  _____ _      _____ ___ _____ ___
 |  ___/ _ \|  ___/ \    |_   _/ _ \_   _/ _ \
 | |_ | | | | |_ / _ \     | || | | || || | | |
 |  _|| |_| |  _/ ___ \    | || |_| || || |_| |
 |_|   \___/|_|/_/   \_\   |_| \___/ |_| \___/

                        FOFA Query Tool v{APP_VERSION}
                        {GITHUB_URL}"""

INTERACTIVE_OUTPUT = sys.stdout.isatty()
WINDOWS_COLOR_TERMINAL = bool(
    os.environ.get("WT_SESSION")
    or os.environ.get("ANSICON")
    or os.environ.get("TERM_PROGRAM")
    or os.environ.get("FORCE_COLOR")
    or os.environ.get("ConEmuANSI") == "ON"
)
COLOR_ENABLED = (
    not os.environ.get("NO_COLOR")
    and (os.environ.get("FORCE_COLOR") or (INTERACTIVE_OUTPUT and (os.name != "nt" or WINDOWS_COLOR_TERMINAL)))
)

GREEN = "\033[92m" if COLOR_ENABLED else ""
YELLOW = "\033[93m" if COLOR_ENABLED else ""
RED = "\033[91m" if COLOR_ENABLED else ""
CYAN = "\033[96m" if COLOR_ENABLED else ""
BOLD = "\033[1m" if COLOR_ENABLED else ""
RESET = "\033[0m" if COLOR_ENABLED else ""

def highlight(text: str, value: str) -> str:
    return f"{text}: {BOLD}{value}{RESET}"


# ============ Web UI 模板 ============

# Web UI 字段选择器的字段分组（分类名 -> 字段列表），经 __FIELD_CATEGORIES_JSON__
# 占位符注入前端。字段全集以 FofaResult 为准（KNOWN_FIELDS | CUSTOM_FIELDS），
# 模块加载时 _validate_web_field_categories() 校验分组与之完全一致。
WEB_FIELD_CATEGORIES: list[dict] = [
    {"name": "核心", "fields": ["host", "ip", "port", "protocol", "domain"]},
    {"name": "服务", "fields": ["title", "server", "product", "version"]},
    {
        "name": "位置",
        "fields": ["country", "city", "region", "country_name", "latitude", "longitude"],
    },
    {"name": "网络", "fields": ["asn", "org", "base_protocol", "link", "url"]},
    {"name": "证书", "fields": ["cert", "jarm", "icp", "cname", "header", "banner"]},
    {"name": "时间", "fields": ["lastupdatetime"]},
    {"name": "系统", "fields": ["os", "product_category"]},
]

WEB_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FOFATOTO</title>
<style>
:root{--primary:#1a365d;--primary-dark:#0f2440;--primary-light:#2c5282;--accent:#3182ce;--accent-hover:#2b6cb0;--accent-border:rgba(49,130,206,0.3);--bg:#e6e9ee;--card-bg:#fff;--text:#1a202c;--text-secondary:#64748b;--border:#d0d5dd;--table-header:#f1f5f9;--table-stripe:#f4f7fb;--success:#16a34a;--danger:#dc2626;--warning:#d97706;--chip-bg:#e8f0fe;--chip-border:#c5d9f0}
*{box-sizing:border-box;margin:0;padding:0}
html{height:100%;overflow:hidden}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--text);font-size:13px;line-height:1.5;height:100dvh;overflow:hidden}
.header{background:var(--primary-dark);color:#fff;padding:0 28px;min-height:52px;display:flex;align-items:center;justify-content:space-between;gap:16px;font-size:13px;border-bottom:2px solid var(--primary)}
.header .brand{display:flex;align-items:baseline;gap:8px;min-width:0}
.header .logo{font-weight:700;font-size:17px;line-height:1;letter-spacing:1.5px;color:#e2e8f0;text-decoration:none;white-space:nowrap}
.header .logo:hover{color:#fff}
.version-badge{display:inline-block;font-size:11px;line-height:1;font-weight:600;letter-spacing:0;color:#94a3b8;white-space:nowrap}
.header .account{display:flex;gap:12px;align-items:center;justify-content:flex-end;flex-wrap:wrap;font-size:12px;color:#a0aec0;min-width:0;text-align:right}
.header .account strong{color:#e2e8f0}
.vip-badge{padding:2px 8px;border-radius:2px;font-size:11px;font-weight:600}
.vip-badge.active{background:var(--success);color:#fff}
.vip-badge.inactive{background:var(--danger);color:#fff}
.container{width:100%;max-width:1400px;height:calc(100dvh - var(--header-height,52px));margin:0 auto;padding:16px 24px;overflow-y:auto;overscroll-behavior:contain}
.mode-tabs{display:flex;overflow-x:auto;overflow-y:hidden;border-bottom:2px solid var(--border);margin-bottom:16px;background:var(--card-bg);border-radius:2px 2px 0 0;scrollbar-width:thin}
.mode-tab{flex:0 0 auto;padding:10px 20px;font-size:13px;font-weight:600;color:var(--text-secondary);cursor:pointer;border:none;background:none;border-bottom:2px solid transparent;margin-bottom:-2px;transition:all 0.15s ease}
.mode-tab:hover{color:var(--primary)}
.mode-tab.active{color:var(--primary);border-bottom-color:var(--accent)}
.card{background:var(--card-bg);border:1px solid var(--border);border-left:3px solid var(--accent-border);border-radius:2px;padding:16px;margin-bottom:16px}
.search-row{display:flex;gap:8px;align-items:flex-start}
.search-input-wrap{position:relative;flex:1;min-width:0;min-height:calc(1.5em + 18px)}
.search-row input[type=text]{width:100%;padding:8px 12px;font-size:13px;font-family:"SF Mono","Fira Code",Consolas,Monaco,monospace;border:1px solid var(--border);border-radius:2px;background:#fafbfc;color:var(--text);outline:none;transition:all 0.15s ease}
.search-row input[type=text]:focus{border-color:var(--accent);background:#fff}
.search-row textarea#queryInput{display:block;width:100%;padding:8px 12px;font-size:13px;line-height:1.5;font-family:"SF Mono","Fira Code",Consolas,Monaco,monospace;border:1px solid var(--border);border-radius:2px;background:#fafbfc;color:var(--text);outline:none;transition:border-color 0.15s ease,background 0.15s ease;resize:none;overflow:hidden;white-space:nowrap;min-height:calc(1.5em + 18px);max-height:200px}
.search-row textarea#queryInput:focus{border-color:var(--accent);background:#fff;position:absolute;left:0;right:0;top:0;z-index:50;box-shadow:0 6px 18px rgba(15,36,64,0.16);white-space:pre-wrap;max-height:calc(100dvh - 160px)}
.search-row textarea#queryInput.drop-target{border-color:var(--accent);background:#eff6ff;outline:2px dashed rgba(49,130,206,0.45);outline-offset:-2px}
.search-row .btn{flex-shrink:0}
.btn{padding:8px 20px;font-size:13px;font-weight:600;border:1px solid transparent;border-radius:2px;cursor:pointer;white-space:nowrap;transition:all 0.15s ease}
.btn:disabled{opacity:.65;cursor:not-allowed}
.btn-primary{background:var(--accent);color:#fff;border-color:var(--accent)}
.btn-primary:hover{background:var(--accent-hover)}
.btn-secondary{background:var(--card-bg);color:var(--text);border-color:var(--border)}
.btn-secondary:hover{background:#f1f5f9}
.btn-danger{background:var(--danger);color:#fff;border-color:var(--danger)}
.btn-danger:hover{background:#b91c1c}
.field-row{display:flex;gap:8px;margin-top:10px;position:relative}
.field-row>label{font-size:12px;color:var(--text-secondary);font-weight:600;padding-top:5px;min-width:40px;flex-shrink:0}
.field-control{flex:1;min-width:0;display:flex;flex-wrap:wrap;gap:4px;align-items:center;min-height:28px}
.chip{display:inline-flex;align-items:center;gap:3px;background:var(--chip-bg);border:1px solid var(--chip-border);border-radius:2px;padding:2px 6px;font-size:11px;cursor:grab;user-select:none;font-family:"SF Mono","Fira Code",Consolas,Monaco,monospace;transition:all 0.15s ease}
.chip:hover{border-color:var(--accent)}
.chip-label{line-height:1.4}
.chip-remove{cursor:pointer;color:var(--text-secondary);font-size:13px;line-height:1;width:14px;height:14px;display:inline-flex;align-items:center;justify-content:center;border-radius:1px;transition:all 0.15s ease}
.chip-remove:hover{color:var(--danger);background:rgba(220,38,38,0.08)}
.chip.dragging{opacity:.35;cursor:grabbing}
.chip.drop-before{box-shadow:-2px 0 0 0 var(--accent)}
.chip.drop-after{box-shadow:2px 0 0 0 var(--accent)}
.field-trigger{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border:1px dashed var(--border);border-radius:2px;cursor:pointer;color:var(--text-secondary);font-size:15px;font-weight:700;line-height:1;transition:all 0.15s ease;flex-shrink:0}
.field-trigger:hover{border-color:var(--accent);color:var(--accent);background:var(--chip-bg)}
.field-panel{display:none;position:absolute;top:calc(100% + 4px);left:48px;right:0;background:var(--card-bg);border:1px solid var(--border);border-radius:2px;z-index:200;max-height:340px;overflow:hidden;box-shadow:0 4px 16px rgba(0,0,0,0.12)}
.field-panel.open{display:flex;flex-direction:column}
.fp-search-wrap{padding:8px;border-bottom:1px solid var(--border);flex-shrink:0}
.fp-search{width:100%;padding:5px 8px;font-size:12px;border:1px solid var(--border);border-radius:2px;background:#fafbfc;outline:none;font-family:"SF Mono","Fira Code",Consolas,Monaco,monospace;transition:all 0.15s ease}
.fp-search:focus{border-color:var(--accent);background:#fff}
.fp-body{overflow-y:auto;flex:1;padding:4px 0}
.fp-cat-name{font-size:10px;font-weight:700;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.8px;padding:6px 10px 4px}
.fp-cat-fields{display:flex;flex-wrap:wrap;gap:2px;padding:0 8px 6px}
.fp-field{font-size:11px;font-family:"SF Mono","Fira Code",Consolas,Monaco,monospace;padding:3px 8px;border:1px solid var(--border);border-radius:2px;background:var(--card-bg);color:var(--text);cursor:pointer;transition:all 0.15s ease;line-height:1.4}
.fp-field:hover{border-color:var(--accent);color:var(--accent)}
.fp-field.selected{background:var(--accent);color:#fff;border-color:var(--accent)}
.fp-field.selected::after{content:'';display:inline-block;width:10px;height:10px;margin-left:4px;background:rgba(255,255,255,0.9);clip-path:polygon(20% 50%,40% 70%,80% 20%,70% 15%,40% 55%,28% 40%);vertical-align:middle}
.fp-field.hidden{display:none}
.fp-empty{padding:16px 10px;text-align:center;color:var(--text-secondary);font-size:12px}
.options-row{display:flex;gap:16px;align-items:center;margin-top:12px;flex-wrap:wrap;min-height:25px}
.options-row label{font-size:12px;color:var(--text-secondary);font-weight:600}
.options-row select,.options-row input[type=number]{padding:4px 8px;font-size:12px;border:1px solid var(--border);border-radius:2px;background:#fafbfc;margin-left:4px;transition:all 0.15s ease}
.options-row select{-webkit-appearance:none;-moz-appearance:none;appearance:none;padding:4px 24px 4px 8px;font-size:11px;font-weight:600;color:var(--text-secondary);cursor:pointer;background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'><path d='M2 4l3 3 3-3' fill='none' stroke='%2364748b' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/></svg>");background-repeat:no-repeat;background-position:right 6px center;background-color:var(--card-bg)}
.options-row select:hover{border-color:var(--accent);color:var(--accent)}
.options-row select:focus,.options-row input[type=number]:focus{border-color:var(--accent);background-color:#fff;outline:none}
.options-row select:focus{background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'><path d='M2 4l3 3 3-3' fill='none' stroke='%233182ce' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/></svg>")}
.options-row input[type=number]{width:80px}
.options-row input[type=text]{padding:4px 8px;font-size:12px;border:1px solid var(--border);border-radius:2px;background:#fafbfc;margin-left:4px;transition:all 0.15s ease}
.options-row input[type=text]:focus{border-color:var(--accent);background:#fff;outline:none}
.options-row select,.options-row input[type=number],.options-row input[type=text],.options-row .mini-btn{height:25px;box-sizing:border-box;vertical-align:middle}
.batch-textarea{width:100%;min-height:160px;margin-top:12px;padding:10px;font-size:12px;font-family:"SF Mono","Fira Code",Consolas,Monaco,monospace;border:1px solid var(--border);border-radius:2px;background:#fafbfc;resize:vertical;outline:none;transition:all 0.15s ease}
.batch-textarea:focus{border-color:var(--accent);background:#fff}
.history-dropdown{display:none;position:absolute;top:calc(100% + 4px);left:0;right:0;z-index:80;background:var(--card-bg);border:1px solid var(--border);border-radius:2px;max-height:min(300px,calc(100dvh - 180px));overflow-y:auto;overscroll-behavior:contain;box-shadow:0 8px 18px rgba(15,36,64,0.14)}
.history-dropdown.show{display:block}
.history-item{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:6px 12px;font-size:12px;font-family:"SF Mono","Fira Code",Consolas,Monaco,monospace;border-bottom:1px solid var(--border);cursor:pointer}
.history-item:last-child{border-bottom:none}
.history-item:hover,.history-item.active{background:var(--table-stripe)}
.history-item .query-text{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.history-actions{display:flex;gap:4px;margin-left:12px;flex-shrink:0}
.h-act{font-size:11px;color:var(--text-secondary);cursor:pointer;padding:2px 6px;border:1px solid var(--border);border-radius:2px;background:var(--card-bg);transition:all 0.15s ease}
.h-act:hover{background:var(--table-header);color:var(--text)}
.h-act.del:hover{color:var(--danger);border-color:var(--danger)}
.stats-bar{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:10px 16px;background:var(--table-header);border:1px solid var(--border);border-radius:2px;margin-bottom:12px;font-size:12px;color:var(--text-secondary)}
.stats-metrics{display:flex;gap:28px;align-items:center;flex-wrap:wrap}
.stats-actions{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.preview-status{font-size:11px;font-weight:600;color:var(--success);white-space:nowrap}
.stat-item{display:inline-flex;align-items:center;gap:6px}
.stat-dot{display:inline-block;width:7px;height:7px;border-radius:50%;flex-shrink:0}
.stat-value{font-weight:700;color:var(--text)}
.mini-btn{padding:4px 8px;font-size:11px;font-weight:600;border:1px solid var(--border);border-radius:2px;background:var(--card-bg);color:var(--text-secondary);cursor:pointer;transition:all 0.15s ease}
.mini-btn:hover{border-color:var(--accent);color:var(--accent);background:#eff6ff}
.mini-btn.pick-active{border-color:var(--warning);color:var(--warning);background:#fffbeb}
#resultsTable.picking td{cursor:crosshair}
#resultsTable.picking td:hover{background:#fffbeb;outline:1px solid var(--warning);box-shadow:inset 0 0 0 1px var(--warning)}
.settings-wrap{position:relative}
.settings-popup{display:none;position:absolute;top:100%;right:0;margin-top:4px;background:var(--card-bg);border:1px solid var(--border);border-radius:2px;padding:10px 12px;z-index:100;box-shadow:0 4px 12px rgba(0,0,0,0.08);min-width:180px}
.settings-popup.show{display:block}
.settings-popup label{display:flex;align-items:center;gap:6px;padding:4px 0;font-size:12px;cursor:pointer;white-space:nowrap}
.exc-chips{display:inline-flex;gap:4px;flex-wrap:wrap;align-items:center}
.exc-chip{display:inline-flex;align-items:center;gap:3px;padding:2px 6px;font-size:11px;background:#fef2f2;border:1px solid #fecaca;color:#991b1b;border-radius:2px;white-space:nowrap}
.exc-chip .exc-x{cursor:pointer;font-weight:700;color:#dc2626;opacity:.7}
.exc-chip .exc-x:hover{opacity:1}
.server-status{font-weight:700}
.server-status.ok{color:var(--success)}
.server-status.fail{color:var(--danger)}
#resultsArea>.card{margin-bottom:0}
.table-container{background:var(--card-bg);border:1px solid var(--border);border-radius:2px;overflow:auto;overscroll-behavior:contain;max-height:calc(100dvh - 340px);min-height:160px}
table{width:100%;min-width:760px;border-collapse:collapse;font-size:12px}
thead{position:sticky;top:0;z-index:1}
th{background:var(--table-header);padding:7px 12px;text-align:left;font-weight:600;font-size:11px;line-height:18px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:.5px;border-bottom:2px solid var(--border);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer;user-select:none;transition:all 0.15s ease}
th:hover{color:var(--text)}
th.sorted{color:var(--accent)}
td{padding:7px 12px;border-bottom:1px solid var(--border);max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11.5px;line-height:18px}
tr.vs-stripe{background:var(--table-stripe)}
tr:hover{background:#e8f0fe}
#resultsTable.scrolling tr:hover{background:transparent}
#resultsTable.scrolling tr.vs-stripe:hover{background:var(--table-stripe)}
td a{color:var(--accent);text-decoration:none;transition:all 0.15s ease}
td a:hover{text-decoration:underline}
td.mono{font-family:"SF Mono","Fira Code",Consolas,Monaco,monospace;font-size:11px}
.overlay{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(15,36,64,.85);z-index:1000;justify-content:center;align-items:center}
.overlay.show{display:flex}
.overlay-content{background:var(--card-bg);border:1px solid var(--border);border-radius:2px;padding:32px 40px;min-width:420px;max-width:520px}
.overlay-content h3{font-size:15px;font-weight:700;margin-bottom:20px;color:var(--primary)}
.icon-modal-input{width:100%;padding:8px 12px;font-size:13px;font-family:"SF Mono","Fira Code",Consolas,Monaco,monospace;border:1px solid var(--border);border-radius:2px;background:#fafbfc;color:var(--text);outline:none;margin-bottom:12px;transition:all 0.15s ease}
.icon-modal-input:focus{border-color:var(--accent);background:#fff}
.icon-modal-error{display:none;background:#fef2f2;border:1px solid #fecaca;color:var(--danger);border-radius:2px;padding:8px 10px;font-size:12px;margin-bottom:12px;text-align:left;word-break:break-all}
.progress-track{height:8px;background:var(--border);overflow:hidden;margin-bottom:12px;border-radius:1px}
.progress-fill{height:100%;width:0;background:linear-gradient(90deg,var(--accent) 30%,#63b3ed 50%,var(--accent) 70%);background-size:200% 100%;transition:width .3s;animation:shimmer 2s ease-in-out infinite}
@keyframes shimmer{0%{background-position:200% center}100%{background-position:-200% center}}
.progress-details{font-size:12px;color:var(--text-secondary);margin-bottom:16px;line-height:1.8}
.progress-details span{color:var(--text);font-weight:600}
.export-panel{display:none;background:var(--card-bg);border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:2px;margin-bottom:16px;overflow:hidden}
.export-panel.show{display:block}
.export-panel-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;background:var(--table-header);border-bottom:1px solid var(--border)}
.export-panel-title{font-size:13px;font-weight:700;color:var(--primary)}
.export-panel-state{font-size:12px;font-weight:700;color:var(--accent);white-space:nowrap}
.export-panel-body{padding:14px}
.export-meta{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:12px 0}
.export-meta-item{border:1px solid var(--border);background:#fafbfc;border-radius:2px;padding:8px 10px}
.export-meta-label{display:block;font-size:11px;color:var(--text-secondary);margin-bottom:2px}
.export-meta-value{display:block;font-size:13px;font-weight:700;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.export-panel-msg{font-size:12px;color:var(--text-secondary);line-height:1.6}
.export-panel-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.message{padding:10px 14px;border-radius:2px;font-size:12px;margin-bottom:12px}
.message.error{background:#fef2f2;border:1px solid #fecaca;color:var(--danger)}
.message.info{background:#eff6ff;border:1px solid #bfdbfe;color:var(--primary-light)}
.config-alert{display:none;background:#fff7ed;border:1px solid #fed7aa;border-left:3px solid var(--warning);border-radius:2px;padding:12px 14px;margin-bottom:16px;font-size:12px;color:#7c2d12}
.config-alert.show{display:block}
.config-alert strong{display:block;color:#9a3412;font-size:13px;margin-bottom:6px}
.config-alert code{display:block;background:#ffedd5;border:1px solid #fed7aa;color:#7c2d12;padding:6px 8px;margin-top:8px;overflow:auto;font-family:"SF Mono","Fira Code",Consolas,Monaco,monospace;font-size:11px}
.config-alert pre{background:#fffaf0;border:1px solid #fed7aa;margin-top:8px;padding:8px;overflow:auto;font-family:"SF Mono","Fira Code",Consolas,Monaco,monospace;font-size:11px;line-height:1.5;white-space:pre-wrap}
.empty-state{text-align:center;padding:40px 20px;color:var(--text-secondary);font-size:13px}
.spinner{display:inline-block;width:14px;height:14px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .6s linear infinite;vertical-align:middle;margin-right:6px}
@keyframes spin{to{transform:rotate(360deg)}}
@media (max-width: 760px){
.header{align-items:flex-start;flex-direction:column;padding:10px 14px;gap:6px}
.header .brand{width:100%;justify-content:space-between}
.header .account{justify-content:flex-start;text-align:left;gap:6px 10px}
.container{padding:12px}
.mode-tabs{margin-bottom:12px}
.mode-tab{flex:1 0 auto;text-align:center;padding:9px 12px}
.card{padding:12px;margin-bottom:12px}
.search-row{flex-direction:column}
.search-row .btn{width:100%}
.field-row{display:block}
.field-row>label{display:block;min-width:0;padding-top:0;margin-bottom:6px}
.field-panel{left:0;right:0;max-height:min(300px,calc(100dvh - 220px))}
.options-row{gap:8px 12px}
.history-item{align-items:flex-start;flex-direction:column}
.history-actions{margin-left:0}
.stats-bar{align-items:stretch;flex-direction:column;gap:8px}
.stats-metrics{gap:10px 16px}
.stats-actions{justify-content:flex-start}
.preview-status{width:100%}
.export-meta{grid-template-columns:repeat(2,minmax(0,1fr))}
td{max-width:240px}
.overlay-content{width:calc(100vw - 24px);min-width:0;max-width:none;padding:24px}
}
@media (max-width: 420px){
.container{padding:8px}
.mode-tab{font-size:12px;padding:8px 10px}
.chip{max-width:100%}
.chip-label{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.options-row label{width:100%}
.options-row select,.options-row input[type=number],.options-row input[type=text]{width:100%;margin:4px 0 0}
.batch-textarea{min-height:120px}
.history-dropdown{max-height:calc(100dvh - 170px)}
.mini-btn{flex:1;text-align:center}
.stats-actions{width:100%}
.empty-state{padding:28px 14px}
}
@media (max-height: 620px){
.container{padding-top:10px;padding-bottom:10px}
.card{padding:12px;margin-bottom:10px}
.mode-tabs{margin-bottom:10px}
.batch-textarea{min-height:96px}
.table-container{min-height:120px}
}
</style>
</head>
<body>
<div class="header">
<div class="brand"><a class="logo" href="__GITHUB_URL__" target="_blank" rel="noopener">FOFATOTO</a><span class="version-badge">v__APP_VERSION__</span></div>
<div class="account" id="accountInfo">加载中...</div>
</div>
<div class="container">
<div class="mode-tabs">
<button class="mode-tab active" data-mode="instant">即时预览</button>
<button class="mode-tab" data-mode="export">深度导出</button>
<button class="mode-tab" data-mode="batch">批量模式</button>
</div>
<div class="config-alert" id="configAlert">
<strong id="configAlertTitle">未配置 FOFA API Key</strong>
<div id="configAlertText"></div>
<code id="configPath"></code>
<pre id="configTemplate"></pre>
</div>
<div class="card">
<div class="search-row">
<div class="search-input-wrap">
<textarea id="queryInput" placeholder="FOFA 查询语法，如 domain=baidu.com" autofocus autocomplete="off" spellcheck="false" rows="1"></textarea>
<div class="history-dropdown" id="historyDropdown"></div>
</div>
<button class="btn btn-primary" id="searchBtn" onclick="executeSearch()">搜索</button>
</div>
<div class="field-row">
<label>字段</label>
<div class="field-control" id="fieldControl"></div>
<div class="field-panel" id="fieldPanel">
<div class="fp-search-wrap"><input type="text" class="fp-search" id="fpSearch" placeholder="搜索字段..." spellcheck="false" autocomplete="off"></div>
<div class="fp-body" id="fpBody"></div>
</div>
</div>
<div class="options-row" id="instantOptions">
<label>数量:<select id="instantSize"><option value="10">10</option><option value="20">20</option><option value="50">50</option><option value="100" selected>100</option><option value="200">200</option><option value="500">500</option><option value="1000">1000</option><option value="2000">2000</option><option value="5000">5000</option><option value="10000">10000</option></select></label>
<span class="exc-chips" id="exclusionChips"></span>
<button class="mini-btn" onclick="openIconModal()">Icon 提取</button>
<div class="settings-wrap"><button class="mini-btn" onclick="toggleSettings(event)">设置</button><div class="settings-popup" id="settingsPopup"><label><input type="checkbox" id="fitToWindow" checked onchange="toggleFitToWindow(this)"> 适应窗口宽度</label><label><input type="checkbox" id="instantFull"> 全部数据</label><label><input type="checkbox" id="instantAutoQuery"> 选取查询后自动搜索</label><label><input type="checkbox" id="showHistory" checked onchange="toggleShowHistory(this)"> 显示历史记录</label></div></div>
</div>
<div class="options-row" id="exportOptions" style="display:none">
<label>覆盖率:<input type="number" id="exportFill" value="0.8" min="0.1" max="1.0" step="0.1"></label>
<label>上限:<input type="number" id="exportMaxSize" value="0" min="0" placeholder="0=不限制"></label>
<label><input type="checkbox" id="exportFull"> 全部数据</label>
</div>
<div id="batchOptions" style="display:none">
<div class="options-row">
<label>占位符:<input type="text" id="batchPlaceholder" value="{}" style="width:120px"></label>
<label>覆盖率:<input type="number" id="batchFill" value="0.8" min="0.1" max="1.0" step="0.1"></label>
<label>每目标上限:<input type="number" id="batchMaxSize" value="0" min="0" placeholder="0=不限制"></label>
</div>
<textarea class="batch-textarea" id="batchTargets" placeholder="在此粘贴目标，每行一个..."></textarea>
</div>
</div>
<div class="export-panel" id="exportPanel">
<div class="export-panel-head">
<div class="export-panel-title" id="exportPanelTitle">深度导出</div>
<div class="export-panel-state" id="exportPanelState">等待中</div>
</div>
<div class="export-panel-body">
<div class="progress-track"><div class="progress-fill" id="exportPanelFill"></div></div>
<div class="export-panel-msg" id="exportPanelMessage">准备开始导出...</div>
<div class="export-meta" id="exportPanelMeta"></div>
<div class="export-panel-actions" id="exportPanelActions"></div>
</div>
</div>
<div id="resultsArea" style="display:none">
<div class="card" style="padding:0;overflow:hidden">
<div class="stats-bar" id="statsBar" style="border:none;margin:0"></div>
<div class="table-container" style="border:none"><div class="empty-state" id="emptyState" style="display:none"></div><table id="resultsTable"><thead></thead><tbody></tbody></table></div>
</div>
</div>
<div id="messageArea"></div>
</div>
<div class="overlay" id="progressOverlay">
<div class="overlay-content">
<h3 id="progressTitle">正在导出</h3>
<div class="progress-track"><div class="progress-fill" id="progressFill"></div></div>
<div class="progress-details" id="progressDetails">初始化中...</div>
<div id="progressActions"><button class="btn btn-secondary" onclick="cancelExport()">取消</button></div>
</div>
</div>
<div class="overlay" id="cancelOverlay">
<div class="overlay-content" style="text-align:center">
<h3>确认取消</h3>
<p style="font-size:13px;color:var(--text-secondary);margin:0 0 24px;line-height:1.7">已查询到的数据是否保留？<br>保留后可继续下载 CSV / JSON / TXT 文件。</p>
<div style="display:flex;gap:8px;justify-content:center">
<button class="btn btn-primary" onclick="confirmCancel(1)">保存并取消</button>
<button class="btn btn-danger" onclick="confirmCancel(0)">直接取消</button>
<button class="btn btn-secondary" onclick="hideCancelConfirm()">返回</button>
</div>
</div>
</div>
<div class="overlay" id="iconOverlay">
<div class="overlay-content" style="text-align:center">
<h3>提取 Icon Hash</h3>
<input type="text" class="icon-modal-input" id="iconTargetInput" placeholder="网站地址，如 https://example.com" spellcheck="false" autocomplete="off">
<div class="icon-modal-error" id="iconModalError"></div>
<div style="display:flex;gap:8px;justify-content:center">
<button class="btn btn-primary" id="iconExtractBtn" onclick="submitIconExtract()">提取并填入</button>
<button class="btn btn-secondary" onclick="closeIconModal()">取消</button>
</div>
</div>
</div>
<script>
var fieldCategories=__FIELD_CATEGORIES_JSON__;
var allFields=[];fieldCategories.forEach(function(c){c.fields.forEach(function(f){allFields.push(f)})});
var selectedFields=__DEFAULT_FIELDS_JSON__;
var currentMode="instant",currentResults=[],currentColumns=[],currentView=[],rowHeight=0,OVERSCAN=10,previewRendered=false,exportTaskId=null,exportPollTimer=null,progressUiMode="overlay",sortColumn=null,sortAsc=true,historyActiveIndex=-1,historyVisibleItems=[],vsLastWindow=null;
var ACCOUNT_REFRESH_INTERVAL=180000,accountRefreshTimer=null,lastAccountRefresh=0;
function initFieldSelector(){renderChips();renderFieldPanel();var ctrl=document.getElementById("fieldControl");var trig=document.createElement("div");trig.className="field-trigger";trig.id="fieldTrigger";trig.textContent="+";trig.addEventListener("click",function(e){e.stopPropagation();toggleFieldPanel()});ctrl.appendChild(trig);document.getElementById("fpSearch").addEventListener("input",filterFields);var fieldRowDown=false;document.addEventListener("mousedown",function(e){fieldRowDown=!!(e.target.closest&&e.target.closest(".field-row"))},true);document.addEventListener("click",function(){var p=document.getElementById("fieldPanel");if(p.classList.contains("open")&&!fieldRowDown)p.classList.remove("open")});document.addEventListener("keydown",function(e){if(e.key==="Escape")document.getElementById("fieldPanel").classList.remove("open")})}
var dragField=null;
function clearChipDropClasses(){document.querySelectorAll("#fieldControl .chip").forEach(function(el){el.classList.remove("drop-before","drop-after")})}
function renderChips(){var c=document.getElementById("fieldControl");c.querySelectorAll(".chip").forEach(function(el){el.remove()});var trig=document.getElementById("fieldTrigger");selectedFields.forEach(function(f){var ch=document.createElement("span");ch.className="chip";ch.draggable=true;ch.dataset.field=f;ch.innerHTML='<span class="chip-label">'+escHtml(f)+'</span><span class="chip-remove">&times;</span>';ch.querySelector(".chip-remove").addEventListener("click",function(e){e.stopPropagation();removeField(f)});ch.addEventListener("dragstart",function(e){dragField=f;ch.classList.add("dragging");e.dataTransfer.effectAllowed="move";try{e.dataTransfer.setData("text/plain",f)}catch(_){}});ch.addEventListener("dragend",function(){dragField=null;ch.classList.remove("dragging");clearChipDropClasses()});ch.addEventListener("dragover",function(e){if(dragField===null||dragField===f)return;e.preventDefault();e.dataTransfer.dropEffect="move";var r=ch.getBoundingClientRect();clearChipDropClasses();ch.classList.add((e.clientX-r.left)<r.width/2?"drop-before":"drop-after")});ch.addEventListener("dragleave",function(){ch.classList.remove("drop-before","drop-after")});ch.addEventListener("drop",function(e){if(dragField===null||dragField===f)return;e.preventDefault();e.stopPropagation();var r=ch.getBoundingClientRect(),before=(e.clientX-r.left)<r.width/2;var from=selectedFields.indexOf(dragField);if(from<0)return;selectedFields.splice(from,1);var to=selectedFields.indexOf(f);if(!before)to++;selectedFields.splice(to,0,dragField);dragField=null;clearChipDropClasses();renderChips()});c.insertBefore(ch,trig)})}
function renderFieldPanel(){var body=document.getElementById("fpBody");body.innerHTML="";fieldCategories.forEach(function(cat){var div=document.createElement("div");div.className="fp-category";var hdr=document.createElement("div");hdr.className="fp-cat-name";hdr.textContent=cat.name;div.appendChild(hdr);var fd=document.createElement("div");fd.className="fp-cat-fields";cat.fields.forEach(function(f){var btn=document.createElement("button");btn.className="fp-field"+(selectedFields.indexOf(f)>-1?" selected":"");btn.dataset.field=f;btn.textContent=f;btn.addEventListener("click",function(){toggleField(f)});fd.appendChild(btn)});div.appendChild(fd);body.appendChild(div)})}
function toggleFieldPanel(){var p=document.getElementById("fieldPanel");p.classList.toggle("open");if(p.classList.contains("open")){document.getElementById("fpSearch").value="";filterFields();document.getElementById("fpSearch").focus()}}
function toggleField(f){var i=selectedFields.indexOf(f);if(i>-1)selectedFields.splice(i,1);else selectedFields.push(f);renderChips();renderFieldPanel()}
function removeField(f){var i=selectedFields.indexOf(f);if(i>-1){selectedFields.splice(i,1);renderChips();renderFieldPanel()}}
function filterFields(){var q=document.getElementById("fpSearch").value.trim().toLowerCase();var total=0;document.querySelectorAll("#fpBody .fp-category").forEach(function(cat){var v=0;cat.querySelectorAll(".fp-field").forEach(function(b){var m=!q||b.dataset.field.indexOf(q)>-1;b.classList.toggle("hidden",!m);if(m){v++;total++}});cat.style.display=v>0?"":"none"});var old=document.getElementById("fpEmpty");if(total===0&&q){if(!old){var el=document.createElement("div");el.id="fpEmpty";el.className="fp-empty";el.textContent="无匹配字段";document.getElementById("fpBody").appendChild(el)}}else if(old)old.remove()}
function getSelectedFields(){return selectedFields.join(",")}
document.addEventListener("DOMContentLoaded",function(){initFieldSelector();loadAccountInfo(false).finally(function(){lastAccountRefresh=Date.now()});setupModeTabs();setupSearchShortcut();setupQueryDropTarget();updateHistoryCount();var sh=document.getElementById("showHistory");if(sh)sh.checked=getShowHistory();updateLayout();startAccountRefresh();document.addEventListener("visibilitychange",onVisibilityChange);window.addEventListener("resize",function(){autoResizeQueryInput();updateLayout();renderVirtual()})});
function setupModeTabs(){document.querySelectorAll(".mode-tab").forEach(function(t){t.addEventListener("click",function(){switchMode(this.dataset.mode)})})}
function modeButtonText(){return currentMode==="instant"?"搜索":(currentMode==="export"?"导出":"批量查询")}
function refreshModeButton(){var btn=document.getElementById("searchBtn");btn.textContent=modeButtonText();btn.className="btn btn-primary"}
function switchMode(mode){if(exportPollTimer&&currentMode!==mode){showMessage("error","已有导出任务正在运行，请先取消或等待完成");return}currentMode=mode;document.querySelectorAll(".mode-tab").forEach(function(t){t.classList.toggle("active",t.dataset.mode===mode)});document.getElementById("instantOptions").style.display=mode==="instant"?"":"none";document.getElementById("exportOptions").style.display=mode==="export"?"":"none";document.getElementById("batchOptions").style.display=mode==="batch"?"":"none";if(!document.getElementById("searchBtn").disabled)refreshModeButton();clearMessage();updateLayout()}
function syncModeContent(){var results=document.getElementById("resultsArea"),panel=document.getElementById("exportPanel");if(results)results.style.display=currentMode==="instant"&&previewRendered?"block":"none";if(panel)panel.style.display=(currentMode==="export"||currentMode==="batch")&&panel.classList.contains("show")?"":"none"}
function autoResizeQueryInput(){var el=document.getElementById("queryInput");if(!el)return;el.style.height="auto";var h=el.scrollHeight;var maxH=el===document.activeElement?Math.floor(window.innerHeight-160):200;el.style.height=Math.max(34,Math.min(h,maxH))+"px";var dd=document.getElementById("historyDropdown");if(dd&&dd.classList.contains("show")){dd.style.top=el.getBoundingClientRect().height+4+"px";fitHistoryDropdown()}updateLayout()}
function setupSearchShortcut(){var input=document.getElementById("queryInput");input.addEventListener("focus",function(){renderHistorySuggestions(true);autoResizeQueryInput()});input.addEventListener("input",function(){renderHistorySuggestions(false);autoResizeQueryInput()});input.addEventListener("blur",function(){input.style.height="calc(1.5em + 18px)";var dd=document.getElementById("historyDropdown");if(dd)dd.style.top="";updateLayout()});input.addEventListener("keydown",function(e){var dd=document.getElementById("historyDropdown"),open=dd&&dd.classList.contains("show");if(e.key==="ArrowDown"){e.preventDefault();if(!open)renderHistorySuggestions(true);moveHistorySelection(1)}else if(e.key==="ArrowUp"){e.preventDefault();if(!open)renderHistorySuggestions(true);moveHistorySelection(-1)}else if(e.key==="Escape"){closeHistorySuggestions()}else if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();if(open&&historyActiveIndex>-1&&pickActiveHistory()){return}closeHistorySuggestions();executeSearch()}})}
function dropFieldToQuery(fieldName){var input=document.getElementById("queryInput"),base=input.value.replace(/\s+$/,""),frag=fieldName+'=""',pos;if(!base){input.value=frag;pos=frag.length-1}else if(/(&&|\|\|)\s*$/.test(base)){input.value=base+" "+frag;pos=input.value.length-1}else{input.value=base+" || "+frag;pos=input.value.length-1}input.focus();closeHistorySuggestions();input.setSelectionRange(pos,pos);autoResizeQueryInput()}
function setupQueryDropTarget(){var input=document.getElementById("queryInput");input.addEventListener("dragover",function(e){if(dragField===null)return;e.preventDefault();e.dataTransfer.dropEffect="move";input.classList.add("drop-target")});input.addEventListener("dragleave",function(){if(dragField===null)return;input.classList.remove("drop-target")});input.addEventListener("drop",function(e){if(dragField===null)return;e.preventDefault();e.stopPropagation();input.classList.remove("drop-target");var f=dragField;dragField=null;clearChipDropClasses();dropFieldToQuery(f)})}
function showConfigNotice(d){var box=document.getElementById("configAlert");document.getElementById("configAlertTitle").textContent="未配置有效的 FOFA API Key";document.getElementById("configAlertText").textContent="请编辑下方配置文件，保存后刷新本页面。";document.getElementById("configPath").textContent=d.config_path||"";document.getElementById("configTemplate").textContent=d.config_template||"";box.classList.add("show")}
function hideConfigNotice(){document.getElementById("configAlert").classList.remove("show")}
function formatApiError(data,fallback){var msg=(data&&data.error)||fallback||"请求失败";if(data&&data.data&&data.data.configured===false&&data.data.config_path){msg+="。配置文件: "+data.data.config_path}return msg}
function loadAccountInfo(silent){return fetch("/api/info").then(function(r){return r.json()}).then(function(data){var d=data.data||{};if(d.configured===false){showConfigNotice(d);document.getElementById("accountInfo").innerHTML='<span class="vip-badge inactive">未配置</span> 等待 API Key';return}hideConfigNotice();if(data.success){if(d.relay){var vClass=d.isvip?"active":"inactive",vText=d.isvip?"有效":"无效";var h='<span class="vip-badge inactive">中转站</span> <span class="vip-badge '+vClass+'">'+vText+'</span> '+"剩余查询: <strong>"+escHtml(d.remain_api_query||"N/A")+"</strong>";if(d.today_remaining!==null&&d.today_remaining!==undefined)h+=" | 今日剩余: <strong>"+escHtml(d.today_remaining)+"</strong>";h+=" | 过期: "+escHtml(d.expiration||"N/A");document.getElementById("accountInfo").innerHTML=h}else{var vipClass=d.isvip?"active":"inactive",vipText=d.isvip?"VIP "+(d.vip_level||""):"未激活",serverText=d.server_ok?"正常":"异常",serverClass=d.server_ok?"ok":"fail";document.getElementById("accountInfo").innerHTML='<span class="vip-badge '+vipClass+'">'+escHtml(vipText)+'</span> 服务器: <span class="server-status '+serverClass+'">'+serverText+'</span> | 剩余查询: <strong>'+escHtml(d.remain_api_query||"N/A")+'</strong> | 过期: '+escHtml(d.expiration||"N/A");if(d.server_ok===false&&d.error&&!silent)showMessage("error",d.error)}}else{if(!silent){document.getElementById("accountInfo").innerHTML='<span class="vip-badge inactive">异常</span> 账户信息不可用';showMessage("error",formatApiError(data,"账户信息不可用"))}}}).catch(function(e){if(!silent){document.getElementById("accountInfo").innerHTML='<span class="vip-badge inactive">异常</span> 本地服务不可用';showMessage("error","网络错误: "+e.message)}}).finally(function(){updateLayout()})}
function startAccountRefresh(){if(accountRefreshTimer)return;accountRefreshTimer=setInterval(function(){loadAccountInfo(true);lastAccountRefresh=Date.now()},ACCOUNT_REFRESH_INTERVAL)}
function stopAccountRefresh(){if(accountRefreshTimer){clearInterval(accountRefreshTimer);accountRefreshTimer=null}}
function onVisibilityChange(){if(document.hidden){stopAccountRefresh()}else{var elapsed=Date.now()-lastAccountRefresh;if(elapsed>=ACCOUNT_REFRESH_INTERVAL){loadAccountInfo(true);lastAccountRefresh=Date.now()}startAccountRefresh()}}
function executeSearch(){var q=document.getElementById("queryInput").value.trim();if(!q)return;closeHistorySuggestions();addToHistory(q);if(currentMode==="instant")doInstantSearch(q);else if(currentMode==="export")doDeepExport(q);else doBatchSearch(q)}
function openIconModal(){var ov=document.getElementById("iconOverlay"),inp=document.getElementById("iconTargetInput");document.getElementById("iconModalError").style.display="none";inp.value="";inp.onkeydown=function(e){if(e.key==="Enter"){e.preventDefault();submitIconExtract()}else if(e.key==="Escape"){closeIconModal()}};ov.classList.add("show");setTimeout(function(){inp.focus()},50)}
function closeIconModal(){document.getElementById("iconOverlay").classList.remove("show")}
function iconModalError(msg){var el=document.getElementById("iconModalError");el.textContent=msg;el.style.display="block"}
function submitIconExtract(){var inp=document.getElementById("iconTargetInput"),target=inp.value.trim();if(!target){iconModalError("请输入网站地址");return}var btn=document.getElementById("iconExtractBtn"),oldText=btn.textContent;btn.disabled=true;btn.textContent="提取中...";fetch("/api/icon",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({target:target})}).then(function(r){return r.json()}).then(function(data){if(!data.success){iconModalError(formatApiError(data,"icon 提取失败"));return}var q='icon_hash="'+(data.data||{}).icon_hash+'"';var qin=document.getElementById("queryInput");qin.value=q;autoResizeQueryInput();closeIconModal();qin.focus()}).catch(function(e){iconModalError("网络错误: "+e.message)}).finally(function(){btn.disabled=false;btn.textContent=oldText})}
function doInstantSearch(query){var size=parseInt(document.getElementById("instantSize").value)||100,fields=getSelectedFields(),full=document.getElementById("instantFull").checked;clearResults();showMessage("info","搜索中...");fetch("/api/search",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query:query,size:size,fields:fields,full:full})}).then(function(r){return r.json()}).then(function(data){clearMessage();if(data.success){currentResults=data.data.results||[];currentColumns=data.data.columns||[];var _sb=getScrollBox();if(_sb)_sb.scrollTop=0;renderResults(data.data)}else showMessage("error",formatApiError(data,"搜索失败"))}).catch(function(e){showMessage("error","网络错误: "+e.message)})}
function doDeepExport(query){var fill=parseFloat(document.getElementById("exportFill").value),maxSize=parseInt(document.getElementById("exportMaxSize").value)||0,fields=getSelectedFields(),full=document.getElementById("exportFull").checked;if(isNaN(fill))fill=0.8;if(fill<=0||fill>1){showMessage("error","覆盖率必须在 0 到 1 之间");return}if(maxSize<0){showMessage("error","上限不能小于 0");return}if(exportPollTimer){showMessage("error","已有导出任务正在运行，请先取消或等待完成");return}progressUiMode="panel";exportTaskId=null;clearMessage();showExportPanelStart(query,fill,maxSize,full);setSearchBusy(true,"导出中...");fetch("/api/export",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query:query,fill_percent:fill,max_size:maxSize,fields:fields,full:full})}).then(function(r){return r.json()}).then(function(data){if(data.success){exportTaskId=data.task_id;pollProgress()}else{setSearchBusy(false);showExportPanelError(formatApiError(data,"导出失败"))}}).catch(function(e){setSearchBusy(false);showExportPanelError("网络错误: "+e.message)})}
function doBatchSearch(baseQuery){var ph=document.getElementById("batchPlaceholder").value||"{}",targets=document.getElementById("batchTargets").value.trim(),fill=parseFloat(document.getElementById("batchFill").value)||0.8,maxSize=parseInt(document.getElementById("batchMaxSize").value)||0,fields=getSelectedFields();if(!targets){showMessage("error","请输入批量目标");return}if(baseQuery.indexOf(ph)===-1){showMessage("error","基础查询必须包含占位符: "+ph);return}if(maxSize<0){showMessage("error","每目标上限不能小于 0");return}if(exportPollTimer){showMessage("error","已有任务正在运行，请先取消或等待完成");return}var targetLines=targets.replace(/\r/g,"").split("\n").filter(function(l){return l.trim()});progressUiMode="panel";exportTaskId=null;clearMessage();showBatchPanelStart(baseQuery,targetLines.length,ph,fill,maxSize);setSearchBusy(true,"批量查询中...");fetch("/api/batch",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({base_query:baseQuery,targets:targetLines,placeholder:ph,fill_percent:fill,max_size:maxSize,fields:fields})}).then(function(r){return r.json()}).then(function(data){if(data.success){exportTaskId=data.task_id;pollProgress()}else{setSearchBusy(false);showExportPanelError(formatApiError(data,"批量导出失败"))}}).catch(function(e){setSearchBusy(false);showExportPanelError("网络错误: "+e.message)})}
function renderProgressDetails(d,pct){if(d.kind==="batch"){var current=d.current_target||0,total=d.total_targets||0,curFetched=d.current_fetched||0,curTotal=d.current_target_count||d.current_total_estimated||0;return "进度: <span>"+pct+"%</span><br>目标: <span>"+current+"</span> / "+total+" | 当前: <span>"+curFetched.toLocaleString()+"</span> / ~"+curTotal.toLocaleString()+"<br>累计结果: <span>"+(d.fetched||0).toLocaleString()+"</span> | 失败: <span>"+(d.failed_count||0).toLocaleString()+"</span>"}var target=d.target_count||d.total_estimated||0;return "进度: <span>"+pct+"%</span><br>已获取: <span>"+(d.fetched||0).toLocaleString()+"</span> / ~"+target.toLocaleString()+"<br>总匹配: <span>"+(d.total_estimated||0).toLocaleString()+"</span> | 独立IP: <span>"+(d.unique_ips||0).toLocaleString()+"</span> | 配额: <span>"+(d.total_quota_used||0).toLocaleString()+"</span>"}
function exportMetaItem(label,value){return '<div class="export-meta-item"><span class="export-meta-label">'+escHtml(label)+'</span><span class="export-meta-value">'+escHtml(value)+'</span></div>'}
function exportTarget(d){return d.target_count||d.total_estimated||0}
function showExportPanelStart(query,fill,maxSize,full){document.getElementById("exportPanel").classList.add("show");document.getElementById("exportPanelTitle").textContent="深度导出";document.getElementById("exportPanelState").textContent="启动中";document.getElementById("exportPanelFill").style.width="0%";document.getElementById("exportPanelMessage").textContent="正在创建导出任务，完成后可下载 CSV / JSON / TXT。";document.getElementById("exportPanelMeta").innerHTML=exportMetaItem("查询",query)+exportMetaItem("覆盖率",Math.round(fill*100)+"%")+exportMetaItem("上限",maxSize>0?maxSize.toLocaleString():"不限制")+exportMetaItem("数据范围",full?"全部数据":"基础字段");document.getElementById("exportPanelActions").innerHTML='<button class="btn btn-secondary" onclick="cancelExport()">取消</button>';updateLayout()}
function showBatchPanelStart(baseQuery,targetCount,placeholder,fill,maxSize){document.getElementById("exportPanel").classList.add("show");document.getElementById("exportPanelTitle").textContent="批量查询";document.getElementById("exportPanelState").textContent="启动中";document.getElementById("exportPanelFill").style.width="0%";document.getElementById("exportPanelMessage").textContent="正在创建批量查询任务，完成后可下载 CSV / JSON / TXT。";document.getElementById("exportPanelMeta").innerHTML=exportMetaItem("基础查询",baseQuery)+exportMetaItem("占位符",placeholder)+exportMetaItem("目标数",targetCount.toLocaleString())+exportMetaItem("覆盖率",Math.round(fill*100)+"%")+exportMetaItem("每目标上限",maxSize>0?maxSize.toLocaleString():"不限制");document.getElementById("exportPanelActions").innerHTML='<button class="btn btn-secondary" onclick="cancelExport()">取消</button>';updateLayout()}
function showExportPanelError(message){document.getElementById("exportPanel").classList.add("show");document.getElementById("exportPanelState").textContent="失败";document.getElementById("exportPanelMessage").innerHTML='<span style="color:#dc2626">'+escHtml(message)+"</span>";document.getElementById("exportPanelActions").innerHTML='<button class="btn btn-secondary" onclick="hideExportPanel()">关闭</button>';updateLayout()}
function updateExportPanel(d,pct){var target=exportTarget(d),fetched=d.fetched||0,elapsed=d.elapsed_seconds?d.elapsed_seconds+" 秒":"刚开始";document.getElementById("exportPanel").classList.add("show");document.getElementById("exportPanelFill").style.width=pct+"%";document.getElementById("exportPanelState").textContent=d.status==="done"?(d.partial?"部分完成":"完成"):(d.status==="error"?"失败":pct+"%");document.getElementById("exportPanelMessage").textContent=d.status==="done"?(d.partial?("部分导出完成，已保留 "+fetched.toLocaleString()+" 条可用结果。"):"导出文件已生成，可选择格式下载。"):(d.message||(d.kind==="batch"?"正在批量查询...":"正在按时间游标分批拉取 FOFA 数据..."));document.getElementById("exportPanelMeta").innerHTML=d.kind==="batch"?exportMetaItem("目标",(d.current_target||0)+" / "+(d.total_targets||0))+exportMetaItem("当前",(d.current_fetched||0).toLocaleString()+" / ~"+(d.current_target_count||d.current_total_estimated||0).toLocaleString())+exportMetaItem("累计",(d.fetched||0).toLocaleString())+exportMetaItem("失败",(d.failed_count||0).toLocaleString())+exportMetaItem("耗时",elapsed):exportMetaItem("已获取",fetched.toLocaleString())+exportMetaItem("目标",target?("~"+target.toLocaleString()):"估算中")+exportMetaItem("总匹配",((d.total_estimated||0).toLocaleString()))+exportMetaItem("独立 IP",((d.unique_ips||0).toLocaleString()))+exportMetaItem("配额",((d.total_quota_used||0).toLocaleString()))+exportMetaItem("耗时",elapsed);if(d.status==="done"){document.getElementById("exportPanelActions").innerHTML='<button class="btn btn-primary" onclick="downloadExport(\'csv\')">下载 CSV</button><button class="btn btn-secondary" onclick="downloadExport(\'json\')">下载 JSON</button><button class="btn btn-secondary" onclick="downloadExport(\'txt\')">下载 TXT</button><button class="btn btn-secondary" onclick="hideExportPanel()">收起</button>'}else if(d.status==="error"){document.getElementById("exportPanelActions").innerHTML='<button class="btn btn-secondary" onclick="hideExportPanel()">关闭</button>';document.getElementById("exportPanelMessage").innerHTML='<span style="color:#dc2626">'+escHtml(d.error||"未知错误")+"</span>"}else{document.getElementById("exportPanelActions").innerHTML='<button class="btn btn-secondary" onclick="cancelExport()">取消</button>'}updateLayout()}
function hideExportPanel(){document.getElementById("exportPanel").classList.remove("show");updateLayout()}
function setSearchBusy(busy,label){var btn=document.getElementById("searchBtn");btn.disabled=!!busy;if(busy)btn.textContent=label||"处理中...";else refreshModeButton()}
function pollProgress(){if(!exportTaskId)return;if(exportPollTimer)clearInterval(exportPollTimer);exportPollTimer=setInterval(function(){fetch("/api/progress?task_id="+exportTaskId).then(function(r){return r.json()}).then(function(data){if(!data.success){clearInterval(exportPollTimer);exportPollTimer=null;setSearchBusy(false);var err=formatApiError(data,"任务状态不可用");if(progressUiMode==="panel")showExportPanelError(err);else{document.getElementById("progressTitle").textContent="导出失败";document.getElementById("progressDetails").innerHTML='<span style="color:#dc2626">'+escHtml(err)+"</span>";document.getElementById("progressActions").innerHTML='<button class="btn btn-secondary" onclick="hideOverlay()">关闭</button>'}return}var d=data.data,pct=(Math.max(0,Math.min(d.progress||0,1))*100).toFixed(1);if(progressUiMode==="panel")updateExportPanel(d,pct);else{document.getElementById("progressFill").style.width=pct+"%";document.getElementById("progressDetails").innerHTML=renderProgressDetails(d,pct)}if(d.status==="done"){clearInterval(exportPollTimer);exportPollTimer=null;setSearchBusy(false);if(progressUiMode==="panel")updateExportPanel(d,"100.0");else{document.getElementById("progressTitle").textContent=d.kind==="batch"?"批量导出完成":"导出完成";document.getElementById("progressActions").innerHTML='<button class="btn btn-primary" onclick="downloadExport(\'csv\')">下载 CSV</button><button class="btn btn-secondary" onclick="downloadExport(\'json\')">下载 JSON</button><button class="btn btn-secondary" onclick="downloadExport(\'txt\')">下载 TXT</button><button class="btn btn-secondary" onclick="hideOverlay()">关闭</button>'}}else if(d.status==="error"){clearInterval(exportPollTimer);exportPollTimer=null;setSearchBusy(false);if(progressUiMode==="panel")updateExportPanel(d,pct);else{document.getElementById("progressTitle").textContent="导出失败";document.getElementById("progressDetails").innerHTML='<span style="color:#dc2626">'+escHtml(d.error||"未知错误")+"</span>";document.getElementById("progressActions").innerHTML='<button class="btn btn-secondary" onclick="hideOverlay()">关闭</button>'}}}).catch(function(e){clearInterval(exportPollTimer);exportPollTimer=null;setSearchBusy(false);if(progressUiMode==="panel")showExportPanelError("网络错误: "+e.message);else{document.getElementById("progressTitle").textContent="导出失败";document.getElementById("progressDetails").innerHTML='<span style="color:#dc2626">网络错误: '+escHtml(e.message)+"</span>";document.getElementById("progressActions").innerHTML='<button class="btn btn-secondary" onclick="hideOverlay()">关闭</button>'}})},800)}
function cancelExport(){if(exportTaskId)document.getElementById("cancelOverlay").classList.add("show")}
function confirmCancel(save){if(!exportTaskId)return;document.getElementById("cancelOverlay").classList.remove("show");var discard=save?"0":"1";if(progressUiMode==="panel"){document.getElementById("exportPanelState").textContent="取消中";document.getElementById("exportPanelActions").innerHTML="";document.getElementById("exportPanelMessage").textContent="取消请求已发送，正在等待当前请求结束..."}else{document.getElementById("progressTitle").textContent="正在取消";document.getElementById("progressActions").innerHTML="";document.getElementById("progressDetails").innerHTML="取消请求已发送，正在等待当前请求结束..."}fetch("/api/progress/cancel?task_id="+exportTaskId+"&discard="+discard,{method:"POST"})}
function hideCancelConfirm(){document.getElementById("cancelOverlay").classList.remove("show")}
function downloadExport(format){if(!exportTaskId)return;fetch("/api/export/download?task_id="+exportTaskId+"&format="+format).then(function(r){if(!r.ok)return r.json().then(function(j){throw new Error(j.error||("HTTP "+r.status))});var cd=r.headers.get("Content-Disposition")||"",m=cd.match(/filename="([^"]*)"/),name=m&&m[1]?m[1]:("fofa_export."+format);return r.blob().then(function(b){var u=URL.createObjectURL(b),a=document.createElement("a");a.href=u;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(function(){URL.revokeObjectURL(u)},1000)})}).catch(function(e){showMessage("error","下载失败: "+e.message)})}
function showOverlay(title){document.getElementById("progressTitle").textContent=title;document.getElementById("progressFill").style.width="0%";document.getElementById("progressDetails").innerHTML="初始化中...";document.getElementById("progressActions").innerHTML='<button class="btn btn-secondary" onclick="cancelExport()">取消</button>';document.getElementById("progressOverlay").classList.add("show")}
function hideOverlay(){document.getElementById("progressOverlay").classList.remove("show")}
function renderResults(data){var area=document.getElementById("resultsArea"),rows=data.results||[],table=document.getElementById("resultsTable"),empty=document.getElementById("emptyState");previewRendered=true;syncModeContent();var pickBtns='<button class="mini-btn" id="pickFilterBtn" onclick="enterPickMode(\'filter\')">不看</button><button class="mini-btn" id="pickQueryBtn" onclick="enterPickMode(\'query\')">选取查询</button>';var actions=rows.length>0?'<div class="stats-actions"><span class="preview-status" id="previewStatus"></span>'+pickBtns+'<button class="mini-btn" onclick="exportPreview(&quot;csv&quot;)">导出 CSV</button><button class="mini-btn" onclick="exportPreview(&quot;json&quot;)">JSON</button><button class="mini-btn" onclick="exportPreview(&quot;txt&quot;)">TXT</button></div>':"";document.getElementById("statsBar").innerHTML='<div class="stats-metrics"><span class="stat-item"><span class="stat-dot" style="background:var(--accent)"></span>总计: <span class="stat-value">'+(data.total||0).toLocaleString()+'</span></span><span class="stat-item"><span class="stat-dot" style="background:var(--success)"></span>独立IP: <span class="stat-value">'+(data.unique_ips||0).toLocaleString()+'</span></span><span class="stat-item"><span class="stat-dot" style="background:var(--warning)"></span>结果: <span class="stat-value">'+rows.length.toLocaleString()+'</span></span></div>'+actions;var cols=data.columns||[];if(cols.length===0&&rows.length>0)cols=Object.keys(rows[0]);currentColumns=cols;if(rows.length===0){table.style.display="none";empty.style.display="block";empty.textContent=excludedFilters.length?"所有结果已被「不看」排除，移除排除项可恢复显示。":((data.total||0)>0?"当前预览没有返回记录，可调大数量或更换字段后重试。":"没有匹配结果。");document.querySelector("#resultsTable thead").innerHTML="";document.querySelector("#resultsTable tbody").innerHTML="";updateLayout();return}table.style.display="table";empty.style.display="none";var thead="";cols.forEach(function(col){var sc=sortColumn===col?" sorted":"";thead+="<th class=\""+sc+"\" onclick=\"sortBy('"+escHtml(col)+"')\">"+(sortColumn===col?(sortAsc?"▲ ":"▼ "):"")+escHtml(col)+"</th>"});document.querySelector("#resultsTable thead").innerHTML="<tr>"+thead+"</tr>";currentView=rows;vsLastWindow=null;stabilizeColumnWidths();setupVirtualScroll();updateLayout();renderVirtual()}
function buildRowsHtml(pageRows,cols){var html="";pageRows.forEach(function(row){html+="<tr>";cols.forEach(function(col){var val=row[col]!==undefined?row[col]:"",cls=(col==="ip"||col==="port"||col==="host")?" mono":"";if((col==="host"||col==="url")&&val){var url=val.indexOf("http")===0?val:"http://"+val;html+='<td class="'+escAttr(cls)+'"><a href="'+escAttr(url)+'" target="_blank" rel="noopener">'+escHtml(val)+"</a></td>"}else html+='<td class="'+escAttr(cls)+'" title="'+escAttr(val)+'">'+escHtml(val)+"</td>"});html+="</tr>"});return html}
function getScrollBox(){return document.getElementById("resultsTable").parentElement}
function measureRowHeight(){var cols=currentColumns,probe=currentView[0]||{},tbody=document.querySelector("#resultsTable tbody");var n=Math.min(8,currentView.length||1),rows=[];for(var k=0;k<n;k++)rows.push(probe);tbody.innerHTML=buildRowsHtml(rows,cols);vsLastWindow=null;var h=tbody.offsetHeight;return h>0?h/n:31}
var colWidthsRef=null;var fitToWindow=true;function toggleFitToWindow(el){fitToWindow=el.checked;colWidthsRef=null;stabilizeColumnWidths();renderVirtual()}function stabilizeColumnWidths(){var table=document.getElementById("resultsTable");var oldCg=table.querySelector("colgroup");if(colWidthsRef===currentResults&&oldCg)return;colWidthsRef=currentResults;var cols=currentColumns;if(oldCg)oldCg.remove();if(!cols.length||!currentResults.length){table.style.tableLayout="";table.style.width="";return}var tbody=document.querySelector("#resultsTable tbody");var probeRows=currentResults.slice(0,Math.min(100,currentResults.length));tbody.innerHTML=buildRowsHtml(probeRows,cols);var firstRow=tbody.querySelector("tr");if(!firstRow){table.style.tableLayout="";table.style.width="";return}table.style.width="auto";table.style.tableLayout="auto";var stackH=tbody.offsetHeight;if(stackH>0&&probeRows.length>1){var eff=stackH/probeRows.length;if(eff>0)rowHeight=eff}else{var h=firstRow.offsetHeight;if(h>0)rowHeight=h}var widths=[];firstRow.querySelectorAll("td").forEach(function(td){widths.push(td.offsetWidth)});table.style.width="";var cg=document.createElement("colgroup");if(fitToWindow){var total=0;widths.forEach(function(w){total+=w});cols.forEach(function(col,i){var el=document.createElement("col");var w=widths[i]||100;el.style.width=total>0?((w/total)*100).toFixed(3)+"%":w+"px";cg.appendChild(el)})}else{cols.forEach(function(col,i){var el=document.createElement("col");el.style.width=(widths[i]||100)+"px";cg.appendChild(el)})}table.insertBefore(cg,table.firstChild);table.style.tableLayout="fixed";vsLastWindow=null}
function renderVirtual(){var box=getScrollBox();if(!box)return;var total=currentView.length,tbody=document.querySelector("#resultsTable tbody");if(total===0){if(tbody.childNodes.length)tbody.innerHTML="";vsLastWindow=null;return}if(!rowHeight)rowHeight=measureRowHeight();var cols=currentColumns,vh=box.clientHeight||parseFloat(box.style.maxHeight)||0;if(vh<=0)return;var st=box.scrollTop;var start=Math.max(0,Math.floor(st/rowHeight)-OVERSCAN);var end=Math.min(total,Math.ceil((st+vh)/rowHeight)+OVERSCAN);if(vsLastWindow&&vsLastWindow[0]===start&&vsLastWindow[1]===end&&vsLastWindow[2]===cols.length)return;if(!vsLastWindow){tbody.innerHTML=""}else if(vsLastWindow[2]!==cols.length){tbody.innerHTML=""}if(!tbody.childNodes.length){tbody.appendChild(document.createElement("tr"));tbody.appendChild(document.createElement("tr"))}var topSpacer=tbody.firstChild,bottomSpacer=tbody.lastChild;var need=2+(end-start);while(tbody.childNodes.length>need)tbody.removeChild(bottomSpacer.previousSibling);while(tbody.childNodes.length<need)tbody.insertBefore(document.createElement("tr"),bottomSpacer);topSpacer.style.height=(start*rowHeight)+"px";topSpacer.style.padding="0";topSpacer.style.border="0";if(topSpacer._striped!==false){topSpacer.classList.remove("vs-stripe");topSpacer._striped=false}topSpacer._idx=null;var tds=topSpacer.childNodes;while(tds.length>1)topSpacer.removeChild(tds.lastChild);if(!tds.length){var td=document.createElement("td");td.colSpan=cols.length;td.style.padding="0";td.style.border="0";topSpacer.appendChild(td)}else{tds[0].colSpan=cols.length;tds[0].style.padding="0";tds[0].style.border="0";if(tds[0].innerHTML)tds[0].innerHTML=""}bottomSpacer.style.height=((total-end)*rowHeight)+"px";bottomSpacer.style.padding="0";bottomSpacer.style.border="0";if(bottomSpacer._striped!==false){bottomSpacer.classList.remove("vs-stripe");bottomSpacer._striped=false}bottomSpacer._idx=null;var btds=bottomSpacer.childNodes;while(btds.length>1)bottomSpacer.removeChild(btds.lastChild);if(!btds.length){var btd=document.createElement("td");btd.colSpan=cols.length;btd.style.padding="0";btd.style.border="0";bottomSpacer.appendChild(btd)}else{btds[0].colSpan=cols.length;btds[0].style.padding="0";btds[0].style.border="0";if(btds[0].innerHTML)btds[0].innerHTML=""}var dataNodes=[];for(var k=1;k<tbody.childNodes.length-1;k++)dataNodes.push(tbody.childNodes[k]);var stale=[];for(var k=0;k<dataNodes.length;k++){var n=dataNodes[k];if(n._idx>=start&&n._idx<end){}else{stale.push(n)}}var stalePos=0;for(var i=start;i<end;i++){var match=null;for(var k=0;k<dataNodes.length;k++){var n=dataNodes[k];if(n._idx===i){match=n;break}}if(match){tbody.insertBefore(match,bottomSpacer)}else{var reuse=stalePos<stale.length?stale[stalePos++]:null;if(reuse){updateRowNode(reuse,currentView[i],cols,i);reuse._idx=i;tbody.insertBefore(reuse,bottomSpacer)}else{var fresh=document.createElement("tr");updateRowNode(fresh,currentView[i],cols,i);fresh._idx=i;tbody.insertBefore(fresh,bottomSpacer)}}}vsLastWindow=[start,end,cols.length]}
function updateRowNode(tr,row,cols,rowIndex){if(tr.style.height)tr.style.height="";if(tr.style.padding)tr.style.padding="";if(tr.style.border)tr.style.border="";var striped=rowIndex%2===1;if(tr._striped!==striped){tr.classList.toggle("vs-stripe",striped);tr._striped=striped}var need=cols.length,cells=tr.childNodes;while(cells.length>need)tr.removeChild(cells.lastChild);for(var c=0;c<need;c++){var col=cols[c],val=row[col]!==undefined?row[col]:"",isLink=(col==="host"||col==="url")&&val,cls=(col==="ip"||col==="port"||col==="host")?" mono":"",td=cells[c];if(!td){td=document.createElement("td");tr.appendChild(td)}else{if(td.style.padding)td.style.padding="";if(td.style.border)td.style.border="";if(td.style.height)td.style.height="";if(td.colSpan&&td.colSpan!==1)td.colSpan=1}if(td.className!==cls)td.className=cls;var url=val.indexOf("http")===0?val:"http://"+val;if(isLink){var a=td.firstChild;if(!a||a.tagName!=="A"){td.innerHTML="";a=document.createElement("a");a.target="_blank";a.rel="noopener";td.appendChild(a)}if(a.getAttribute("href")!==url)a.setAttribute("href",url);if(a.textContent!==val)a.textContent=val}else{var n=td.firstChild;if(td.childNodes.length!==1||n.nodeType!==3){td.innerHTML="";td.appendChild(document.createTextNode(val))}else if(n.nodeValue!==val){n.nodeValue=val}if(td.getAttribute("title")!==val)td.setAttribute("title",val)}}}
function setupVirtualScroll(){var box=getScrollBox();if(!box||box._vsBound)return;box._vsBound=true;var tick=false,scrollTimer=null;var table=document.getElementById("resultsTable");box.addEventListener("scroll",function(){if(table)table.classList.add("scrolling");if(scrollTimer)clearTimeout(scrollTimer);scrollTimer=setTimeout(function(){scrollTimer=null;if(table)table.classList.remove("scrolling")},180);if(tick)return;tick=true;requestAnimationFrame(function(){tick=false;renderVirtual()})})}
function previewTimestamp(){return new Date().toISOString().replace(/[-:]/g,"").replace(/\..+/,"").replace("T","_")}
function previewColumns(){return currentColumns.length?currentColumns:Object.keys(currentResults[0]||{})}
function previewRows(){var cols=previewColumns(),src=currentResults;if(excludedFilters.length){src=src.filter(function(r){return !excludedFilters.some(function(f){return String(r[f.field]||"")===String(f.value)})})}return src.map(function(row){var out={};cols.forEach(function(col){out[col]=row[col]!==undefined&&row[col]!==null?row[col]:""});return out})}
function csvCell(v){var s=v===undefined||v===null?"":String(v);return /[",\r\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s}
function previewUrl(row){var val=row.url||row.link||row.host||"";if(!val&&row.ip)val=row.ip;if(val&&row.host&&String(val).indexOf("http")!==0){var protocol=row.protocol?String(row.protocol).toLowerCase():"";if(protocol.indexOf(",")>-1)protocol=protocol.split(",")[0];if(!protocol)protocol=String(row.port)==="443"?"https":"http";val=protocol+"://"+val}return val}
function downloadPreviewBlob(content,filename,type){var blob=new Blob([content],{type:type}),url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download=filename;document.body.appendChild(a);a.click();a.remove();setTimeout(function(){URL.revokeObjectURL(url)},1000)}
function showPreviewStatus(text){var el=document.getElementById("previewStatus");if(el){el.textContent=text;updateLayout()}}
function exportPreview(format){if(!currentResults.length){showMessage("error","当前预览没有可导出的结果");return}var cols=previewColumns(),rows=previewRows(),ts=previewTimestamp(),content="",filename="fofatoto_preview_"+ts+"."+format,type="text/plain;charset=utf-8";var src=currentResults;if(excludedFilters.length){src=src.filter(function(r){return !excludedFilters.some(function(f){return String(r[f.field]||"")===String(f.value)})})}var exportedCount=0;if(format==="csv"){content="\ufeff"+[cols.map(csvCell).join(",")].concat(rows.map(function(row){return cols.map(function(col){return csvCell(row[col])}).join(",")})).join("\r\n")+"\r\n";type="text/csv;charset=utf-8";exportedCount=rows.length}else if(format==="json"){content=JSON.stringify(rows,null,2)+"\n";type="application/json;charset=utf-8";exportedCount=rows.length}else{var values;if(cols.length===1&&cols[0]==="ip")values=src.map(function(row){return row.ip||""});else if(cols.length===1&&cols[0]==="domain")values=src.map(function(row){return row.domain||""});else values=src.map(previewUrl);values=values.filter(function(v){return v});exportedCount=values.length;content=values.join("\n")+"\n"}downloadPreviewBlob(content,filename,type);clearMessage();showPreviewStatus("已导出 "+exportedCount.toLocaleString()+" 条")}
function sortValueCompare(a,b){var na=Number(a),nb=Number(b);if(a!==""&&b!==""&&!isNaN(na)&&!isNaN(nb))return na<nb?-1:(na>nb?1:0);return a<b?-1:(a>b?1:0)}
function sortBy(col){if(sortColumn===col){sortAsc=!sortAsc}else{sortColumn=col;sortAsc=true}currentResults.sort(function(a,b){var r=sortValueCompare(a[col]||"",b[col]||"");return sortAsc?r:-r});renderCurrentView()}
var pickModeActive=false,pickModeAction="query",excludedFilters=[];
function enterPickMode(mode){if(!currentResults.length){showMessage("error","当前预览没有可选取的结果");return}if(pickModeActive)return;pickModeActive=true;pickModeAction=mode;var t=document.getElementById("resultsTable");t.classList.add("picking");var bId=mode==="filter"?"pickFilterBtn":"pickQueryBtn",b=document.getElementById(bId);if(b)b.classList.add("pick-active");t.addEventListener("click",pickTableClick,true);document.addEventListener("keydown",pickKeyHandler);showPreviewStatus(mode==="filter"?"不看：点击单元格排除该值，Esc 取消":"加入查询：点击单元格选取值加入查询，Esc 取消")}
function exitPickMode(){if(!pickModeActive)return;pickModeActive=false;var t=document.getElementById("resultsTable");if(t){t.classList.remove("picking");t.removeEventListener("click",pickTableClick,true)}["pickFilterBtn","pickQueryBtn"].forEach(function(id){var b=document.getElementById(id);if(b)b.classList.remove("pick-active")});document.removeEventListener("keydown",pickKeyHandler);showPreviewStatus(excludedFilters.length?("已排除 "+excludedFilters.length+" 项"):"")}
function pickTableClick(e){if(!pickModeActive)return;var td=e.target.closest?e.target.closest("td"):null;if(!td)return;e.preventDefault();e.stopPropagation();var idx=td.cellIndex;if(idx<0||idx>=currentColumns.length)return;var field=currentColumns[idx],value=(td.textContent||"").trim();exitPickMode();if(pickModeAction==="filter")addExclusion(field,value);else applyQueryPick(field,value)}
function pickKeyHandler(e){if(e.key==="Escape"){e.preventDefault();exitPickMode()}}
function applyQueryPick(field,value){var safe=value.replace(/"/g,'\\"');var frag=field+'="'+safe+'"';var input=document.getElementById("queryInput"),cur=input.value.trim();if(!cur)input.value=frag;else if(/(&&|\|\|)\s*$/.test(cur))input.value=cur+" "+frag;else input.value=cur+" && "+frag;autoResizeQueryInput();input.focus();if(document.getElementById("instantAutoQuery").checked)executeSearch()}
function addExclusion(field,value){for(var i=0;i<excludedFilters.length;i++){if(excludedFilters[i].field===field&&excludedFilters[i].value===value)return}excludedFilters.push({field:field,value:value});renderCurrentView()}
function removeExclusion(index){if(index<0||index>=excludedFilters.length)return;excludedFilters.splice(index,1);renderCurrentView()}
function renderExclusionChips(){var c=document.getElementById("exclusionChips");if(!c)return;var h="";excludedFilters.forEach(function(f,i){h+='<span class="exc-chip">不看 '+escHtml(f.field)+'="'+escHtml(f.value)+'"<span class="exc-x" onclick="removeExclusion('+i+')">&times;</span></span>'});c.innerHTML=h}
function renderCurrentView(){var view=currentResults,ips={};if(excludedFilters.length){view=currentResults.filter(function(r){return !excludedFilters.some(function(f){return String(r[f.field]||"")===String(f.value)})})}view.forEach(function(r){if(r.ip)ips[r.ip]=1});renderResults({results:view,columns:currentColumns,total:currentResults.length,unique_ips:Object.keys(ips).length});renderExclusionChips();if(excludedFilters.length)showPreviewStatus("已排除 "+excludedFilters.length+" 项，显示 "+view.length+"/"+currentResults.length)}
function toggleSettings(e){if(e)e.stopPropagation();var p=document.getElementById("settingsPopup");p.classList.toggle("show")}
function clearResults(){exitPickMode();excludedFilters=[];currentView=[];rowHeight=0;vsLastWindow=null;renderExclusionChips();previewRendered=false;document.getElementById("resultsArea").style.display="none";document.getElementById("resultsTable").style.display="table";document.getElementById("emptyState").style.display="none";document.querySelector("#resultsTable thead").innerHTML="";document.querySelector("#resultsTable tbody").innerHTML="";currentResults=[];currentColumns=[];sortColumn=null;updateLayout()}
function updateShellHeight(){var header=document.querySelector(".header");if(header)document.documentElement.style.setProperty("--header-height",Math.ceil(header.getBoundingClientRect().height)+"px")}
function updateLayout(){syncModeContent();updateShellHeight();fitHistoryDropdown();fitResultsHeight()}
function shellBottom(){var shell=document.querySelector(".container");return shell?shell.getBoundingClientRect().bottom:window.innerHeight}
function fitResultsHeight(){var area=document.getElementById("resultsArea"),box=document.querySelector("#resultsArea .table-container");if(!area||!box||area.style.display==="none")return;var rect=box.getBoundingClientRect(),pad=window.innerWidth<=760?12:24,minH=window.innerHeight<560?120:180,msgEl=document.getElementById("messageArea"),msgH=msgEl&&msgEl.offsetHeight?msgEl.offsetHeight+12:0,available=shellBottom()-rect.top-pad-2-msgH;box.style.maxHeight=Math.max(minH,available)+"px"}
function showMessage(type,text){document.getElementById("messageArea").innerHTML='<div class="message '+type+'">'+escHtml(text)+"</div>";updateLayout()}
function clearMessage(){document.getElementById("messageArea").innerHTML="";updateLayout()}
function getHistory(){try{return JSON.parse(localStorage.getItem("fofa_query_history")||"[]")}catch(e){return[]}}
function saveHistory(history){localStorage.setItem("fofa_query_history",JSON.stringify(history))}
function getShowHistory(){try{return localStorage.getItem("fofa_show_history")!=="0"}catch(e){return true}}
function setShowHistory(v){try{localStorage.setItem("fofa_show_history",v?"1":"0")}catch(e){}}
function toggleShowHistory(el){setShowHistory(el.checked);if(!el.checked)closeHistorySuggestions()}
function addToHistory(query){try{var history=getHistory();history=history.filter(function(h){return h.query!==query});history.unshift({query:query,mode:currentMode,time:Date.now()});if(history.length>50)history=history.slice(0,50);saveHistory(history);updateHistoryCount()}catch(e){}}
function updateHistoryCount(){var el=document.getElementById("historyCount");if(el)el.textContent=getHistory().length}
function fitHistoryDropdown(){var dd=document.getElementById("historyDropdown");if(!dd||!dd.classList.contains("show"))return;var rect=dd.getBoundingClientRect(),minH=window.innerHeight<520?120:160,maxH=Math.max(minH,shellBottom()-rect.top-12);dd.style.maxHeight=Math.min(320,maxH)+"px"}
function renderHistorySuggestions(showAll){var dd=document.getElementById("historyDropdown"),input=document.getElementById("queryInput");if(!dd||!input)return false;if(!getShowHistory())return false;var q=showAll?"":input.value.trim().toLowerCase(),history=getHistory(),items=[];history.forEach(function(h,i){if(!q||String(h.query||"").toLowerCase().indexOf(q)>-1)items.push({item:h,index:i})});historyVisibleItems=items.slice(0,20);historyActiveIndex=-1;if(!historyVisibleItems.length){closeHistorySuggestions();return false}var html="";historyVisibleItems.forEach(function(entry){var h=entry.item,ml=h.mode==="instant"?"即":(h.mode==="export"?"深":"批");html+='<div class="history-item" data-history-index="'+entry.index+'" onclick="insertHistory('+entry.index+')"><span class="query-text" title="'+escAttr(h.query)+'">['+ml+"] "+escHtml(h.query)+'</span><span class="history-actions"><button class="h-act del" onclick="event.stopPropagation();deleteHistory('+entry.index+')">删除</button></span></div>'});dd.innerHTML=html;dd.classList.add("show");fitHistoryDropdown();return true}
function closeHistorySuggestions(){var dd=document.getElementById("historyDropdown");if(dd){dd.classList.remove("show");dd.style.maxHeight="";dd.innerHTML=""}historyActiveIndex=-1;historyVisibleItems=[]}
function moveHistorySelection(step){if(!historyVisibleItems.length)return;historyActiveIndex=(historyActiveIndex+step+historyVisibleItems.length)%historyVisibleItems.length;document.querySelectorAll("#historyDropdown .history-item").forEach(function(el,i){el.classList.toggle("active",i===historyActiveIndex);if(i===historyActiveIndex)el.scrollIntoView({block:"nearest"})})}
function pickActiveHistory(){if(historyActiveIndex<0||!historyVisibleItems[historyActiveIndex])return false;insertHistory(historyVisibleItems[historyActiveIndex].index);return true}
function toggleHistory(){var dd=document.getElementById("historyDropdown");if(dd&&dd.classList.contains("show"))closeHistorySuggestions();else renderHistorySuggestions(true)}
function insertHistory(index){try{var history=getHistory();if(history[index]){document.getElementById("queryInput").value=history[index].query;autoResizeQueryInput();switchMode(history[index].mode||"instant");closeHistorySuggestions();document.getElementById("queryInput").focus()}}catch(e){}}
function deleteHistory(index){try{var history=getHistory();history.splice(index,1);saveHistory(history);updateHistoryCount();renderHistorySuggestions()}catch(e){}}
document.addEventListener("click",function(e){if(!e.target.closest(".search-input-wrap"))closeHistorySuggestions();if(!e.target.closest(".settings-wrap"))document.getElementById("settingsPopup").classList.remove("show")});
function escHtml(str){var div=document.createElement("div");div.appendChild(document.createTextNode(str));return div.innerHTML}
function escAttr(str){return escHtml(str).replace(/"/g,'&quot;').replace(/'/g,'&#39;')}
</script>
</body>
</html>"""


def render_web_html() -> str:
    return (
        WEB_HTML_TEMPLATE.replace("__APP_VERSION__", APP_VERSION)
        .replace("__GITHUB_URL__", GITHUB_URL)
        .replace(
            "__FIELD_CATEGORIES_JSON__",
            json.dumps(WEB_FIELD_CATEGORIES, ensure_ascii=False),
        )
        .replace(
            "__DEFAULT_FIELDS_JSON__",
            json.dumps(DEFAULT_FIELD_LIST, ensure_ascii=False),
        )
    )


# ============ 配置相关 ============


class ConfigManager:
    """配置管理器"""

    def __init__(self):
        self.config_dir = self._get_config_dir()
        self.config_file = self.config_dir / "config.json"
        self.url = ""
        self.key = ""
        self.last_error = ""
        self._client = None
        self._client_signature = None

    def _get_config_dir(self) -> Path:
        """获取配置目录。

        Nuitka onefile 模式下，bootstrap 在子进程环境注入 `NUITKA_ONEFILE_DIRECTORY`，
        指向用户运行的原始可执行文件所在目录（解压出的临时目录不可用作配置目录，
        进程退出即清理）。优先使用它；普通 Python 脚本模式回退到 sys.argv[0]/__file__。

        注意：`NUITKA_ONEFILE_PARENT` 是 Nuitka 内部的进程 PID 标识
        （`GetCurrentProcessId()`/`getpid()`），不是路径，不可用作配置目录——
        v1.2.1 曾误用导致 config 被写入 `CWD\\<PID>\\config.json` 后丢失。
        """
        onefile_directory = os.environ.get("NUITKA_ONEFILE_DIRECTORY")
        if onefile_directory:
            return Path(onefile_directory).resolve()

        entry = Path(sys.argv[0] if sys.argv and sys.argv[0] else __file__).resolve()
        return entry.parent

    def ensure_exists(self) -> bool:
        """检测配置文件是否存在，如不存在则自动生成默认配置文件"""
        if self.config_file.exists():
            return True

        try:
            self.config_file.write_text(
                json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=4),
                encoding="utf-8",
            )
            print(f"[*] 已自动生成配置文件: {self.config_file}")
            print("[*] 请编辑配置文件填入你的 FOFA API Key 后重试")
            return False
        except Exception as e:
            self.last_error = str(e)
            print(f"[!] 创建配置文件失败: {e}", file=sys.stderr)
            return False

    def load(self):
        """加载配置"""
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text(encoding="utf-8"))
                self.url = data.get("url", "")
                self.key = data.get("key", "")
            except Exception as e:
                self.last_error = str(e)
                print(f"[警告] 读取 config.json 失败: {e}", file=sys.stderr)
        return self

    def is_valid(self) -> bool:
        """验证配置是否有效"""
        placeholder_keys = {
            DEFAULT_CONFIG["key"],
            "your-api-key",
            "your_fofa_api_key_here",
        }
        return bool(self.url and self.key and self.key not in placeholder_keys)

    def public_status(self) -> dict:
        """返回可安全展示给 Web UI 的配置状态。

        每次调用前重新读取配置，支持热更新：Web UI 无需重启即可
        感知 config.json 的最新变化（用于配置引导提示和状态展示）。
        """
        self.load()
        return {
            "configured": self.is_valid(),
            "config_path": str(self.config_file),
            "config_template": json.dumps(
                DEFAULT_CONFIG, ensure_ascii=False, indent=4
            ),
            "error": self.last_error,
        }

    def get_client(self) -> Optional[FofaClient]:
        """按需重新读取配置并返回有效 client；配置未变化时复用缓存。

        用于 Web UI 热更新：用户修改 config.json 后无需重启服务，
        下次请求会检测到配置变化并重建 FofaClient。
        """
        self.load()
        if not self.is_valid():
            self._client = None
            self._client_signature = None
            return None
        info_api = _detect_relay_info_api(self.url, self.key)
        signature = (self.url, self.key, info_api)
        if self._client is None or self._client_signature != signature:
            self._client = FofaClient(self.url, self.key, info_api=info_api)
            self._client_signature = signature
        return self._client


# ============ FOFA API 相关 ============


@dataclass
class FofaResult:
    """单条查询结果"""

    host: str = ""
    ip: str = ""
    port: str = ""
    protocol: str = ""
    domain: str = ""
    title: str = ""
    server: str = ""
    country: str = ""
    city: str = ""
    lastupdatetime: str = ""
    asn: str = ""
    org: str = ""
    os: str = ""
    icp: str = ""
    jarm: str = ""
    header: str = ""
    banner: str = ""
    cert: str = ""
    product: str = ""
    product_category: str = ""
    version: str = ""
    cname: str = ""
    latitude: str = ""
    longitude: str = ""
    region: str = ""
    country_name: str = ""
    base_protocol: str = ""
    link: str = ""
    _extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        # 浅拷贝即可（字段均为 str/dict，后续不改写 _extra 本身），
        # 避免 asdict() 递归深拷贝拖慢大批量导出
        result = dict(self.__dict__)
        result.update(self._extra)
        for key in list(result.keys()):
            if key.startswith("_"):
                del result[key]
                continue
            if result[key] == "" and key not in self._extra:
                del result[key]
        return result


# ============ 字段清单（单一来源） ============

# 全部已知 FOFA 字段，顺序同 FofaResult 声明序（决定默认导出列序）。
# 新增 FOFA 字段时只需两处：FofaResult 加字段 + WEB_FIELD_CATEGORIES 归类，
# 模块加载时校验两份清单一致，其余引用方（API 解析/导出/Web UI）自动生效。
ALL_FIELD_NAMES: list[str] = [
    name for name in FofaResult.__dataclass_fields__ if name != "_extra"
]
# search() 解析 API 返回时的已知字段快速判断
KNOWN_FIELDS: frozenset[str] = frozenset(ALL_FIELD_NAMES)
# 本地自定义字段：FOFA API 不提供，url 由 host/ip/port/protocol 本地拼接
CUSTOM_FIELDS: frozenset[str] = frozenset({"url"})


def _validate_web_field_categories() -> None:
    """校验 Web 字段分组与字段全集一一对应，防止多处清单漂移。"""
    listed = [f for cat in WEB_FIELD_CATEGORIES for f in cat["fields"]]
    expected = KNOWN_FIELDS | CUSTOM_FIELDS
    if len(listed) != len(set(listed)) or set(listed) != expected:
        missing = sorted(expected - set(listed))
        extra = sorted(set(listed) - expected)
        duplicated = sorted({f for f in listed if listed.count(f) > 1})
        raise ValueError(
            "WEB_FIELD_CATEGORIES 与 FofaResult 字段全集不一致："
            f"缺失={missing} 多余={extra} 重复={duplicated}"
        )


_validate_web_field_categories()


@dataclass
class SearchStats:
    """查询统计信息"""

    total: int = 0
    unique_ips: int = 0
    results: list = field(default_factory=list)
    total_quota_used: int = 0
    partial: bool = False
    partial_error: str = ""


class FofaAPIError(Exception):
    """FOFA API 错误"""

    pass


def _is_retryable_api_error(message: str) -> bool:
    text = str(message).lower()
    retryable_markers = (
        "[-501]",
        "服务错误",
        "稍候重试",
        "timeout",
        "timed out",
        "temporar",
        "try again",
    )
    return any(marker in text for marker in retryable_markers)


def _retry_sleep_seconds(error: Exception, attempt: int) -> int:
    if _is_retryable_api_error(str(error)):
        return min(10 * attempt, 30)
    return min(2 * attempt, 8)


def _sleep_interruptible(
    seconds: float, cancel_check: Optional[Callable[[], bool]] = None
) -> None:
    """分片休眠并周期检查取消标志，取消时抛 KeyboardInterrupt 立即中断。

    FOFA 限流休眠最长 60s、重试退避最长 30s，整段 time.sleep 会让
    Web UI 的「取消导出」等到休眠结束才生效。
    """
    if cancel_check is None:
        time.sleep(seconds)
        return
    deadline = time.monotonic() + seconds
    while True:
        if cancel_check():
            raise KeyboardInterrupt()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.25, remaining))


def _field_names(fields: str) -> list[str]:
    return [f.strip() for f in fields.split(",") if f.strip()]


def _append_missing_fields(fields: str, required_fields: list[str]) -> str:
    requested = set(_field_names(fields))
    missing = [f for f in required_fields if f not in requested]
    if missing:
        fields = (fields + "," if fields else "") + ",".join(missing)
    return fields


def _api_fields(fields: str) -> str:
    """将用户请求字段转为 FOFA API 实际接受的字段列表。

    url 是本工具自定义字段（由 host/ip/port/protocol 本地拼接），
    FOFA API 并不提供，直接传入会返回 HTTP 400，必须剥离；
    同时确保拼接所需的 host,ip,port,protocol 字段存在。
    """
    requested = _field_names(fields)
    if "url" not in requested:
        return fields
    fields = ",".join(f for f in requested if f != "url")
    return _append_missing_fields(fields, ["host", "ip", "port", "protocol"])


def _infer_domain_from_host(host: str) -> str:
    """从 host 或 URL 中提取可用 domain，IP 字面量返回空字符串"""
    parsed = urlparse(host if host.startswith("http") else f"//{host}")
    hostname = parsed.hostname or host
    try:
        ipaddress.ip_address(hostname)
        return ""
    except ValueError:
        return hostname


def _detect_relay_info_api(base_url: str, key: str) -> str:
    """根据 base_url 域名自动检测已知中转站，返回对应的账户信息 API URL。

    按 RELAY_INFO_APIS 表进行域名后缀匹配。匹配不到则返回
    空字符串，回退到标准 FOFA /api/v1/info/my 接口。
    """
    try:
        host = urlparse(base_url.rstrip("/")).hostname or ""
    except Exception:
        return ""
    for domain, template in RELAY_INFO_APIS.items():
        if host == domain or host.endswith("." + domain):
            return template.replace("{base_url}", base_url.rstrip("/")).replace(
                "{key}", quote(key, safe="")
            )
    return ""


# ============ Icon 提取与 icon_hash ============

class IconExtractError(Exception):
    """favicon 提取 / icon_hash 计算失败"""

    pass


_ICON_HASH_RE = re.compile(r"^-?\d+$")
_FETCH_TIMEOUT = 10
_MAX_HTML_BYTES = 2 * 1024 * 1024
_MAX_ICON_BYTES = 5 * 1024 * 1024
_ICON_PREVIEW_MAX_BYTES = 512 * 1024
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _murmur3_32(data: bytes, seed: int = 0) -> int:
    """MurmurHash3 x86_32（纯 Python 实现），返回有符号 32 位整数。

    Shodan/FOFA 的 icon_hash 即 mmh3.hash() 的输出格式（负数很常见），
    标准库无 mmh3，故自实现以保持零依赖。
    """
    c1, c2 = 0xCC9E2D51, 0x1B873593
    h = seed & 0xFFFFFFFF
    nblocks = len(data) & ~3
    for i in range(0, nblocks, 4):
        k = int.from_bytes(data[i : i + 4], "little")
        k = (k * c1) & 0xFFFFFFFF
        k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
        k = (k * c2) & 0xFFFFFFFF
        h ^= k
        h = ((h << 13) | (h >> 19)) & 0xFFFFFFFF
        h = (h * 5 + 0xE6546B64) & 0xFFFFFFFF
    tail = data[nblocks:]
    k = 0
    if len(tail) >= 3:
        k ^= tail[2] << 16
    if len(tail) >= 2:
        k ^= tail[1] << 8
    if tail:
        k ^= tail[0]
        k = (k * c1) & 0xFFFFFFFF
        k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
        k = (k * c2) & 0xFFFFFFFF
        h ^= k
    h ^= len(data)
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & 0xFFFFFFFF
    h ^= h >> 16
    return h - 0x100000000 if h & 0x80000000 else h


def favicon_hash(icon_bytes: bytes) -> str:
    """计算 FOFA/Shodan 约定的 icon_hash。

    编码用 base64.encodebytes（76 列换行 + 结尾换行），编码结果整体参与
    哈希，与 mmh3.hash(base64.encodebytes(icon)) 对齐。
    """
    return str(_murmur3_32(base64.encodebytes(icon_bytes)))


def build_icon_query(icon_hash: str, extra: str = "") -> str:
    """拼接 icon_hash 查询；extra 为附加过滤条件，自动加括号防外溢"""
    query = f'icon_hash="{icon_hash}"'
    extra = (extra or "").strip()
    if extra:
        query = f"{query} && ({extra})"
    return query


class _IconLinkParser(HTMLParser):
    """从 HTML 中提取 <link rel=...icon...> 的 href，按 rel 优先级取最优"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.icon_href: Optional[str] = None
        self._best_rank = 1 << 30

    @staticmethod
    def _rank(rel: str) -> int:
        tokens = set((rel or "").lower().split())
        if "icon" in tokens:
            return 0 if "shortcut" in tokens else 1
        if "apple-touch-icon-precomposed" in tokens:
            return 2
        if "apple-touch-icon" in tokens:
            return 3
        return -1

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "link":
            return
        attr = {k.lower(): (v or "") for k, v in attrs}
        href = attr.get("href", "").strip()
        if not href:
            return
        rank = self._rank(attr.get("rel", ""))
        if 0 <= rank < self._best_rank:
            self._best_rank = rank
            self.icon_href = href


def _decode_data_uri(href: str) -> Optional[bytes]:
    if not href.lower().startswith("data:"):
        return None
    try:
        header, sep, payload = href.partition(",")
        if not sep:
            return None
        if ";base64" in header.lower():
            return base64.b64decode(re.sub(r"\s+", "", payload))
        return unquote_to_bytes(payload)
    except Exception:
        return None


def _guess_content_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"GIF8"):
        return "image/gif"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    head = data.lstrip()[:256].lower()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in head):
        return "image/svg+xml"
    return "image/x-icon"


def _looks_like_icon(data: bytes, ctype: str) -> bool:
    if ctype.startswith("image/"):
        return True
    if "html" in ctype or not data:
        return False
    if data.startswith((b"\x00\x00\x01\x00", b"\x00\x00\x02\x00")):
        return True
    if data.startswith((b"\x89PNG", b"GIF8", b"\xff\xd8\xff")):
        return True
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return True
    return _guess_content_type(data) == "image/svg+xml"


def _fetch_url(url: str, max_bytes: int, accept: str = "*/*") -> tuple[bytes, str, str]:
    """下载 URL 内容，返回 (bytes, 最终 URL, content_type)。仅允许 http/https。"""
    if urlparse(url).scheme.lower() not in ("http", "https"):
        raise IconExtractError(f"仅支持 http/https: {url}")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _BROWSER_UA, "Accept": accept, "Accept-Language": "zh-CN,zh;q=0.9"},
    )
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT, context=ctx) as resp:
            data = resp.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise IconExtractError(f"响应超过大小上限 {max_bytes // (1024 * 1024)}MB: {url}")
            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            return data, resp.geturl(), ctype
    except IconExtractError:
        raise
    except urllib.error.HTTPError as e:
        raise IconExtractError(f"HTTP {e.code} {e.reason}: {url}")
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, (socket.timeout, TimeoutError)):
            raise IconExtractError(f"连接超时: {url}")
        if isinstance(reason, socket.gaierror):
            raise IconExtractError(f"域名解析失败: {url}")
        raise IconExtractError(f"连接失败: {reason}: {url}")
    except (socket.timeout, TimeoutError):
        raise IconExtractError(f"连接超时: {url}")
    except Exception as e:
        raise IconExtractError(f"抓取失败: {e}: {url}")


def _resolve_icon_from_url(url: str) -> tuple[bytes, str, str]:
    """抓取网页解析 icon 标签；目标本身是图片时直接作为 icon。

    返回 (icon_bytes, icon 来源 URL, content_type)。
    """
    data, final_url, ctype = _fetch_url(
        url, _MAX_HTML_BYTES, accept="text/html,application/xhtml+xml,image/*;q=0.8,*/*;q=0.5"
    )
    if _looks_like_icon(data, ctype):
        return data, final_url, ctype or _guess_content_type(data)

    parser = _IconLinkParser()
    try:
        parser.feed(data.decode("utf-8", errors="replace"))
        parser.close()
    except Exception:
        pass

    candidates = []
    if parser.icon_href:
        candidates.append(parser.icon_href)
    candidates.append(urljoin(final_url, "/favicon.ico"))

    last_error: Optional[Exception] = None
    for href in candidates:
        try:
            if href.lower().startswith("data:"):
                raw = _decode_data_uri(href)
                if not raw:
                    continue
                return raw, "(data: URI)", _guess_content_type(raw)
            icon_url = urljoin(final_url, href)
            raw, icon_final, icon_ctype = _fetch_url(icon_url, _MAX_ICON_BYTES, accept="image/*,*/*;q=0.8")
            return raw, icon_final, icon_ctype or _guess_content_type(raw)
        except Exception as e:
            last_error = e
            continue
    if last_error:
        raise IconExtractError(f"页面未找到可用图标（{last_error}）")
    raise IconExtractError(f"页面未找到可用图标: {url}")


def resolve_icon(target: str, allow_file: bool = True) -> dict:
    """解析目标的 favicon 并计算 icon_hash。

    target 支持三种形态：
    1. 原始 icon_hash 整数（-?\\d+）→ 直接返回，不产生网络请求
    2. 本地 icon 文件路径（仅 allow_file=True 的 CLI 场景）
    3. 网址（缺 scheme 时先补 https://，失败回退 http://；也可以直接
       指向图片 URL，如 https://x.com/favicon.ico）
    """
    target = (target or "").strip()
    if not target:
        raise IconExtractError("目标为空")

    def _result(icon_bytes: bytes, icon_url: str, ctype: str, source: str, icon_hash: str = "") -> dict:
        icon_hash = icon_hash or favicon_hash(icon_bytes)
        preview = ""
        if icon_bytes and len(icon_bytes) <= _ICON_PREVIEW_MAX_BYTES:
            b64 = base64.b64encode(icon_bytes).decode()
            preview = f"data:{ctype or _guess_content_type(icon_bytes)};base64,{b64}"
        return {
            "target": target,
            "source": source,
            "icon_hash": icon_hash,
            "icon_md5": hashlib.md5(icon_bytes).hexdigest() if icon_bytes else "",
            "icon_url": icon_url,
            "icon_size": len(icon_bytes),
            "content_type": ctype,
            "icon_bytes": icon_bytes,
            "icon_data_uri": preview,
        }

    if _ICON_HASH_RE.match(target):
        return _result(b"", "", "", "hash", icon_hash=target)

    if allow_file:
        path = Path(target)
        if path.is_file():
            raw = path.read_bytes()
            if len(raw) > _MAX_ICON_BYTES:
                raise IconExtractError(f"icon 文件超过大小上限 {_MAX_ICON_BYTES // (1024 * 1024)}MB")
            return _result(raw, str(path), _guess_content_type(raw), "file")

    if re.match(r"^https?://", target, re.I):
        attempts = [target]
    elif "://" in target:
        raise IconExtractError(f"仅支持 http/https: {target}")
    else:
        attempts = [f"https://{target}", f"http://{target}"]

    errors = []
    for url in attempts:
        try:
            raw, icon_url, ctype = _resolve_icon_from_url(url)
            return _result(raw, icon_url, ctype, "url")
        except IconExtractError as e:
            errors.append(str(e))
        except Exception as e:
            errors.append(f"{e}: {url}")
    raise IconExtractError("；".join(errors))


_ICON_CACHE: dict[str, dict] = {}
_ICON_CACHE_MAX = 64
_ICON_CACHE_LOCK = threading.Lock()


def resolve_icon_cached(target: str) -> dict:
    """resolve_icon 的带缓存版本（Web 端用，禁用本地文件输入）"""
    key = (target or "").strip()
    with _ICON_CACHE_LOCK:
        hit = _ICON_CACHE.get(key)
    if hit is not None:
        return hit
    info = resolve_icon(key, allow_file=False)
    with _ICON_CACHE_LOCK:
        while len(_ICON_CACHE) >= _ICON_CACHE_MAX:
            _ICON_CACHE.pop(next(iter(_ICON_CACHE)))
        _ICON_CACHE[key] = info
    return info


class FofaClient:
    """FOFA API 客户端"""

    def __init__(self, url: str, key: str, info_api: str = ""):
        self.base_url = url.rstrip("/")
        self.key = key
        self.info_api = info_api  # 中转站账户信息 API（由 _detect_relay_info_api 自动填充）

    def get_usage(self) -> dict:
        """
        获取账户信息。

        若自动识别到已知中转站，调用对应接口并将响应
        归一化为标准 FOFA 字段格式；否则调用标准 /api/v1/info/my 接口。

        Returns:
            包含用户信息的字典
        """
        if self.info_api:
            return self._get_usage_relay()
        api_url = f"{self.base_url}/api/v1/info/my?key={quote(self.key, safe='')}"
        try:
            resp = urllib.request.urlopen(api_url, timeout=10)
            data = json.loads(resp.read().decode())
            if data.get("error"):
                raise FofaAPIError(f"获取用量失败: {data.get('errmsg', '未知错误')}")
            return data
        except FofaAPIError:
            raise
        except Exception as e:
            err_msg = str(e).replace(self.key, "***") if self.key else str(e)
            raise FofaAPIError(f"获取用量失败: {err_msg}")

    def _get_usage_relay(self) -> dict:
        """通过中转站自定义 API 获取账户信息并归一化为标准字段。"""
        try:
            resp = urllib.request.urlopen(self.info_api, timeout=10)
            data = json.loads(resp.read().decode())
        except Exception as e:
            err_msg = str(e).replace(self.key, "***") if self.key else str(e)
            raise FofaAPIError(f"获取用量失败: {err_msg}")
        return {
            "isvip": bool(data.get("valid", False)),
            "vip_level": "中转",
            "remain_api_query": data.get("totalRemaining", "N/A"),
            "expiration": data.get("expireTime", "N/A"),
            "today_remaining": data.get("todayRemaining"),
            "first_used": data.get("firstUsedAt"),
            "relay": True,
        }

    def search(
        self,
        query: str,
        size: int = 100,
        page: int = 1,
        fields: Optional[str] = None,
        full: bool = False,
        max_retries: int = 3,
        retry_callback: Optional[Callable[[int, int, Exception], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> SearchStats:
        """
        执行 FOFA 查询

        Args:
            query: FOFA 查询语句
            size: 返回数量（最大 10000）
            page: 页码（默认为1）
            fields: 返回字段，默认为 DEFAULT_FIELDS
            full: 是否搜索全部数据（不止一年）
            max_retries: 失败重试次数
            retry_callback: 重试回调
            cancel_check: 取消检查函数，返回 True 时抛 KeyboardInterrupt 中断

        Returns:
            SearchStats 对象，包含结果列表、总匹配数和独立 IP 数
        """
        if fields is None:
            fields = DEFAULT_FIELDS
        else:
            fields = _api_fields(fields)

        qbase64 = base64.b64encode(query.encode()).decode()
        # 参数一律 URL 编码：base64 字母表含 '+'，未编码时可能被服务端
        # 按表单规则解码为空格，导致查询语句被破坏
        url = (
            f"{self.base_url}/api/v1/search/all"
            f"?key={quote(self.key, safe='')}"
            f"&qbase64={quote(qbase64, safe='')}"
            f"&size={size}&page={page}&fields={quote(fields, safe='')}"
        )
        if full:
            url += "&full=true"

        data = None
        for attempt in range(1, max_retries + 1):
            try:
                resp = urllib.request.urlopen(url, timeout=45)
                data = json.loads(resp.read().decode())
            except Exception as e:
                if attempt >= max_retries:
                    err_msg = str(e).replace(self.key, "***") if self.key else str(e)
                    raise FofaAPIError(f"请求失败: {err_msg}")
                if retry_callback:
                    retry_callback(attempt, max_retries, e)
                _sleep_interruptible(_retry_sleep_seconds(e, attempt), cancel_check)
                continue

            if data.get("error"):
                errmsg = data.get("errmsg", "未知错误")
                api_error = FofaAPIError(f"API 错误: {errmsg}")
                if attempt < max_retries and _is_retryable_api_error(errmsg):
                    if retry_callback:
                        retry_callback(attempt, max_retries, api_error)
                    _sleep_interruptible(
                        _retry_sleep_seconds(api_error, attempt), cancel_check
                    )
                    continue
                raise api_error

            break

        results = []
        fields_list = _field_names(fields) or list(DEFAULT_FIELD_LIST)
        unique_ips = set()
        for item in data.get("results", []):
            if isinstance(item, str):
                item = [item]
            result = FofaResult()
            result._extra = {}
            for i, field in enumerate(fields_list):
                value = item[i] if len(item) > i else ""
                if field in KNOWN_FIELDS:
                    setattr(result, field, value)
                else:
                    result._extra[field] = value
            if "domain" in fields_list and result.host and not result.domain:
                result.domain = _infer_domain_from_host(result.host)
            results.append(result)
            if result.ip:
                unique_ips.add(result.ip)

        total = data.get("size", 0)
        return SearchStats(total=total, unique_ips=len(unique_ips), results=results)

    def search_all_efficient(
        self,
        query: str,
        max_size: int = 0,
        fields: Optional[str] = None,
        fill_percent: float = 0.8,
        api_rate_limit: float = 5.0,
        full: bool = False,
        progress_callback: Optional[callable] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> SearchStats:
        """
        多次查询所有结果：使用 before 递进策略

        策略：
        1. 用 before 从最新时间往前查，每次最多 10000 条
        2. 每批记录本批中最小的 lastupdatetime，作为下次查询的 before 值
        3. 直到某批数据不足 10000 条或达到目标数量
        4. 合并所有结果并去重

        Args:
            query: FOFA 查询语句
            max_size: 最大返回数量（0 表示不限制）
            fields: 返回字段
            fill_percent: 完成百分比（0.0-1.0），默认 0.8
            api_rate_limit: API 频率限制（秒），默认 5 秒
            full: 是否搜索全部数据
            progress_callback: 进度回调函数，用于解耦控制台输出
            cancel_check: 取消检查函数，返回 True 时抛 KeyboardInterrupt 中断

        Returns:
            SearchStats 对象
        """
        if fields is None:
            fields = DEFAULT_FIELDS
        else:
            fields = _api_fields(fields)
        fields = _append_missing_fields(fields, ["lastupdatetime", "host"])

        all_results = []
        seen_hosts = set()
        unique_ips = set()
        total_estimated = 0
        total_quota_used = 0
        current_rate_limit = max(float(api_rate_limit), 0.0)
        max_rate_limit = 60.0

        def trigger_cb(event, **kwargs):
            if progress_callback:
                progress_callback({"event": event, **kwargs})

        def adaptive_retry_callback(stage: str, batch_no: int = 0):
            def on_retry(attempt: int, max_attempts: int, error: Exception):
                nonlocal current_rate_limit
                err_text = str(error)
                if _is_retryable_api_error(err_text):
                    current_rate_limit = min(
                        max_rate_limit,
                        max(current_rate_limit * 1.8, current_rate_limit + 5, 10),
                    )
                else:
                    current_rate_limit = min(
                        max_rate_limit,
                        max(current_rate_limit * 1.5, current_rate_limit + 2),
                    )
                trigger_cb(
                    "retry",
                    stage=stage,
                    batch_num=batch_no,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    error=err_text,
                    rate_limit=current_rate_limit,
                )

            return on_retry

        count_stats = self.search(
            query,
            size=1,
            page=1,
            fields=fields,
            full=full,
            retry_callback=adaptive_retry_callback("count"),
            cancel_check=cancel_check,
        )
        total_quota_used += 1
        total_estimated = count_stats.total

        _sleep_interruptible(current_rate_limit, cancel_check)

        if total_estimated == 0:
            trigger_cb("no_match")
            return SearchStats(
                total=0,
                unique_ips=0,
                results=[],
                total_quota_used=total_quota_used,
            )

        raw_target_count = int(total_estimated * fill_percent)
        target_count = raw_target_count
        if max_size > 0 and target_count > max_size:
            target_count = max_size
        trigger_cb(
            "init",
            total_estimated=total_estimated,
            target_count=target_count,
            raw_target_count=raw_target_count,
            max_size=max_size,
            fill_percent=fill_percent,
        )

        if target_count <= 0:
            trigger_cb("skip_zero_target")
            return SearchStats(
                total=total_estimated,
                unique_ips=0,
                results=[],
                total_quota_used=total_quota_used,
            )

        trigger_cb("start")

        before_time = None
        batch_num = 0
        interrupted = False
        partial_error = ""

        try:
            while True:
                if cancel_check and cancel_check():
                    raise KeyboardInterrupt()
                remaining = target_count - len(all_results)
                if remaining <= 0:
                    break
                min_tail_size = 1000 if target_count > 10000 else 0
                request_size = min(10000, max(remaining, min_tail_size))

                if before_time:
                    range_query = f'{query} && before="{before_time}"'
                else:
                    range_query = query

                try:
                    slice_stats = self.search(
                        range_query,
                        size=request_size,
                        page=1,
                        fields=fields,
                        full=full,
                        retry_callback=adaptive_retry_callback("batch", batch_num + 1),
                        cancel_check=cancel_check,
                    )
                except FofaAPIError as e:
                    if all_results:
                        interrupted = True
                        trigger_cb(
                            "error_partial",
                            error=str(e),
                            fetched=len(all_results),
                            target_count=target_count,
                            total_estimated=total_estimated,
                        )
                        partial_error = str(e)
                        break
                    raise
                total_quota_used += len(slice_stats.results)
                if current_rate_limit > api_rate_limit:
                    current_rate_limit = max(api_rate_limit, current_rate_limit * 0.9)

                if not slice_stats.results:
                    break

                new_count = 0
                batch_min_time = None
                for r in slice_stats.results:
                    if r.host and r.host not in seen_hosts:
                        seen_hosts.add(r.host)
                        all_results.append(r)
                        new_count += 1
                        if r.ip:
                            unique_ips.add(r.ip)
                    if r.lastupdatetime:
                        if batch_min_time is None or r.lastupdatetime < batch_min_time:
                            batch_min_time = r.lastupdatetime

                batch_num += 1
                dup_rate = (
                    (len(slice_stats.results) - new_count)
                    / len(slice_stats.results)
                    * 100
                    if len(slice_stats.results) > 0
                    else 0
                )

                trigger_cb(
                    "progress",
                    batch_num=batch_num,
                    new_count=new_count,
                    dup_rate=dup_rate,
                    fetched=len(all_results),
                    total_estimated=total_estimated,
                    target_count=target_count,
                    total_quota_used=total_quota_used,
                    rate_limit=current_rate_limit,
                )

                if len(all_results) >= target_count:
                    trigger_cb(
                        "target_reached",
                        fetched=len(all_results),
                        total_estimated=total_estimated,
                        target_count=target_count,
                        fill_percent=fill_percent,
                    )
                    break

                if len(slice_stats.results) < request_size:
                    break

                if batch_min_time:
                    try:
                        dt = datetime.strptime(batch_min_time, "%Y-%m-%d %H:%M:%S")
                        dt -= timedelta(seconds=1)
                        before_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except (ValueError, TypeError):
                        before_time = None
                else:
                    break

                _sleep_interruptible(current_rate_limit, cancel_check)

                if max_size > 0 and len(all_results) >= max_size:
                    break
        except KeyboardInterrupt:
            interrupted = True
            partial_error = "Interrupted by user"
            trigger_cb("interrupted")

        if max_size > 0 and len(all_results) > max_size:
            all_results = all_results[:max_size]
            unique_ips = set(r.ip for r in all_results if r.ip)

        trigger_cb(
            "done",
            interrupted=interrupted,
            fetched=len(all_results),
            total_estimated=total_estimated,
            target_count=target_count,
            unique_ips=len(unique_ips),
            total_quota_used=total_quota_used,
            partial_error=partial_error,
        )

        return SearchStats(
            total=total_estimated,
            unique_ips=len(unique_ips),
            results=all_results,
            total_quota_used=total_quota_used,
            partial=interrupted,
            partial_error=partial_error,
        )


# ============ 导出相关 ============


def build_url(r: FofaResult) -> str:
    """根据 host、protocol、port 组装完整 URL"""
    if not r.host:
        return ""
    if r.host.startswith("http"):
        return r.host

    parsed = urlparse(f"//{r.host}")
    try:
        host_has_port = parsed.port is not None
    except ValueError:
        host_has_port = False

    protocol = (
        r.protocol.lower()
        if r.protocol
        else ("https" if r.port in ("443", "8443", "4443") else "http")
    )
    # 处理协议字段中的脏数据，例如 "http,https" 或 "socks5"
    if "," in protocol:
        protocol = protocol.split(",")[0]

    if not host_has_port and r.port:
        if (protocol == "http" and r.port == "80") or (
            protocol == "https" and r.port == "443"
        ):
            return f"{protocol}://{r.host}"
        return f"{protocol}://{r.host}:{r.port}"

    return f"{protocol}://{r.host}"


def unique_path(path: Path) -> Path:
    """如果文件存在，自动重命名"""
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    n = 1
    while True:
        new_path = parent / f"{stem}_{n}{suffix}"
        if not new_path.exists():
            return new_path
        n += 1


def dedup_results(
    results: list[FofaResult], fields: Optional[str], dedup_field: Optional[str] = None
) -> list[FofaResult]:
    """去重"""
    user_fields = set(f.strip() for f in (fields or "").split(",") if f.strip())

    if dedup_field:
        dedup_fields = set(f.strip() for f in dedup_field.split(",") if f.strip())
    else:
        dedup_fields = user_fields

    if not dedup_fields:
        return results

    seen = set()
    unique_results = []
    for r in results:
        key_tuple = []
        for f in dedup_fields:
            if f == "url":
                key_tuple.append(build_url(r) or "")
            elif f in KNOWN_FIELDS:
                key_tuple.append(getattr(r, f, "") or "")
            else:
                # 不在 FofaResult 上的字段（如 fid）只存在于 _extra。
                # 取值必须参与分组，否则按该字段去重会把所有行并成一组。
                extra = r._extra.get(f, "")
                key_tuple.append(extra if isinstance(extra, str) else str(extra or ""))
        key = tuple(key_tuple)
        if key not in seen:
            seen.add(key)
            unique_results.append(r)
    return unique_results


class Exporter:
    """导出管理器"""

    # 默认导出列 = 全部已知字段，单一来源见 ALL_FIELD_NAMES（序同 FofaResult）

    def __init__(
        self,
        results: list[FofaResult],
        fields: Optional[str] = None,
        dedup_field: Optional[str] = None,
    ):
        if not results:
            self.results = []
        else:
            self.results = dedup_results(results, fields, dedup_field)

        self.fields_str = fields
        if fields:
            self.requested_fields = [f.strip() for f in fields.split(",") if f.strip()]
        else:
            self.requested_fields = []

        self.requested_has_url = "url" in self.requested_fields

    def _prepare_dict_data(self):
        """准备转换为字典的数据，包含动态 url 拼接"""
        data = []
        for r in self.results:
            d = r.to_dict()
            if self.requested_has_url and not d.get("url"):
                d["url"] = build_url(r)
            data.append(d)
        return data

    def export_csv(self, output_path: Path) -> int:
        if self.requested_fields:
            fieldnames = self.requested_fields.copy()
        else:
            fieldnames = ALL_FIELD_NAMES.copy()

        all_keys = set()
        data = self._prepare_dict_data()
        for d in data:
            all_keys.update(d.keys())

        dynamic_extra = [
            f
            for f in all_keys
            if f not in ALL_FIELD_NAMES
            and not f.startswith("_")
            and f not in fieldnames
        ]

        with output_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=fieldnames + dynamic_extra, extrasaction="ignore"
            )
            writer.writeheader()
            for row in data:
                writer.writerow(row)

        return len(self.results)

    def export_json(self, output_path: Path) -> int:
        if not self.results:
            output_path.write_text("[]\n", encoding="utf-8")
            return 0

        data = self._prepare_dict_data()
        processed_data = []

        for d in data:
            if self.requested_fields:
                d = {k: d.get(k, "") for k in self.requested_fields}
            else:
                d = {k: v for k, v in d.items() if v != "" and v is not None}
            processed_data.append(d)

        output_path.write_text(
            json.dumps(processed_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return len(self.results)

    def export_txt(self, output_path: Path) -> int:
        if not self.results:
            output_path.write_text("", encoding="utf-8")
            return 0

        user_fields = set(self.requested_fields)

        if user_fields == {"ip"}:
            output_type = "ip"
        elif user_fields == {"domain"}:
            output_type = "domain"
        else:
            output_type = "url"

        count = 0
        with output_path.open("w", encoding="utf-8", newline="\n") as f:
            for r in self.results:
                if output_type == "ip":
                    if r.ip:
                        f.write(f"{r.ip}\n")
                        count += 1
                elif output_type == "domain":
                    if r.domain:
                        f.write(f"{r.domain}\n")
                        count += 1
                else:
                    if r.host:
                        f.write(f"{build_url(r)}\n")
                        count += 1
                    elif r.ip:
                        f.write(f"{r.ip}\n")
                        count += 1

        return count


def _merge_dedup_fields(fields: str, dedup: Optional[str]) -> str:
    """将去重字段中缺失的字段追加到查询字段列表"""
    if not dedup:
        return fields
    fields = fields or ""
    dedup_fields = set(f.strip() for f in dedup.split(",") if f.strip())
    user_fields = set(f.strip() for f in fields.split(",") if f.strip())
    extra_fields = dedup_fields - user_fields
    if extra_fields:
        return (fields + "," if fields else "") + ",".join(extra_fields)
    return fields


def parse_limit_value(limit: str) -> tuple[bool, int]:
    """解析 limit 参数，返回 (is_max, limit_value)。"""
    limit_str = str(limit).strip()
    is_max = limit_str.lower() == "max"
    if is_max:
        return True, 0

    try:
        limit_value = int(limit_str)
    except ValueError as e:
        raise ValueError("-l/--limit 必须是正整数或 'max'") from e

    if limit_value <= 0:
        raise ValueError("-l/--limit 必须大于 0，或使用 'max'")

    return False, limit_value


# ============ 主函数 ============


def create_console_progress_callback(bar_width=25):
    """创建用于控制台输出的进度回调函数"""
    progress_active = False

    def finish_progress_line():
        nonlocal progress_active
        if progress_active:
            print()
            progress_active = False

    def progress_callback(state: dict):
        nonlocal progress_active
        event = state.get("event")

        if event == "no_match":
            finish_progress_line()
            print("  [*] 无匹配数据")

        elif event == "init":
            finish_progress_line()
            total_estimated = state.get("total_estimated", 0)
            target_count = state.get("target_count", 0)
            raw_target_count = state.get("raw_target_count", target_count)
            max_size = state.get("max_size", 0)
            fill_percent = state.get("fill_percent", 0)
            target_note = (
                "数量限制"
                if max_size > 0 and target_count < raw_target_count
                else f"{int(fill_percent * 100)}%"
            )
            print(
                f"\n[*] 匹配总量: {total_estimated:,} | 目标: {target_count:,} ({target_note})"
            )
            print()

        elif event == "skip_zero_target":
            finish_progress_line()
            print("[*] 目标为 0，跳过批量抓取")

        elif event == "start":
            pass  # 可以在这里打印"开始..."，目前推迟到第一个progress事件

        elif event == "progress":
            fetched = state.get("fetched", 0)
            total_estimated = state.get("total_estimated", 1)
            target_count = state.get("target_count", total_estimated) or total_estimated
            total_quota_used = state.get("total_quota_used", 0)
            batch_num = state.get("batch_num", 0)
            new_count = state.get("new_count", 0)
            dup_rate = state.get("dup_rate", 0)

            percent = fetched / target_count if target_count > 0 else 0
            display_percent = min(percent, 1.0)
            filled = int(bar_width * display_percent)
            tail = "~" if filled < bar_width else ""
            spaces = " " * max(bar_width - filled - len(tail), 0)
            bar = f"{GREEN}{'=' * filled}{RESET}{tail}{spaces}"
            pct_color = YELLOW if percent < 0.5 else GREEN
            msg = f"批次 {batch_num} (新增:{new_count} 重复:{dup_rate:.0f}%)"
            display_fetched = min(fetched, target_count)
            line = (
                f"[{bar}] {pct_color}{display_percent * 100:5.1f}%{RESET} | "
                f"{GREEN}{display_fetched:>6}{RESET}/{target_count:<6} | "
                f"{RED}配额:{total_quota_used:>6}{RESET} | {msg}"
            )
            if INTERACTIVE_OUTPUT:
                print(f"\r{line}", end="", flush=True)
                progress_active = True
            elif batch_num % 10 == 0 or fetched >= target_count:
                print(line)

        elif event == "target_reached":
            finish_progress_line()
            fetched = state.get("fetched", 0)
            total_estimated = state.get("total_estimated", 0)
            target_count = state.get("target_count", total_estimated)
            fill_percent = state.get("fill_percent", 0)
            display_fetched = min(fetched, target_count)
            extra_note = f"，实际抓取 {fetched:,}" if fetched > target_count else ""
            print(
                f"[*] {GREEN}已达目标{RESET} ({display_fetched:,}/{target_count:,}{extra_note}，总匹配 {total_estimated:,})"
            )

        elif event == "retry":
            finish_progress_line()
            stage = state.get("stage", "request")
            batch_num = state.get("batch_num", 0)
            attempt = state.get("attempt", 0)
            max_attempts = state.get("max_attempts", 0)
            rate_limit = state.get("rate_limit", 0)
            label = "统计总量" if stage == "count" else f"批次 {batch_num}"
            print(
                f"[!] {label} 请求超时/失败，重试 {attempt}/{max_attempts - 1}，后续间隔调整为 {rate_limit:.1f}s..."
            )

        elif event == "error_partial":
            finish_progress_line()
            error = state.get("error", "未知错误")
            fetched = state.get("fetched", 0)
            print(
                f"[!] 请求重试后仍失败，保留已获取 {fetched:,} 条结果继续导出: {error}"
            )

        elif event == "interrupted":
            finish_progress_line()
            print("[*] 已中断，保存已获取的数据...")

        elif event == "done":
            finish_progress_line()
            interrupted = state.get("interrupted", False)
            fetched = state.get("fetched", 0)
            total_estimated = state.get("total_estimated", 0)
            target_count = state.get("target_count", total_estimated) or total_estimated
            unique_ips = state.get("unique_ips", 0)
            total_quota_used = state.get("total_quota_used", 0)

            if not interrupted:
                percent = (
                    int(fetched / total_estimated * 100) if total_estimated > 0 else 0
                )
                print(
                    f"[*] {GREEN}查询完成{RESET} (API消耗: {RED}{total_quota_used}{RESET} 配额)"
                )
                print(
                    f"[*] 获取数据: {GREEN}{fetched:,}{RESET} 条 (覆盖率 ~{percent}%)"
                )
                if target_count != total_estimated:
                    print(f"[*] 有效目标: {CYAN}{target_count:,}{RESET} 条")
                print(f"[*] 独立 IP: {CYAN}{unique_ips:,}{RESET}")
            else:
                print(f"[*] 获取数据: {GREEN}{fetched:,}{RESET} 条")
                print(f"[*] 独立 IP: {CYAN}{unique_ips:,}{RESET}")

    return progress_callback


def build_parser():
    parser = argparse.ArgumentParser(
        description="FOFA 查询工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        usage="%(prog)s 查询语句 [选项]",
        epilog="""
示例:
  %(prog)s "domain=baidu.com" -o results.csv      # 指定 CSV 输出文件
  %(prog)s "domain=baidu.com" -l max -o all.csv   # 导出全部匹配数据
  %(prog)s "ip=1.1.1.1/24" -json -o ips.json      # 输出 JSON 格式
  %(prog)s "domain=baidu.com" -f "ip,port"        # 指定查询字段
  %(prog)s --icon https://example.com              # 查询使用相同图标的网站（同框架/同产品）
  %(prog)s --icon https://example.com "port=443"   # Icon 同款 + 附加过滤条件
  %(prog)s --icon ./favicon.ico -l max -csv        # 本地 icon 文件直接导出
  %(prog)s -c                                      # 快速检测账户状态
        """,
    )
    parser.add_argument("query", nargs="?", help="FOFA 查询语句，如: domain=baidu.com（--icon 模式下作为附加过滤条件）")
    parser.add_argument("-o", "--output", help="输出文件名（含后缀），如 results.csv")
    parser.add_argument(
        "-l",
        "--limit",
        help="最大返回数量，支持 >10000 或 'max'（导出全部）",
        default="100",
    )
    parser.add_argument(
        "-b",
        "--batch",
        dest="batch_file",
        metavar="FILE",
        help="批量查询文件，每行一个查询语句（配合占位符使用）",
    )
    parser.add_argument(
        "--fill",
        type=float,
        default=0.8,
        help="多次查询完成百分比（0.0-1.0），仅 -l>10000 或 max 时生效",
    )
    parser.add_argument(
        "-p",
        "--placeholder",
        default="{}",
        help='占位符格式，默认 {}，配合 -b 使用，如: python fofatoto.py "host={}" -b targets.txt',
    )
    parser.add_argument("-csv", action="store_true", help="导出 CSV 格式")
    parser.add_argument("-txt", action="store_true", help="导出 TXT 格式（URL 列表）")
    parser.add_argument("-json", action="store_true", help="导出 JSON 格式")
    parser.add_argument(
        "-f",
        "--fields",
        help=f"查询字段，控制 FOFA API 返回哪些字段及导出字段，默认 {DEFAULT_FIELDS}",
        default=DEFAULT_FIELDS,
    )
    parser.add_argument(
        "--dedup",
        help="根据指定字段去重，多个字段用逗号分隔，如 --dedup ip 或 --dedup ip,host",
    )
    parser.add_argument(
        "-i",
        "--icon",
        metavar="TARGET",
        help="Icon 同款查询：网站地址 / 本地 icon 文件 / 已知 icon_hash 整数，自动提取 icon_hash 并查询使用相同图标的网站（同框架/同产品）",
    )
    parser.add_argument("--full", action="store_true", help="搜索全部数据（不止一年）")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细信息")
    parser.add_argument(
        "-w",
        "--web",
        action="store_true",
        help="启动 Web UI 模式（默认无参数时自动进入）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help=f"Web UI 端口号（默认 {DEFAULT_WEB_PORT}，被占用则自动递增）",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Web UI 监听地址（默认 127.0.0.1 仅本机可访问；0.0.0.0 监听所有网卡供局域网访问；指定后不再自动打开浏览器）",
    )
    parser.add_argument(
        "-c",
        "--check",
        action="store_true",
        help="快速检测：仅显示账户信息后退出",
    )
    return parser


def print_account_status(client: FofaClient):
    """检查并打印账号状态"""
    try:
        user_info = client.get_usage()
        if user_info:
            if user_info.get("relay"):
                valid = user_info.get("isvip", False)
                status = f"{GREEN}有效{RESET}" if valid else f"{RED}无效{RESET}"
                print(highlight("[*] 类型", "中转站"))
                print(highlight("[*] Key状态", status))
                print(highlight("[*] 剩余查询", user_info.get("remain_api_query", "N/A")))
                if user_info.get("today_remaining") is not None:
                    print(highlight("[*] 今日剩余", user_info["today_remaining"]))
                print(highlight("[*] 过期时间", user_info.get("expiration", "N/A")))
                if user_info.get("first_used"):
                    print(highlight("[*] 首次使用", user_info["first_used"]))
            else:
                is_vip = user_info.get("isvip", False)
                vip_status = f"{GREEN}正常{RESET}" if is_vip else f"{RED}无效{RESET}"
                server_status = (
                    f"{GREEN}正常{RESET}"
                    if user_info.get("fofa_server")
                    else f"{RED}异常{RESET}"
                )
                print(highlight("[*] 服务器", server_status))
                print(highlight("[*] Key状态", vip_status))
                print(highlight("[*] 剩余查询", user_info.get("remain_api_query", "N/A")))
                print(highlight("[*] 过期时间", user_info.get("expiration", "N/A")))
                print(highlight("[*] VIP等级", user_info.get("vip_level", "N/A")))
            print()
    except FofaAPIError as e:
        print(f"[!] 用量检查失败: {e}", file=sys.stderr)


def determine_output_filename(args, prefix="fofa_results"):
    """根据参数确定默认输出文件名"""
    if args.output:
        return args.output

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.json:
        return f"{prefix}_{timestamp}.json"
    elif args.txt:
        return f"{prefix}_{timestamp}.txt"
    else:
        return f"{prefix}_{timestamp}.csv"


def handle_batch_mode(client: FofaClient, args):
    """处理批量查询模式"""
    try:
        targets = load_batch_targets(Path(args.batch_file))
        placeholder = args.placeholder

        if args.query and placeholder in args.query:
            queries = expand_placeholder_query(
                args.query, [t[0] for t in targets], placeholder
            )
            print(f"[*] 批量模式: 已加载 {len(queries)} 个查询 (占位符: {placeholder})")
        else:
            queries = [(t[0], t[1]) for t in targets]
            print(f"[*] 批量模式: 已加载 {len(queries)} 个查询")

        if not any([args.csv, args.txt, args.json]):
            args.csv = True

        args.output = determine_output_filename(args, prefix="fofa_batch")

        all_results = run_batch_search(client, queries, args)
        print(f"\n[*] 批量查询完成: 共获取 {len(all_results)} 条结果")

        if not all_results:
            print("[-] 没有找到任何结果")
            sys.exit(0)

        export_results(all_results, args)
        sys.exit(0)
    except FileNotFoundError as e:
        print(f"[!] {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"[!] {e}", file=sys.stderr)
        sys.exit(1)
    except FofaAPIError as e:
        print(f"[-] API 错误: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[-] 错误: {e}", file=sys.stderr)
        sys.exit(1)


def handle_icon_mode(client: FofaClient, args):
    """Icon 同款查询：提取目标 favicon 的 icon_hash 后走单查询链路"""
    try:
        info = resolve_icon(args.icon)
    except IconExtractError as e:
        print(f"[-] icon 提取失败: {e}", file=sys.stderr)
        print("[*] 可改用本地 icon 文件或已知 icon_hash 整数重试", file=sys.stderr)
        sys.exit(1)

    source = info["icon_url"] or args.icon
    size_note = f"{info['icon_size']} bytes" if info["icon_size"] else "raw hash"
    print(f"[*] icon_hash={info['icon_hash']}（来源 {source}，{size_note}）")
    args.query = build_icon_query(info["icon_hash"], args.query)
    print(f"[*] 查询语句: {args.query}")
    handle_single_mode(client, args)


def handle_single_mode(client: FofaClient, args):
    """处理单次查询模式"""
    # 没有查询语句时报错 (这部分交给调用者处理更好，但在内部处理也可以)
    if not any([args.csv, args.txt, args.json]):
        args.csv = True

    args.output = determine_output_filename(args, prefix="fofa_results")

    try:
        is_max, limit_value = parse_limit_value(args.limit)

        if args.verbose:
            print(f"[*] 查询: {args.query}")
            print(f"[*] 数量限制: {'无限制(max)' if is_max else limit_value}")

        query_fields = _merge_dedup_fields(args.fields, args.dedup)

        if limit_value > 10000 or is_max:
            max_size = 0 if is_max else limit_value
            if args.full:
                print(f"[*] 搜索全部数据（不止一年）")
            if args.verbose:
                print(f"[*] 目标: {int(args.fill * 100)}%")
            stats = client.search_all_efficient(
                args.query,
                max_size=max_size,
                fields=query_fields,
                fill_percent=args.fill,
                full=args.full,
                progress_callback=create_console_progress_callback(),
            )
        else:
            stats = client.search(
                args.query, size=limit_value, fields=query_fields, full=args.full
            )

        results = stats.results

        print(f"[*] 找到 {YELLOW}{stats.total:,}{RESET} 条匹配结果")

        if not results:
            print("[-] 没有找到结果")
            sys.exit(0)

        export_results(results, args)

    except FofaAPIError as e:
        print(f"[-] API 错误: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[-] 错误: {e}", file=sys.stderr)
        sys.exit(1)


# ============ Web UI 相关 ============

_export_tasks: dict = {}
_export_lock = threading.Lock()
_EXPORT_TASK_TTL = 1800  # 终态任务完成 30 分钟后自动清理
_MAX_REQUEST_BODY = 8 * 1024 * 1024  # Web API 请求体上限，挡住异常 Content-Length
_export_cleanup_thread: Optional[threading.Thread] = None
_export_cleanup_stop = threading.Event()


def _cleanup_export_tasks():
    """清理过期的导出任务及其临时文件，防止内存和磁盘泄漏。

    TTL 从任务完成时刻（finished_at）起算而非创建时刻，保证运行超过
    30 分钟的深度导出完成后仍有完整的 30 分钟下载窗口。
    """
    now = time.time()
    expired = []
    with _export_lock:
        for tid, task in list(_export_tasks.items()):
            if task.status in ("done", "error") and (
                now - (task.finished_at or task.created_at)
            ) > _EXPORT_TASK_TTL:
                expired.append((tid, dict(task.output_files)))
                del _export_tasks[tid]
    for tid, files in expired:
        for filepath in files.values():
            try:
                Path(filepath).unlink(missing_ok=True)
            except Exception:
                pass


def _cleanup_loop() -> None:
    """后台循环：每 60 秒清理一次过期任务与临时文件。

    仅 Web UI 模式下启动（`start_export_cleanup_timer`），
    随服务器关闭时停止（`stop_export_cleanup_timer`）。
    """
    while not _export_cleanup_stop.wait(60):
        _cleanup_export_tasks()


def start_export_cleanup_timer() -> None:
    """启动后台 TTL 清理线程（幂等）。"""
    global _export_cleanup_thread
    if _export_cleanup_thread and _export_cleanup_thread.is_alive():
        return
    _export_cleanup_stop.clear()
    t = threading.Thread(target=_cleanup_loop, daemon=True, name="export-cleanup")
    t.start()
    _export_cleanup_thread = t


def stop_export_cleanup_timer() -> None:
    """停止后台 TTL 清理线程。"""
    _export_cleanup_stop.set()


def _has_running_export_task() -> bool:
    """是否已有未取消的导出/批量任务在运行。

    前端已限制单页一个任务，这里在服务端兜底，防止多标签页或脚本
    并发多个任务、各自独立限流地消耗 FOFA 配额。已请求取消的任务
    不再计入（其线程即将退出）。

    注意：调用方必须已持有 _export_lock——与任务注册放在同一临界区，
    避免检查与注册之间被并发请求插入（TOCTOU）。
    """
    return any(
        t.status == "running" and not t.cancelled for t in _export_tasks.values()
    )


def _finish_export_task(task_id: str, status: str, **fields) -> None:
    """在锁内将任务置为终态（done/error）并记录完成时间。

    集中处理终态迁移，保证 finished_at 与 status 同步写入，
    TTL 清理据此起算。
    """
    with _export_lock:
        task = _export_tasks.get(task_id)
        if task:
            task.status = status
            task.finished_at = time.time()
            for name, value in fields.items():
                setattr(task, name, value)


def _start_export_thread(task_id: str, target: Callable, args: tuple) -> None:
    """启动导出/批量任务线程；启动失败时将已注册任务就地置为终态。

    任务注册先于线程启动：start() 失败（如线程资源耗尽）时若任务
    停留在 running，会永久卡住服务端并发守卫。失败时置为 error 后
    原样抛出，由调用方返回错误响应。
    """
    thread = threading.Thread(target=target, args=args, daemon=True)
    try:
        thread.start()
    except Exception:
        _finish_export_task(task_id, "error", error="任务线程启动失败")
        raise


@dataclass
class ExportTask:
    task_id: str
    kind: str = "export"
    status: str = "running"
    progress: float = 0.0
    message: str = ""
    fetched: int = 0
    total_estimated: int = 0
    target_count: int = 0
    unique_ips: int = 0
    total_quota_used: int = 0
    current_target: int = 0
    total_targets: int = 0
    current_fetched: int = 0
    current_total_estimated: int = 0
    current_target_count: int = 0
    failed_count: int = 0
    output_files: dict = field(default_factory=dict)
    error: str = ""
    partial: bool = False
    partial_error: str = ""
    created_at: float = field(default_factory=time.time)
    finished_at: float = 0.0
    cancelled: bool = False
    discard: bool = False


def _redact_sensitive(text: str, *secrets: str) -> str:
    safe_text = str(text)
    for secret in secrets:
        if secret:
            safe_text = safe_text.replace(secret, "***")
    safe_text = re.sub(r"(key=)[^&\s]+", r"\1***", safe_text)
    return safe_text


def _make_task_cancel_check(task_id: str):
    """构造任务的取消检查函数：供 _sleep_interruptible 在限流/重试休眠中
    及时响应「取消导出」，语义与进度回调中的取消一致。"""

    def cancel_check() -> bool:
        with _export_lock:
            task = _export_tasks.get(task_id)
            return bool(task and task.cancelled)

    return cancel_check


def _create_web_progress_callback(task_id: str, max_size: int = 0):
    def progress_callback(state: dict):
        cancelled = False
        with _export_lock:
            task = _export_tasks.get(task_id)
            if not task:
                return
            cancelled = task.cancelled
            discard = task.discard
            event = state.get("event")
            if event == "no_match":
                task.message = "未找到匹配数据"
                task.progress = 0.99
            elif event == "init":
                task.total_estimated = state.get("total_estimated", 0)
                task.target_count = state.get("target_count", 0)
                if max_size > 0 and task.target_count > 0:
                    task.target_count = min(task.target_count, max_size)
                task.message = "正在按时间游标分批拉取数据"
            elif event == "progress":
                task.fetched = state.get("fetched", 0)
                task.total_estimated = state.get("total_estimated", 1)
                task.target_count = state.get("target_count", task.target_count)
                task.total_quota_used = state.get("total_quota_used", 0)
                if not cancelled:
                    target_count = task.target_count or task.total_estimated
                    task.progress = min(task.fetched / max(target_count, 1), 0.99)
            elif event == "retry":
                stage = state.get("stage", "request")
                batch_num = state.get("batch_num", 0)
                attempt = state.get("attempt", 0)
                max_attempts = state.get("max_attempts", 0)
                rate_limit = state.get("rate_limit", 0)
                label = "统计总量" if stage == "count" else f"批次 {batch_num}"
                task.message = (
                    f"{label} 请求失败，正在重试 {attempt}/{max_attempts - 1}；"
                    f"后续间隔 {rate_limit:.1f}s"
                )
            elif event == "error_partial":
                task.message = f"请求失败，保留已获取 {state.get('fetched', 0)} 条结果"
                task.fetched = state.get("fetched", task.fetched)
                task.total_estimated = state.get("total_estimated", task.total_estimated)
                task.target_count = state.get("target_count", task.target_count)
            elif event == "target_reached":
                task.progress = 0.99
                task.fetched = state.get("fetched", 0)
                task.message = "已达到目标数量，正在整理文件"
            elif event == "interrupted":
                task.message = "Interrupted"
            elif event == "done":
                task.progress = 0.99
                if state.get("interrupted"):
                    task.partial = True
                    task.partial_error = state.get("partial_error", "")
                    task.message = "部分结果已获取，正在生成导出文件"
                else:
                    task.message = "正在生成导出文件"
                task.fetched = state.get("fetched", 0)
                task.unique_ips = state.get("unique_ips", 0)
                task.total_quota_used = state.get("total_quota_used", 0)
        if cancelled and (discard or event not in ("interrupted", "done")):
            raise KeyboardInterrupt()

    return progress_callback


def _create_web_batch_progress_callback(
    task_id: str, batch_idx: int, total_queries: int, base_count: int
):
    def progress_callback(state: dict):
        with _export_lock:
            task = _export_tasks.get(task_id)
            if not task:
                return
            event = state.get("event")
            if task.cancelled and (task.discard or event not in ("interrupted", "done")):
                raise KeyboardInterrupt()

            task.current_target = batch_idx + 1
            task.total_targets = total_queries
            if event == "init":
                task.current_total_estimated = state.get("total_estimated", 0)
                task.current_target_count = state.get("target_count", 0)
            elif event == "progress":
                task.current_fetched = state.get("fetched", 0)
                task.current_total_estimated = state.get("total_estimated", 0)
                task.current_target_count = state.get(
                    "target_count", task.current_target_count
                )
                task.total_quota_used = state.get("total_quota_used", 0)
            elif event == "retry":
                attempt = state.get("attempt", 0)
                max_attempts = state.get("max_attempts", 0)
                rate_limit = state.get("rate_limit", 0)
                task.message = (
                    f"Target {batch_idx + 1}/{total_queries}: "
                    f"retry {attempt}/{max_attempts - 1}, wait {rate_limit:.1f}s"
                )
            elif event == "error_partial":
                task.current_fetched = state.get("fetched", task.current_fetched)
                task.current_total_estimated = state.get(
                    "total_estimated", task.current_total_estimated
                )
                task.current_target_count = state.get(
                    "target_count", task.current_target_count
                )
            elif event == "done":
                task.current_fetched = state.get("fetched", task.current_fetched)

            current_target = task.current_target_count or task.current_total_estimated
            current_ratio = min(task.current_fetched / max(current_target, 1), 1)
            task.progress = min((batch_idx + current_ratio) / max(total_queries, 1), 0.99)
            task.fetched = base_count + task.current_fetched
            task.message = f"Target {batch_idx + 1}/{total_queries}"

    return progress_callback


def _request_body_length(header_value: Optional[str]) -> int:
    """解析 Content-Length。缺失或 0 表示无正文；负数与超限直接拒绝，避免整包读入。"""
    if header_value is None or str(header_value).strip() == "":
        return 0
    try:
        length = int(str(header_value).strip())
    except (TypeError, ValueError) as e:
        raise FofaAPIError("Invalid Content-Length") from e
    if length < 0:
        raise FofaAPIError("Invalid Content-Length")
    if length > _MAX_REQUEST_BODY:
        raise FofaAPIError("请求体过大")
    return length


def _web_export_dir() -> Path:
    """Web 导出临时目录。收成仅当前用户可进入，避免共享机器上其他用户读到结果。"""
    output_dir = Path(tempfile.gettempdir()) / "fofa_web_exports"
    output_dir.mkdir(exist_ok=True)
    try:
        os.chmod(output_dir, 0o700)
    except OSError:
        pass
    return output_dir


def _restrict_export_file(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _write_web_exports(prefix: str, results: list, fields: str) -> dict:
    """把同一批结果写成 CSV/JSON/TXT，返回格式到路径的映射。"""
    output_dir = _web_export_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    exporter = Exporter(results, fields=fields)
    output_files = {}
    for fmt in ("csv", "json", "txt"):
        path = unique_path(output_dir / f"{prefix}_{timestamp}.{fmt}")
        getattr(exporter, f"export_{fmt}")(path)
        _restrict_export_file(path)
        output_files[fmt] = str(path)
    return output_files


class FofaWebHandler(http.server.BaseHTTPRequestHandler):
    """FOFA Web UI 请求处理器"""

    client: Optional[FofaClient] = None
    config_manager: Optional[ConfigManager] = None

    def log_message(self, format, *args):
        src = self.client_address[0] if self.client_address else "?"
        sys.stderr.write(f"[web] {src} {format % args}\n")

    def _send_json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _config_status(self) -> dict:
        if self.config_manager:
            return self.config_manager.public_status()
        return {"configured": bool(self.client), "config_path": "", "config_template": ""}

    def _safe_error(self, error) -> str:
        key = self.config_manager.key if self.config_manager else ""
        return _redact_sensitive(str(error), key)

    def _send_error(self, error, status: int = 200, data: Optional[dict] = None):
        payload = {"success": False, "error": self._safe_error(error)}
        if data:
            payload["data"] = data
        self._send_json(payload, status)

    def _current_client(self) -> Optional[FofaClient]:
        """获取当前有效的 client，支持配置热更新。

        有 config_manager 时每次请求重新读取配置并按需重建 client；
        无 config_manager（CLI 直接传 client）时回退到 self.client。
        """
        if self.config_manager:
            return self.config_manager.get_client()
        return self.client

    def _require_client(self) -> bool:
        client = self._current_client()
        if client:
            return True
        data = self._config_status()
        data["configured"] = False
        self._send_error("未配置有效的 FOFA API Key", data=data)
        return False

    def _send_html(self, html: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _send_file(self, path: Path, filename: str):
        if not path.exists():
            self._send_json({"success": False, "error": "File not found"}, 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(path.stat().st_size))
        self.end_headers()
        self.wfile.write(path.read_bytes())

    def _read_body(self) -> dict:
        length = _request_body_length(self.headers.get("Content-Length"))
        if length == 0:
            return {}
        body = self.rfile.read(length)
        try:
            return json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise FofaAPIError(f"Invalid request body: {e}")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/":
            self._send_html(render_web_html())
        elif path == "/api/info":
            self._handle_info()
        elif path == "/api/progress":
            self._handle_progress(parsed)
        elif path == "/api/export/download":
            self._handle_export_download(parsed)
        else:
            self._send_json({"success": False, "error": "Not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/api/search":
            self._handle_search()
        elif path == "/api/icon":
            self._handle_icon()
        elif path == "/api/export":
            self._handle_export()
        elif path == "/api/batch":
            self._handle_batch()
        elif path == "/api/progress/cancel":
            self._handle_cancel()
        else:
            self._send_json({"success": False, "error": "Not found"}, 404)

    def _handle_info(self):
        client = self._current_client()
        if not client:
            data = self._config_status()
            data["server_ok"] = False
            self._send_json({"success": True, "data": data})
            return

        try:
            info = client.get_usage()
            info["server_ok"] = True
            info.update(self._config_status())
            self._send_json({"success": True, "data": info})
        except FofaAPIError as e:
            data = self._config_status()
            data["server_ok"] = False
            data["error"] = self._safe_error(e)
            self._send_json({"success": True, "data": data})

    def _handle_search(self):
        try:
            if not self._require_client():
                return
            body = self._read_body()
            query = body.get("query", "")
            if not query:
                self._send_error("Query is required")
                return

            try:
                size = int(body.get("size", 100))
            except (TypeError, ValueError):
                size = 100
            size = max(1, min(size, 10000))
            fields = body.get("fields") or DEFAULT_FIELDS
            full = bool(body.get("full", False))

            stats = self._current_client().search(query, size=size, fields=fields, full=full)

            columns = [f.strip() for f in fields.split(",") if f.strip()]
            has_url = "url" in columns
            results = []
            for r in stats.results:
                d = r.to_dict()
                if has_url:
                    d["url"] = build_url(r)
                results.append(d)

            self._send_json(
                {
                    "success": True,
                    "data": {
                        "total": stats.total,
                        "unique_ips": stats.unique_ips,
                        "columns": columns,
                        "results": results,
                    },
                }
            )
        except FofaAPIError as e:
            self._send_error(e)
        except Exception as e:
            self._send_error(e)

    def _handle_icon(self):
        try:
            body = self._read_body()
            target = str(body.get("target", "")).strip()
            if not target:
                self._send_error("Target is required")
                return
            info = resolve_icon_cached(target)
            self._send_json(
                {
                    "success": True,
                    "data": {
                        "icon_hash": info["icon_hash"],
                        "icon_md5": info["icon_md5"],
                        "icon_url": info["icon_url"],
                        "icon_size": info["icon_size"],
                        "icon_data_uri": info["icon_data_uri"],
                        "source": info["source"],
                    },
                }
            )
        except IconExtractError as e:
            self._send_error(e)
        except Exception as e:
            self._send_error(e)

    def _handle_export(self):
        try:
            if not self._require_client():
                return
            body = self._read_body()
            query = body.get("query", "")
            if not query:
                self._send_error("Query is required")
                return

            fields = body.get("fields") or DEFAULT_FIELDS
            try:
                fill_percent = float(body.get("fill_percent", 0.8))
            except (TypeError, ValueError):
                fill_percent = 0.8
            if not (0 < fill_percent <= 1):
                fill_percent = 0.8
            try:
                max_size = int(body.get("max_size", 0))
            except (TypeError, ValueError):
                max_size = 0
            if max_size < 0:
                max_size = 0
            full = bool(body.get("full", False))

            task_id = uuid.uuid4().hex[:12]
            task = ExportTask(task_id=task_id, kind="export")

            _cleanup_export_tasks()
            # 检查与注册在同一临界区，防止两个并发请求同时通过检查
            with _export_lock:
                blocked = _has_running_export_task()
                if not blocked:
                    _export_tasks[task_id] = task
            if blocked:
                self._send_error("已有导出任务正在运行，请先取消或等待完成")
                return

            _start_export_thread(
                task_id,
                self._run_export_task,
                (task_id, query, fields, fill_percent, max_size, full),
            )

            self._send_json({"success": True, "task_id": task_id})
        except Exception as e:
            self._send_error(e)

    def _run_export_task(self, task_id, query, fields, fill_percent, max_size, full):
        try:
            # client 获取也在 try 内：配置热重载期间若 config 异常导致
            # get_client() 抛错，任务会被标记为 error，而不是让线程带着
            # running 状态死亡（后者会永久卡住服务端并发守卫）
            client = self._current_client()
            if not client:
                _finish_export_task(
                    task_id, "error", error="未配置有效的 FOFA API Key"
                )
                return
            stats = client.search_all_efficient(
                query,
                max_size=max_size,
                fields=fields,
                fill_percent=fill_percent,
                full=full,
                progress_callback=_create_web_progress_callback(task_id, max_size),
                cancel_check=_make_task_cancel_check(task_id),
            )

            cancelled = False
            discard = False
            with _export_lock:
                task = _export_tasks.get(task_id)
                if task:
                    cancelled = task.cancelled
                    discard = task.discard

            if discard:
                _finish_export_task(task_id, "error", error="Cancelled by user")
                return

            if not stats.results and cancelled:
                _finish_export_task(task_id, "error", error="Cancelled by user")
                return

            output_files = _write_web_exports("fofa_export", stats.results, fields)

            _finish_export_task(
                task_id,
                "done",
                progress=1.0,
                partial=cancelled or stats.partial,
                partial_error=(
                    "Cancelled by user" if cancelled else stats.partial_error
                ),
                message=(
                    "已取消，已保留部分结果"
                    if cancelled
                    else (
                        "部分导出完成，已保留可用结果"
                        if stats.partial
                        else "导出文件已生成"
                    )
                ),
                fetched=len(stats.results),
                total_estimated=stats.total,
                total_quota_used=stats.total_quota_used,
                unique_ips=stats.unique_ips,
                output_files=output_files,
            )
        except KeyboardInterrupt:
            _finish_export_task(task_id, "error", error="Cancelled by user")
        except Exception as e:
            _finish_export_task(task_id, "error", error=self._safe_error(e))

    def _handle_progress(self, parsed):
        params = parse_qs(parsed.query)
        task_id = params.get("task_id", [None])[0]

        if not task_id:
            self._send_error("task_id required")
            return

        with _export_lock:
            task = _export_tasks.get(task_id)

        if not task:
            self._send_error("Task not found")
            return

        self._send_json(
            {
                "success": True,
                "data": {
                    "status": task.status,
                    "kind": task.kind,
                    "progress": task.progress,
                    "message": task.message,
                    "fetched": task.fetched,
                    "total_estimated": task.total_estimated,
                    "target_count": task.target_count,
                    "unique_ips": task.unique_ips,
                    "total_quota_used": task.total_quota_used,
                    "current_target": task.current_target,
                    "total_targets": task.total_targets,
                    "current_fetched": task.current_fetched,
                    "current_total_estimated": task.current_total_estimated,
                    "current_target_count": task.current_target_count,
                    "failed_count": task.failed_count,
                    "partial": task.partial,
                    "partial_error": task.partial_error,
                    "elapsed_seconds": max(0, int(time.time() - task.created_at)),
                    "error": task.error,
                },
            }
        )

    def _handle_export_download(self, parsed):
        params = parse_qs(parsed.query)
        task_id = params.get("task_id", [None])[0]
        fmt = params.get("format", ["csv"])[0]

        with _export_lock:
            task = _export_tasks.get(task_id)

        if not task:
            self._send_error(
                "导出任务不存在或已过期（任务完成后约 30 分钟自动清理），请重新导出", 404
            )
            return
        if task.status != "done":
            self._send_error("Export not ready", 404)
            return

        filepath = task.output_files.get(fmt)
        if not filepath:
            self._send_error(f"No {fmt} file", 404)
            return

        path = Path(filepath)
        self._send_file(path, path.name)

    def _handle_batch(self):
        try:
            if not self._require_client():
                return
            body = self._read_body()
            base_query = body.get("base_query", "")
            targets = body.get("targets", [])
            placeholder = body.get("placeholder", "{}")
            fields = body.get("fields") or DEFAULT_FIELDS
            try:
                fill_percent = float(body.get("fill_percent", 0.8))
            except (TypeError, ValueError):
                fill_percent = 0.8
            if not (0 < fill_percent <= 1):
                fill_percent = 0.8
            try:
                max_size = int(body.get("max_size", 0))
            except (TypeError, ValueError):
                max_size = 0
            if max_size < 0:
                max_size = 0

            if not base_query or not targets:
                self._send_error("Base query and targets required")
                return

            queries = expand_placeholder_query(base_query, targets, placeholder)

            task_id = uuid.uuid4().hex[:12]
            task = ExportTask(
                task_id=task_id,
                kind="batch",
                total_targets=len(queries),
                target_count=len(queries),
            )

            _cleanup_export_tasks()
            # 检查与注册在同一临界区，防止两个并发请求同时通过检查
            with _export_lock:
                blocked = _has_running_export_task()
                if not blocked:
                    _export_tasks[task_id] = task
            if blocked:
                self._send_error("已有导出任务正在运行，请先取消或等待完成")
                return

            _start_export_thread(
                task_id,
                self._run_batch_task,
                (task_id, queries, fields, fill_percent, max_size),
            )

            self._send_json({"success": True, "task_id": task_id})
        except Exception as e:
            self._send_error(e)

    def _run_batch_task(self, task_id, queries, fields, fill_percent, max_size=0):
        try:
            # 同 _run_export_task：client 获取在 try 内，异常时标记任务
            # error，避免留下卡住并发守卫的 running 幽灵任务
            client = self._current_client()
            if not client:
                _finish_export_task(
                    task_id, "error", error="未配置有效的 FOFA API Key"
                )
                return
            all_results = []
            total_queries = len(queries)
            failed_count = 0
            cancel_check = _make_task_cancel_check(task_id)

            for batch_idx, (query, _) in enumerate(queries):
                base_count = len(all_results)
                with _export_lock:
                    task = _export_tasks.get(task_id)
                    if task and task.cancelled:
                        raise KeyboardInterrupt()
                    if task:
                        task.current_target = batch_idx + 1
                        task.total_targets = total_queries
                        task.current_fetched = 0
                        task.current_total_estimated = 0
                        task.current_target_count = max_size if 0 < max_size <= 10000 else 0
                        task.message = f"Target {batch_idx + 1}/{total_queries}"

                stats = None
                try:
                    # 与 CLI 批量一致：上限不超过单次查询上限时不做时间游标，
                    # 否则每个目标都会先探测再额外等待限流。
                    if 0 < max_size <= 10000:
                        stats = client.search(
                            query,
                            size=max_size,
                            fields=fields,
                            cancel_check=cancel_check,
                        )
                    else:
                        stats = client.search_all_efficient(
                            query,
                            max_size=max_size,
                            fields=fields,
                            fill_percent=fill_percent,
                            progress_callback=_create_web_batch_progress_callback(
                                task_id, batch_idx, total_queries, base_count
                            ),
                            cancel_check=cancel_check,
                        )
                    all_results.extend(stats.results)
                except FofaAPIError:
                    failed_count += 1

                progress = (batch_idx + 1) / total_queries
                with _export_lock:
                    task = _export_tasks.get(task_id)
                    if task:
                        task.progress = progress
                        task.fetched = len(all_results)
                        task.current_fetched = len(stats.results) if stats else 0
                        task.message = f"Target {batch_idx + 1}/{total_queries}"
                        task.failed_count = failed_count

                if batch_idx < total_queries - 1:
                    # 目标间隔同样可被取消中断，补齐批量模式的取消响应
                    _sleep_interruptible(2, cancel_check)

            output_files = _write_web_exports("fofa_batch", all_results, fields)

            done_fields = {"failed_count": failed_count}
            if failed_count:
                done_fields["message"] = f"Partial: {failed_count}/{total_queries} failed"
            _finish_export_task(
                task_id,
                "done",
                progress=1.0,
                fetched=len(all_results),
                output_files=output_files,
                **done_fields,
            )
        except KeyboardInterrupt:
            with _export_lock:
                task = _export_tasks.get(task_id)
                discard = bool(task and task.discard)
            if discard:
                _finish_export_task(task_id, "error", error="Cancelled by user")
                return
            if all_results:
                output_files = _write_web_exports("fofa_batch", all_results, fields)
                _finish_export_task(
                    task_id,
                    "done",
                    progress=1.0,
                    partial=True,
                    partial_error="Cancelled by user",
                    message="已取消，已保留部分结果",
                    fetched=len(all_results),
                    output_files=output_files,
                )
            else:
                _finish_export_task(task_id, "error", error="Cancelled by user")
        except Exception as e:
            _finish_export_task(task_id, "error", error=self._safe_error(e))

    def _handle_cancel(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        task_id = params.get("task_id", [None])[0]
        discard = params.get("discard", ["0"])[0] == "1"

        with _export_lock:
            task = _export_tasks.get(task_id)
            if task:
                task.cancelled = True
                if discard:
                    task.discard = True

        self._send_json({"success": True})


def _find_available_port(
    start_port: int = DEFAULT_WEB_PORT,
    max_attempts: int = 20,
    host: str = "127.0.0.1",
) -> int:
    for offset in range(max_attempts):
        port = start_port + offset
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((host, port))
                return port
        except OSError:
            continue
    raise OSError(
        f"未找到可用端口（尝试 {start_port}-{start_port + max_attempts - 1}，"
        f"监听地址 {host}）"
    )


def _open_browser(url: str) -> bool:
    """尝试在本地环境自动打开浏览器；无法打开时返回 False。

    场景处理:
    - WSL 环境: 调起 Windows 侧默认浏览器（explorer.exe）
    - SSH 会话: 跳过自动打开，避免 X11 转发弹窗和 xdg-open 报错刷屏
    - Linux 无图形环境（无 DISPLAY/WAYLAND_DISPLAY）: 跳过自动打开
    - 其他: 交给系统默认浏览器
    """
    try:
        if os.environ.get("WSL_DISTRO_NAME"):
            subprocess.Popen(
                ["explorer.exe", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT"):
            return False
        if sys.platform.startswith("linux") and not (
            os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
        ):
            return False
        webbrowser.open(url)
        return True
    except Exception:
        return False


def _lan_ips() -> list[str]:
    """枚举本机局域网 IPv4 地址（0.0.0.0 监听时用于提示访问地址）。"""
    try:
        ips = {
            ip
            for ip in socket.gethostbyname_ex(socket.gethostname())[2]
            if not ip.startswith("127.")
        }
        return sorted(ips)
    except OSError:
        return []


class FofaWebServer:
    """FOFA Web UI 服务器"""

    def __init__(
        self,
        client: Optional[FofaClient],
        config_manager: Optional[ConfigManager] = None,
        port: int = 0,
        host: str = "127.0.0.1",
        auto_open: bool = True,
    ):
        self.client = client
        self.config_manager = config_manager
        self.host = host
        self.auto_open = auto_open
        try:
            socket.getaddrinfo(host, None, family=socket.AF_INET)
        except socket.gaierror:
            raise ValueError(f"无效的监听地址: {host}") from None
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((host, 0))
        except OSError as e:
            raise ValueError(f"无法绑定监听地址 {host}: {e}") from None
        self.port = port or _find_available_port(host=host)
        self.httpd = None

    def start(self):
        FofaWebHandler.client = self.client
        FofaWebHandler.config_manager = self.config_manager

        # ThreadingHTTPServer 默认已启用 daemon_threads 与
        # allow_reuse_address（HTTPServer 类属性），无需重复设置
        self.httpd = http.server.ThreadingHTTPServer(
            (self.host, self.port), FofaWebHandler
        )
        start_export_cleanup_timer()

        is_wildcard = self.host == "0.0.0.0"
        url_host = "127.0.0.1" if is_wildcard else self.host
        print(f"\n{GREEN}[*] Web UI 已启动: {CYAN}http://{url_host}:{self.port}{RESET}")
        if is_wildcard:
            for ip in _lan_ips():
                print(f"[*] 局域网访问: {CYAN}http://{ip}:{self.port}{RESET}")
        if self.host not in ("127.0.0.1", "localhost", "::1"):
            print(
                f"{YELLOW}[!] 监听地址为非回环地址，Web UI 无访问鉴权，"
                f"局域网内任何人可访问并使用你的 FOFA 配额{RESET}"
            )
        print(f"[*] 按 {RED}Ctrl+C{RESET} 停止服务器\n")

        url = f"http://{url_host}:{self.port}"
        if self.auto_open and not _open_browser(url):
            print(
                f"[*] 当前环境无图形桌面，请在浏览器手动打开: {CYAN}{url}{RESET}"
            )

        try:
            self.httpd.serve_forever()
        except KeyboardInterrupt:
            print(f"\n[*] 服务器已停止")
            stop_export_cleanup_timer()
            self.httpd.shutdown()


# ============ 主函数 ============


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.icon and args.web:
        print("[!] --icon 与 -w/--web 不能同时使用", file=sys.stderr)
        sys.exit(1)
    if args.icon and args.batch_file:
        print("[!] --icon 与 -b/--batch 不能同时使用", file=sys.stderr)
        sys.exit(1)
    web_mode = args.web or (not args.query and not args.batch_file and not args.check and not args.icon)

    config_manager = ConfigManager()
    config_file_ready = config_manager.ensure_exists()

    # 显示 Banner
    print(BANNER)

    # 加载配置
    config_manager.load()

    client = None
    if not config_manager.is_valid():
        if web_mode:
            print(f"[*] 配置文件: {config_manager.config_file}")
            print("[*] Web UI 将显示 API Key 配置引导")
        else:
            print("[!] 未找到有效的 FOFA API 凭证", file=sys.stderr)
            print(f"[*] 配置文件: {config_manager.config_file}", file=sys.stderr)
    else:
        client = config_manager.get_client()

    # Web UI 模式: -w 参数 或 无参数直接运行
    if web_mode:
        try:
            server = FofaWebServer(
                client,
                config_manager=config_manager,
                port=args.port,
                host=args.host or "127.0.0.1",
                auto_open=args.host is None,
            )
        except ValueError as e:
            print(f"[!] {e}", file=sys.stderr)
            sys.exit(1)
        server.start()
        return

    if not config_file_ready or not client:
        if args.check:
            print("[!] 配置无效，请检查 config.json", file=sys.stderr)
            print(f"[*] 配置文件: {config_manager.config_file}")
            sys.exit(1)
        print("\n请填入配置后重试:", file=sys.stderr)
        print(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=4), file=sys.stderr)
        sys.exit(1)

    print_account_status(client)

    if args.check:
        return

    if args.fill <= 0 or args.fill > 1:
        print("[!] --fill 取值范围必须在 (0, 1]", file=sys.stderr)
        sys.exit(1)

    if args.batch_file:
        handle_batch_mode(client, args)
    elif args.icon:
        handle_icon_mode(client, args)
    else:
        if not args.query:
            sys.stderr.write(parser.format_usage())
            sys.exit(1)
        handle_single_mode(client, args)


def expand_placeholder_query(
    base_query: str, targets: list[str], placeholder: str
) -> list[tuple[str, int]]:
    """
    将占位符替换为具体值

    Args:
        base_query: 包含占位符的基础查询语句，如 "host={}"
        targets: 目标值列表
        placeholder: 占位符格式，如 "{}"

    Returns:
        [(替换后的查询语句, 目标索引), ...]
    """
    results = []
    for idx, target in enumerate(targets, 1):
        query = base_query.replace(placeholder, target)
        results.append((query, idx))
    return results


def load_batch_targets(file_path: Path) -> list[tuple[str, int]]:
    """
    加载批量目标文件

    Args:
        file_path: 批量目标文件路径

    Returns:
        [(目标值, 行号), ...]
    """
    if not file_path.exists():
        raise FileNotFoundError(f"批量目标文件不存在: {file_path}")

    targets = []
    for line_no, line in enumerate(
        file_path.read_text(encoding="utf-8").splitlines(), 1
    ):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        targets.append((line, line_no))

    if not targets:
        raise ValueError("批量目标文件中没有有效的目标值")

    return targets


def run_batch_search(
    client: FofaClient, queries: list[tuple[str, int]], args
) -> list[FofaResult]:
    """
    执行批量查询

    Args:
        client: FOFA 客户端
        queries: [(查询语句, 行号), ...]
        args: 命令行参数

    Returns:
        所有查询的结果列表
    """
    all_results = []
    total_queries = len(queries)
    is_max, limit_value = parse_limit_value(args.limit)
    query_fields = _merge_dedup_fields(args.fields, args.dedup)
    use_deep = limit_value > 10000 or is_max

    for idx, (query, line_no) in enumerate(queries, 1):
        query = query.strip()
        if not query:
            continue

        print(f"\n{CYAN}[{idx}/{total_queries}] 查询:{RESET} {query}")

        try:
            if use_deep:
                max_size = 0 if is_max else limit_value
                stats = client.search_all_efficient(
                    query,
                    max_size=max_size,
                    fields=query_fields,
                    fill_percent=args.fill,
                    full=args.full,
                    progress_callback=create_console_progress_callback(),
                )
            else:
                stats = client.search(
                    query, size=limit_value, fields=query_fields, full=args.full
                )

            all_results.extend(stats.results)
            print(f"    {GREEN}+{RESET} 获取 {len(stats.results)} 条结果")

        except FofaAPIError as e:
            print(f"    {RED}!{RESET} API 错误: {e}")
        except Exception as e:
            print(f"    {RED}!{RESET} 错误: {e}")

        if idx < total_queries:
            time.sleep(2)

    return all_results


def export_results(results, args):
    """导出结果"""
    output_path = Path(args.output)
    exported = 0

    formats = []
    if args.csv:
        formats.append(("csv", ".csv", "CSV"))
    if args.txt:
        formats.append(("txt", ".txt", "TXT"))
    if args.json:
        formats.append(("json", ".json", "JSON"))

    exporter = Exporter(results, fields=args.fields, dedup_field=args.dedup)

    def resolve_output_path(suffix: str) -> Path:
        if len(formats) == 1:
            target = output_path
            if output_path.suffix.lower() != suffix:
                target = output_path.with_suffix(suffix)
            return unique_path(target)
        if output_path.suffix:
            target = output_path.with_suffix(suffix)
        else:
            target = output_path.parent / f"{output_path.name}{suffix}"
        return unique_path(target)

    if args.csv:
        csv_path = resolve_output_path(".csv")
        count = exporter.export_csv(csv_path)
        print(f"[+] 已导出 CSV: {csv_path} ({count} 条)")
        exported += 1

    if args.txt:
        txt_path = resolve_output_path(".txt")
        count = exporter.export_txt(txt_path)
        print(f"[+] 已导出 TXT: {txt_path} ({count} 条)")
        exported += 1

    if args.json:
        json_path = resolve_output_path(".json")
        count = exporter.export_json(json_path)
        print(f"[+] 已导出 JSON: {json_path} ({count} 条)")
        exported += 1

    if exported == 0:
        print("[-] 没有导出任何文件（请指定输出格式）")


if __name__ == "__main__":
    main()
