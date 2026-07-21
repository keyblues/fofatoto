#!/usr/bin/env python3
"""
FOFA 查询工具 - 单文件
"""

from __future__ import annotations

import argparse
import base64
import csv
import http.server
import ipaddress
import json
import os
import re
import socket
import socketserver
import sys
import tempfile
import threading
import time
import urllib.request
import uuid
import webbrowser
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import parse_qs, urlparse

# ============ Banner ============

APP_VERSION = "1.3.0"
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
.search-row{display:flex;gap:8px}
.search-input-wrap{position:relative;flex:1;min-width:0}
.search-row input[type=text]{width:100%;padding:8px 12px;font-size:13px;font-family:"SF Mono","Fira Code",Consolas,Monaco,monospace;border:1px solid var(--border);border-radius:2px;background:#fafbfc;color:var(--text);outline:none;transition:all 0.15s ease}
.search-row input[type=text]:focus{border-color:var(--accent);background:#fff}
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
.options-row{display:flex;gap:16px;align-items:center;margin-top:12px;flex-wrap:wrap}
.options-row label{font-size:12px;color:var(--text-secondary);font-weight:600}
.options-row select,.options-row input[type=number]{padding:4px 8px;font-size:12px;border:1px solid var(--border);border-radius:2px;background:#fafbfc;margin-left:4px;transition:all 0.15s ease}
.options-row select{-webkit-appearance:none;-moz-appearance:none;appearance:none;padding:4px 24px 4px 8px;font-size:11px;font-weight:600;color:var(--text-secondary);cursor:pointer;background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'><path d='M2 4l3 3 3-3' fill='none' stroke='%2364748b' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/></svg>");background-repeat:no-repeat;background-position:right 6px center;background-color:var(--card-bg)}
.options-row select:hover{border-color:var(--accent);color:var(--accent)}
.options-row select:focus,.options-row input[type=number]:focus{border-color:var(--accent);background-color:#fff;outline:none}
.options-row select:focus{background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'><path d='M2 4l3 3 3-3' fill='none' stroke='%233182ce' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/></svg>")}
.options-row input[type=number]{width:80px}
.options-row input[type=text]{padding:4px 8px;font-size:12px;border:1px solid var(--border);border-radius:2px;background:#fafbfc;margin-left:4px;transition:all 0.15s ease}
.options-row input[type=text]:focus{border-color:var(--accent);background:#fff;outline:none}
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
th{background:var(--table-header);padding:7px 12px;text-align:left;font-weight:600;font-size:11px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:.5px;border-bottom:2px solid var(--border);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer;user-select:none;transition:all 0.15s ease}
th:hover{color:var(--text)}
th.sorted{color:var(--accent)}
td{padding:7px 12px;border-bottom:1px solid var(--border);max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11.5px}
tr:nth-child(even){background:var(--table-stripe)}
tr:hover{background:#e8f0fe}
td a{color:var(--accent);text-decoration:none;transition:all 0.15s ease}
td a:hover{text-decoration:underline}
td.mono{font-family:"SF Mono","Fira Code",Consolas,Monaco,monospace;font-size:11px}
.overlay{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(15,36,64,.85);z-index:1000;justify-content:center;align-items:center}
.overlay.show{display:flex}
.overlay-content{background:var(--card-bg);border:1px solid var(--border);border-radius:2px;padding:32px 40px;min-width:420px;max-width:520px}
.overlay-content h3{font-size:15px;font-weight:700;margin-bottom:20px;color:var(--primary)}
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
<input type="text" id="queryInput" placeholder="FOFA 查询语法，如 domain=baidu.com" autofocus autocomplete="off" spellcheck="false">
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
<div class="settings-wrap"><button class="mini-btn" onclick="toggleSettings(event)">设置</button><div class="settings-popup" id="settingsPopup"><label><input type="checkbox" id="fitToWindow" checked onchange="toggleFitToWindow(this)"> 适应窗口宽度</label><label><input type="checkbox" id="instantFull"> 全部数据</label><label><input type="checkbox" id="instantAutoQuery"> 选取查询后自动搜索</label></div></div>
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
<script>
var fieldCategories=[
{name:"核心",fields:["host","ip","port","protocol","domain"]},
{name:"服务",fields:["title","server","product","version"]},
{name:"位置",fields:["country","city","region","country_name","latitude","longitude"]},
{name:"网络",fields:["asn","org","base_protocol","link","url"]},
{name:"证书",fields:["cert","jarm","icp","cname","header","banner"]},
{name:"时间",fields:["lastupdatetime"]},
{name:"系统",fields:["os","product_category"]}
];
var allFields=[];fieldCategories.forEach(function(c){c.fields.forEach(function(f){allFields.push(f)})});
var selectedFields=__DEFAULT_FIELDS_JSON__;
var currentMode="instant",currentResults=[],currentColumns=[],currentView=[],rowHeight=0,OVERSCAN=10,previewRendered=false,exportTaskId=null,exportPollTimer=null,progressUiMode="overlay",sortColumn=null,sortAsc=true,historyActiveIndex=-1,historyVisibleItems=[];
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
document.addEventListener("DOMContentLoaded",function(){initFieldSelector();loadAccountInfo();setupModeTabs();setupSearchShortcut();updateHistoryCount();updateLayout();window.addEventListener("resize",function(){updateLayout();renderVirtual()})});
function setupModeTabs(){document.querySelectorAll(".mode-tab").forEach(function(t){t.addEventListener("click",function(){switchMode(this.dataset.mode)})})}
function modeButtonText(){return currentMode==="instant"?"搜索":(currentMode==="export"?"导出":"批量查询")}
function refreshModeButton(){var btn=document.getElementById("searchBtn");btn.textContent=modeButtonText();btn.className="btn btn-primary"}
function switchMode(mode){if(exportPollTimer&&currentMode!==mode){showMessage("error","已有导出任务正在运行，请先取消或等待完成");return}currentMode=mode;document.querySelectorAll(".mode-tab").forEach(function(t){t.classList.toggle("active",t.dataset.mode===mode)});document.getElementById("instantOptions").style.display=mode==="instant"?"":"none";document.getElementById("exportOptions").style.display=mode==="export"?"":"none";document.getElementById("batchOptions").style.display=mode==="batch"?"":"none";if(!document.getElementById("searchBtn").disabled)refreshModeButton();clearMessage();updateLayout();document.getElementById("queryInput").focus()}
function syncModeContent(){var results=document.getElementById("resultsArea"),panel=document.getElementById("exportPanel");if(results)results.style.display=currentMode==="instant"&&previewRendered?"block":"none";if(panel)panel.style.display=currentMode==="export"&&panel.classList.contains("show")?"":"none"}
function setupSearchShortcut(){var input=document.getElementById("queryInput");input.addEventListener("focus",function(){renderHistorySuggestions(true)});input.addEventListener("input",function(){renderHistorySuggestions(false)});input.addEventListener("keydown",function(e){var dd=document.getElementById("historyDropdown"),open=dd&&dd.classList.contains("show");if(e.key==="ArrowDown"){e.preventDefault();if(!open)renderHistorySuggestions(true);moveHistorySelection(1)}else if(e.key==="ArrowUp"){e.preventDefault();if(!open)renderHistorySuggestions(true);moveHistorySelection(-1)}else if(e.key==="Escape"){closeHistorySuggestions()}else if(e.key==="Enter"){if(open&&historyActiveIndex>-1&&pickActiveHistory()){e.preventDefault();return}closeHistorySuggestions();executeSearch()}})}
function showConfigNotice(d){var box=document.getElementById("configAlert");document.getElementById("configAlertTitle").textContent="未配置有效的 FOFA API Key";document.getElementById("configAlertText").textContent="请编辑下方配置文件，保存后刷新本页面。";document.getElementById("configPath").textContent=d.config_path||"";document.getElementById("configTemplate").textContent=d.config_template||"";box.classList.add("show")}
function hideConfigNotice(){document.getElementById("configAlert").classList.remove("show")}
function formatApiError(data,fallback){var msg=(data&&data.error)||fallback||"请求失败";if(data&&data.data&&data.data.configured===false&&data.data.config_path){msg+="。配置文件: "+data.data.config_path}return msg}
function loadAccountInfo(){fetch("/api/info").then(function(r){return r.json()}).then(function(data){var d=data.data||{};if(d.configured===false){showConfigNotice(d);document.getElementById("accountInfo").innerHTML='<span class="vip-badge inactive">未配置</span> 等待 API Key';return}hideConfigNotice();if(data.success){if(d.relay){var vClass=d.isvip?"active":"inactive",vText=d.isvip?"有效":"无效";var h='<span class="vip-badge inactive">中转站</span> <span class="vip-badge '+vClass+'">'+vText+'</span> '+"剩余查询: <strong>"+(d.remain_api_query||"N/A")+"</strong>";if(d.today_remaining!==null&&d.today_remaining!==undefined)h+=" | 今日剩余: <strong>"+d.today_remaining+"</strong>";h+=" | 过期: "+(d.expiration||"N/A");document.getElementById("accountInfo").innerHTML=h}else{var vipClass=d.isvip?"active":"inactive",vipText=d.isvip?"VIP "+(d.vip_level||""):"未激活",serverText=d.server_ok?"正常":"异常",serverClass=d.server_ok?"ok":"fail";document.getElementById("accountInfo").innerHTML='<span class="vip-badge '+vipClass+'">'+vipText+'</span> 服务器: <span class="server-status '+serverClass+'">'+serverText+'</span> | 剩余查询: <strong>'+(d.remain_api_query||"N/A")+'</strong> | 过期: '+(d.expiration||"N/A");if(d.server_ok===false&&d.error)showMessage("error",d.error)}}else{document.getElementById("accountInfo").innerHTML='<span class="vip-badge inactive">异常</span> 账户信息不可用';showMessage("error",formatApiError(data,"账户信息不可用"))}}).catch(function(e){document.getElementById("accountInfo").innerHTML='<span class="vip-badge inactive">异常</span> 本地服务不可用';showMessage("error","网络错误: "+e.message)}).finally(function(){updateLayout()})}
function executeSearch(){var q=document.getElementById("queryInput").value.trim();if(!q)return;closeHistorySuggestions();addToHistory(q);if(currentMode==="instant")doInstantSearch(q);else if(currentMode==="export")doDeepExport(q);else doBatchSearch(q)}
function doInstantSearch(query){var size=parseInt(document.getElementById("instantSize").value)||100,fields=getSelectedFields(),full=document.getElementById("instantFull").checked;clearResults();showMessage("info","搜索中...");fetch("/api/search",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query:query,size:size,fields:fields,full:full})}).then(function(r){return r.json()}).then(function(data){clearMessage();if(data.success){currentResults=data.data.results||[];currentColumns=data.data.columns||[];var _sb=getScrollBox();if(_sb)_sb.scrollTop=0;renderResults(data.data)}else showMessage("error",formatApiError(data,"搜索失败"))}).catch(function(e){showMessage("error","网络错误: "+e.message)})}
function doDeepExport(query){var fill=parseFloat(document.getElementById("exportFill").value),maxSize=parseInt(document.getElementById("exportMaxSize").value)||0,fields=getSelectedFields(),full=document.getElementById("exportFull").checked;if(isNaN(fill))fill=0.8;if(fill<=0||fill>1){showMessage("error","覆盖率必须在 0 到 1 之间");return}if(maxSize<0){showMessage("error","上限不能小于 0");return}if(exportPollTimer){showMessage("error","已有导出任务正在运行，请先取消或等待完成");return}progressUiMode="panel";exportTaskId=null;clearMessage();showExportPanelStart(query,fill,maxSize,full);setSearchBusy(true,"导出中...");fetch("/api/export",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query:query,fill_percent:fill,max_size:maxSize,fields:fields,full:full})}).then(function(r){return r.json()}).then(function(data){if(data.success){exportTaskId=data.task_id;pollProgress()}else{setSearchBusy(false);showExportPanelError(formatApiError(data,"导出失败"))}}).catch(function(e){setSearchBusy(false);showExportPanelError("网络错误: "+e.message)})}
function doBatchSearch(baseQuery){var ph=document.getElementById("batchPlaceholder").value||"{}",targets=document.getElementById("batchTargets").value.trim(),fill=parseFloat(document.getElementById("batchFill").value)||0.8,fields=getSelectedFields();if(!targets){showMessage("error","请输入批量目标");return}if(baseQuery.indexOf(ph)===-1){showMessage("error","基础查询必须包含占位符: "+ph);return}if(exportPollTimer){showMessage("error","已有任务正在运行，请先取消或等待完成");return}var targetLines=targets.replace(/\r/g,"").split("\n").filter(function(l){return l.trim()});progressUiMode="panel";exportTaskId=null;clearMessage();showBatchPanelStart(baseQuery,targetLines.length,ph,fill);setSearchBusy(true,"批量查询中...");fetch("/api/batch",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({base_query:baseQuery,targets:targetLines,placeholder:ph,fill_percent:fill,fields:fields})}).then(function(r){return r.json()}).then(function(data){if(data.success){exportTaskId=data.task_id;pollProgress()}else{setSearchBusy(false);showExportPanelError(formatApiError(data,"批量导出失败"))}}).catch(function(e){setSearchBusy(false);showExportPanelError("网络错误: "+e.message)})}
function renderProgressDetails(d,pct){if(d.kind==="batch"){var current=d.current_target||0,total=d.total_targets||0,curFetched=d.current_fetched||0,curTotal=d.current_target_count||d.current_total_estimated||0;return "进度: <span>"+pct+"%</span><br>目标: <span>"+current+"</span> / "+total+" | 当前: <span>"+curFetched.toLocaleString()+"</span> / ~"+curTotal.toLocaleString()+"<br>累计结果: <span>"+(d.fetched||0).toLocaleString()+"</span> | 失败: <span>"+(d.failed_count||0).toLocaleString()+"</span>"}var target=d.target_count||d.total_estimated||0;return "进度: <span>"+pct+"%</span><br>已获取: <span>"+(d.fetched||0).toLocaleString()+"</span> / ~"+target.toLocaleString()+"<br>总匹配: <span>"+(d.total_estimated||0).toLocaleString()+"</span> | 独立IP: <span>"+(d.unique_ips||0).toLocaleString()+"</span> | 配额: <span>"+(d.total_quota_used||0).toLocaleString()+"</span>"}
function exportMetaItem(label,value){return '<div class="export-meta-item"><span class="export-meta-label">'+escHtml(label)+'</span><span class="export-meta-value">'+escHtml(value)+'</span></div>'}
function exportTarget(d){return d.target_count||d.total_estimated||0}
function showExportPanelStart(query,fill,maxSize,full){document.getElementById("exportPanel").classList.add("show");document.getElementById("exportPanelTitle").textContent="深度导出";document.getElementById("exportPanelState").textContent="启动中";document.getElementById("exportPanelFill").style.width="0%";document.getElementById("exportPanelMessage").textContent="正在创建导出任务，完成后可下载 CSV / JSON / TXT。";document.getElementById("exportPanelMeta").innerHTML=exportMetaItem("查询",query)+exportMetaItem("覆盖率",Math.round(fill*100)+"%")+exportMetaItem("上限",maxSize>0?maxSize.toLocaleString():"不限制")+exportMetaItem("数据范围",full?"全部数据":"基础字段");document.getElementById("exportPanelActions").innerHTML='<button class="btn btn-secondary" onclick="cancelExport()">取消</button>';updateLayout()}
function showBatchPanelStart(baseQuery,targetCount,placeholder,fill){document.getElementById("exportPanel").classList.add("show");document.getElementById("exportPanelTitle").textContent="批量查询";document.getElementById("exportPanelState").textContent="启动中";document.getElementById("exportPanelFill").style.width="0%";document.getElementById("exportPanelMessage").textContent="正在创建批量查询任务，完成后可下载 CSV / JSON / TXT。";document.getElementById("exportPanelMeta").innerHTML=exportMetaItem("基础查询",baseQuery)+exportMetaItem("占位符",placeholder)+exportMetaItem("目标数",targetCount.toLocaleString())+exportMetaItem("覆盖率",Math.round(fill*100)+"%");document.getElementById("exportPanelActions").innerHTML='<button class="btn btn-secondary" onclick="cancelExport()">取消</button>';updateLayout()}
function showExportPanelError(message){document.getElementById("exportPanel").classList.add("show");document.getElementById("exportPanelState").textContent="失败";document.getElementById("exportPanelMessage").innerHTML='<span style="color:#dc2626">'+escHtml(message)+"</span>";document.getElementById("exportPanelActions").innerHTML='<button class="btn btn-secondary" onclick="hideExportPanel()">关闭</button>';updateLayout()}
function updateExportPanel(d,pct){var target=exportTarget(d),fetched=d.fetched||0,elapsed=d.elapsed_seconds?d.elapsed_seconds+" 秒":"刚开始";document.getElementById("exportPanel").classList.add("show");document.getElementById("exportPanelFill").style.width=pct+"%";document.getElementById("exportPanelState").textContent=d.status==="done"?(d.partial?"部分完成":"完成"):(d.status==="error"?"失败":pct+"%");document.getElementById("exportPanelMessage").textContent=d.status==="done"?(d.partial?("部分导出完成，已保留 "+fetched.toLocaleString()+" 条可用结果。"):"导出文件已生成，可选择格式下载。"):(d.message||(d.kind==="batch"?"正在批量查询...":"正在按时间游标分批拉取 FOFA 数据..."));document.getElementById("exportPanelMeta").innerHTML=d.kind==="batch"?exportMetaItem("目标",(d.current_target||0)+" / "+(d.total_targets||0))+exportMetaItem("当前",(d.current_fetched||0).toLocaleString()+" / ~"+(d.current_target_count||d.current_total_estimated||0).toLocaleString())+exportMetaItem("累计",(d.fetched||0).toLocaleString())+exportMetaItem("失败",(d.failed_count||0).toLocaleString())+exportMetaItem("耗时",elapsed):exportMetaItem("已获取",fetched.toLocaleString())+exportMetaItem("目标",target?("~"+target.toLocaleString()):"估算中")+exportMetaItem("总匹配",((d.total_estimated||0).toLocaleString()))+exportMetaItem("独立 IP",((d.unique_ips||0).toLocaleString()))+exportMetaItem("配额",((d.total_quota_used||0).toLocaleString()))+exportMetaItem("耗时",elapsed);if(d.status==="done"){document.getElementById("exportPanelActions").innerHTML='<button class="btn btn-primary" onclick="downloadExport(\'csv\')">下载 CSV</button><button class="btn btn-secondary" onclick="downloadExport(\'json\')">下载 JSON</button><button class="btn btn-secondary" onclick="downloadExport(\'txt\')">下载 TXT</button><button class="btn btn-secondary" onclick="hideExportPanel()">收起</button>'}else if(d.status==="error"){document.getElementById("exportPanelActions").innerHTML='<button class="btn btn-secondary" onclick="hideExportPanel()">关闭</button>';document.getElementById("exportPanelMessage").innerHTML='<span style="color:#dc2626">'+escHtml(d.error||"未知错误")+"</span>"}else{document.getElementById("exportPanelActions").innerHTML='<button class="btn btn-secondary" onclick="cancelExport()">取消</button>'}updateLayout()}
function hideExportPanel(){document.getElementById("exportPanel").classList.remove("show");updateLayout()}
function setSearchBusy(busy,label){var btn=document.getElementById("searchBtn");btn.disabled=!!busy;if(busy)btn.textContent=label||"处理中...";else refreshModeButton()}
function pollProgress(){if(!exportTaskId)return;if(exportPollTimer)clearInterval(exportPollTimer);exportPollTimer=setInterval(function(){fetch("/api/progress?task_id="+exportTaskId).then(function(r){return r.json()}).then(function(data){if(!data.success){clearInterval(exportPollTimer);exportPollTimer=null;setSearchBusy(false);var err=formatApiError(data,"任务状态不可用");if(progressUiMode==="panel")showExportPanelError(err);else{document.getElementById("progressTitle").textContent="导出失败";document.getElementById("progressDetails").innerHTML='<span style="color:#dc2626">'+escHtml(err)+"</span>";document.getElementById("progressActions").innerHTML='<button class="btn btn-secondary" onclick="hideOverlay()">关闭</button>'}return}var d=data.data,pct=(Math.max(0,Math.min(d.progress||0,1))*100).toFixed(1);if(progressUiMode==="panel")updateExportPanel(d,pct);else{document.getElementById("progressFill").style.width=pct+"%";document.getElementById("progressDetails").innerHTML=renderProgressDetails(d,pct)}if(d.status==="done"){clearInterval(exportPollTimer);exportPollTimer=null;setSearchBusy(false);if(progressUiMode==="panel")updateExportPanel(d,"100.0");else{document.getElementById("progressTitle").textContent=d.kind==="batch"?"批量导出完成":"导出完成";document.getElementById("progressActions").innerHTML='<button class="btn btn-primary" onclick="downloadExport(\'csv\')">下载 CSV</button><button class="btn btn-secondary" onclick="downloadExport(\'json\')">下载 JSON</button><button class="btn btn-secondary" onclick="downloadExport(\'txt\')">下载 TXT</button><button class="btn btn-secondary" onclick="hideOverlay()">关闭</button>'}}else if(d.status==="error"){clearInterval(exportPollTimer);exportPollTimer=null;setSearchBusy(false);if(progressUiMode==="panel")updateExportPanel(d,pct);else{document.getElementById("progressTitle").textContent="导出失败";document.getElementById("progressDetails").innerHTML='<span style="color:#dc2626">'+escHtml(d.error||"未知错误")+"</span>";document.getElementById("progressActions").innerHTML='<button class="btn btn-secondary" onclick="hideOverlay()">关闭</button>'}}}).catch(function(e){clearInterval(exportPollTimer);exportPollTimer=null;setSearchBusy(false);if(progressUiMode==="panel")showExportPanelError("网络错误: "+e.message);else{document.getElementById("progressTitle").textContent="导出失败";document.getElementById("progressDetails").innerHTML='<span style="color:#dc2626">网络错误: '+escHtml(e.message)+"</span>";document.getElementById("progressActions").innerHTML='<button class="btn btn-secondary" onclick="hideOverlay()">关闭</button>'}})},800)}
function cancelExport(){if(exportTaskId)document.getElementById("cancelOverlay").classList.add("show")}
function confirmCancel(save){if(!exportTaskId)return;document.getElementById("cancelOverlay").classList.remove("show");var discard=save?"0":"1";if(progressUiMode==="panel"){document.getElementById("exportPanelState").textContent="取消中";document.getElementById("exportPanelActions").innerHTML="";document.getElementById("exportPanelMessage").textContent="取消请求已发送，正在等待当前请求结束..."}else{document.getElementById("progressTitle").textContent="正在取消";document.getElementById("progressActions").innerHTML="";document.getElementById("progressDetails").innerHTML="取消请求已发送，正在等待当前请求结束..."}fetch("/api/progress/cancel?task_id="+exportTaskId+"&discard="+discard,{method:"POST"})}
function hideCancelConfirm(){document.getElementById("cancelOverlay").classList.remove("show")}
function downloadExport(format){if(exportTaskId)window.open("/api/export/download?task_id="+exportTaskId+"&format="+format,"_blank")}
function showOverlay(title){document.getElementById("progressTitle").textContent=title;document.getElementById("progressFill").style.width="0%";document.getElementById("progressDetails").innerHTML="初始化中...";document.getElementById("progressActions").innerHTML='<button class="btn btn-secondary" onclick="cancelExport()">取消</button>';document.getElementById("progressOverlay").classList.add("show")}
function hideOverlay(){document.getElementById("progressOverlay").classList.remove("show")}
function renderResults(data){var area=document.getElementById("resultsArea"),rows=data.results||[],table=document.getElementById("resultsTable"),empty=document.getElementById("emptyState");previewRendered=true;syncModeContent();var pickBtns='<button class="mini-btn" id="pickFilterBtn" onclick="enterPickMode(\'filter\')">不看</button><button class="mini-btn" id="pickQueryBtn" onclick="enterPickMode(\'query\')">选取查询</button>';var actions=rows.length>0?'<div class="stats-actions"><span class="preview-status" id="previewStatus"></span>'+pickBtns+'<button class="mini-btn" onclick="exportPreview(&quot;csv&quot;)">导出 CSV</button><button class="mini-btn" onclick="exportPreview(&quot;json&quot;)">JSON</button><button class="mini-btn" onclick="exportPreview(&quot;txt&quot;)">TXT</button></div>':"";document.getElementById("statsBar").innerHTML='<div class="stats-metrics"><span class="stat-item"><span class="stat-dot" style="background:var(--accent)"></span>总计: <span class="stat-value">'+(data.total||0).toLocaleString()+'</span></span><span class="stat-item"><span class="stat-dot" style="background:var(--success)"></span>独立IP: <span class="stat-value">'+(data.unique_ips||0).toLocaleString()+'</span></span><span class="stat-item"><span class="stat-dot" style="background:var(--warning)"></span>结果: <span class="stat-value">'+rows.length.toLocaleString()+'</span></span></div>'+actions;var cols=data.columns||[];if(cols.length===0&&rows.length>0)cols=Object.keys(rows[0]);currentColumns=cols;if(rows.length===0){table.style.display="none";empty.style.display="block";empty.textContent=excludedFilters.length?"所有结果已被「不看」排除，移除排除项可恢复显示。":((data.total||0)>0?"当前预览没有返回记录，可调大数量或更换字段后重试。":"没有匹配结果。");document.querySelector("#resultsTable thead").innerHTML="";document.querySelector("#resultsTable tbody").innerHTML="";updateLayout();return}table.style.display="table";empty.style.display="none";var thead="";cols.forEach(function(col){var sc=sortColumn===col?" sorted":"";thead+="<th class=\""+sc+"\" onclick=\"sortBy('"+escHtml(col)+"')\">"+(sortColumn===col?(sortAsc?"▲ ":"▼ "):"")+escHtml(col)+"</th>"});document.querySelector("#resultsTable thead").innerHTML="<tr>"+thead+"</tr>";currentView=rows;stabilizeColumnWidths();setupVirtualScroll();updateLayout();renderVirtual()}
function buildRowsHtml(pageRows,cols){var html="";pageRows.forEach(function(row){html+="<tr>";cols.forEach(function(col){var val=row[col]!==undefined?row[col]:"",cls=(col==="ip"||col==="port"||col==="host")?" mono":"";if((col==="host"||col==="url")&&val){var url=val.indexOf("http")===0?val:"http://"+val;html+='<td class="'+cls+'"><a href="'+escHtml(url)+'" target="_blank" rel="noopener">'+escHtml(val)+"</a></td>"}else html+='<td class="'+cls+'" title="'+escHtml(val)+'">'+escHtml(val)+"</td>"});html+="</tr>"});return html}
function getScrollBox(){return document.getElementById("resultsTable").parentElement}
function measureRowHeight(){var cols=currentColumns,probe=currentView[0]||{},tbody=document.querySelector("#resultsTable tbody");tbody.innerHTML=buildRowsHtml([probe],cols);var tr=tbody.querySelector("tr");var h=tr?tr.offsetHeight:0;return h>0?h:31}
var colWidthsRef=null;var fitToWindow=true;function toggleFitToWindow(el){fitToWindow=el.checked;colWidthsRef=null;stabilizeColumnWidths();renderVirtual()}function stabilizeColumnWidths(){var table=document.getElementById("resultsTable");var oldCg=table.querySelector("colgroup");if(colWidthsRef===currentResults&&oldCg)return;colWidthsRef=currentResults;var cols=currentColumns;if(oldCg)oldCg.remove();if(!cols.length||!currentResults.length){table.style.tableLayout="";table.style.width="";return}var tbody=document.querySelector("#resultsTable tbody");tbody.innerHTML=buildRowsHtml(currentResults.slice(0,Math.min(100,currentResults.length)),cols);var firstRow=tbody.querySelector("tr");if(!firstRow){table.style.tableLayout="";table.style.width="";return}table.style.width="auto";table.style.tableLayout="auto";var h=firstRow.offsetHeight;if(h>0)rowHeight=h;var widths=[];firstRow.querySelectorAll("td").forEach(function(td){widths.push(td.offsetWidth)});table.style.width="";var cg=document.createElement("colgroup");if(fitToWindow){var total=0;widths.forEach(function(w){total+=w});cols.forEach(function(col,i){var el=document.createElement("col");var w=widths[i]||100;el.style.width=total>0?((w/total)*100).toFixed(3)+"%":w+"px";cg.appendChild(el)})}else{cols.forEach(function(col,i){var el=document.createElement("col");el.style.width=(widths[i]||100)+"px";cg.appendChild(el)})}table.insertBefore(cg,table.firstChild);table.style.tableLayout="fixed"}
function renderVirtual(){var box=getScrollBox();if(!box)return;var total=currentView.length,tbody=document.querySelector("#resultsTable tbody");if(total===0){tbody.innerHTML="";return}if(!rowHeight)rowHeight=measureRowHeight();var cols=currentColumns,vh=parseFloat(box.style.maxHeight)||box.clientHeight;var maxSt=Math.max(0,total*rowHeight-vh);var st=box.scrollTop;if(st>maxSt){st=maxSt;box.scrollTop=maxSt}var start=Math.max(0,Math.floor(st/rowHeight)-OVERSCAN);var end=Math.min(total,Math.ceil((st+vh)/rowHeight)+OVERSCAN);var html='<tr><td colspan="'+cols.length+'" style="height:'+(start*rowHeight)+'px;padding:0;border:0"></td></tr>'+buildRowsHtml(currentView.slice(start,end),cols)+'<tr><td colspan="'+cols.length+'" style="height:'+((total-end)*rowHeight)+'px;padding:0;border:0"></td></tr>';tbody.innerHTML=html}
function setupVirtualScroll(){var box=getScrollBox();if(!box||box._vsBound)return;box._vsBound=true;var tick=false;box.addEventListener("scroll",function(){if(tick)return;tick=true;requestAnimationFrame(function(){tick=false;renderVirtual()})})}
function previewTimestamp(){return new Date().toISOString().replace(/[-:]/g,"").replace(/\..+/,"").replace("T","_")}
function previewColumns(){return currentColumns.length?currentColumns:Object.keys(currentResults[0]||{})}
function previewRows(){var cols=previewColumns(),src=currentResults;if(excludedFilters.length){src=src.filter(function(r){return !excludedFilters.some(function(f){return String(r[f.field]||"")===String(f.value)})})}return src.map(function(row){var out={};cols.forEach(function(col){out[col]=row[col]!==undefined&&row[col]!==null?row[col]:""});return out})}
function csvCell(v){var s=v===undefined||v===null?"":String(v);return /[",\r\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s}
function previewUrl(row){var val=row.url||row.link||row.host||"";if(!val&&row.ip)val=row.ip;if(val&&row.host&&String(val).indexOf("http")!==0){var protocol=row.protocol?String(row.protocol).toLowerCase():"";if(protocol.indexOf(",")>-1)protocol=protocol.split(",")[0];if(!protocol)protocol=String(row.port)==="443"?"https":"http";val=protocol+"://"+val}return val}
function downloadPreviewBlob(content,filename,type){var blob=new Blob([content],{type:type}),url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download=filename;document.body.appendChild(a);a.click();a.remove();setTimeout(function(){URL.revokeObjectURL(url)},1000)}
function showPreviewStatus(text){var el=document.getElementById("previewStatus");if(el){el.textContent=text;updateLayout()}else showMessage("info",text)}
function exportPreview(format){if(!currentResults.length){showMessage("error","当前预览没有可导出的结果");return}var cols=previewColumns(),rows=previewRows(),ts=previewTimestamp(),content="",filename="fofatoto_preview_"+ts+"."+format,type="text/plain;charset=utf-8";var src=currentResults;if(excludedFilters.length){src=src.filter(function(r){return !excludedFilters.some(function(f){return String(r[f.field]||"")===String(f.value)})})}var exportedCount=0;if(format==="csv"){content="\ufeff"+[cols.map(csvCell).join(",")].concat(rows.map(function(row){return cols.map(function(col){return csvCell(row[col])}).join(",")})).join("\r\n")+"\r\n";type="text/csv;charset=utf-8";exportedCount=rows.length}else if(format==="json"){content=JSON.stringify(rows,null,2)+"\n";type="application/json;charset=utf-8";exportedCount=rows.length}else{var values;if(cols.length===1&&cols[0]==="ip")values=src.map(function(row){return row.ip||""});else if(cols.length===1&&cols[0]==="domain")values=src.map(function(row){return row.domain||""});else values=src.map(previewUrl);values=values.filter(function(v){return v});exportedCount=values.length;content=values.join("\n")+"\n"}downloadPreviewBlob(content,filename,type);clearMessage();showPreviewStatus("已导出 "+exportedCount.toLocaleString()+" 条")}
function sortBy(col){if(sortColumn===col){sortAsc=!sortAsc}else{sortColumn=col;sortAsc=true}currentResults.sort(function(a,b){var va=a[col]||"",vb=b[col]||"";if(va<vb)return sortAsc?-1:1;if(va>vb)return sortAsc?1:-1;return 0});renderCurrentView()}
var pickModeActive=false,pickModeAction="query",excludedFilters=[];
function enterPickMode(mode){if(!currentResults.length){showMessage("error","当前预览没有可选取的结果");return}if(pickModeActive)return;pickModeActive=true;pickModeAction=mode;var t=document.getElementById("resultsTable");t.classList.add("picking");var bId=mode==="filter"?"pickFilterBtn":"pickQueryBtn",b=document.getElementById(bId);if(b)b.classList.add("pick-active");t.addEventListener("click",pickTableClick,true);document.addEventListener("keydown",pickKeyHandler);showPreviewStatus(mode==="filter"?"不看：点击单元格排除该值，Esc 取消":"加入查询：点击单元格选取值加入查询，Esc 取消")}
function exitPickMode(){if(!pickModeActive)return;pickModeActive=false;var t=document.getElementById("resultsTable");if(t){t.classList.remove("picking");t.removeEventListener("click",pickTableClick,true)}["pickFilterBtn","pickQueryBtn"].forEach(function(id){var b=document.getElementById(id);if(b)b.classList.remove("pick-active")});document.removeEventListener("keydown",pickKeyHandler);showPreviewStatus(excludedFilters.length?("已排除 "+excludedFilters.length+" 项"):"")}
function pickTableClick(e){if(!pickModeActive)return;var td=e.target.closest?e.target.closest("td"):null;if(!td)return;e.preventDefault();e.stopPropagation();var idx=td.cellIndex;if(idx<0||idx>=currentColumns.length)return;var field=currentColumns[idx],value=(td.textContent||"").trim();if(!value)return;exitPickMode();if(pickModeAction==="filter")addExclusion(field,value);else applyQueryPick(field,value)}
function pickKeyHandler(e){if(e.key==="Escape"){e.preventDefault();exitPickMode()}}
function applyQueryPick(field,value){var safe=value.replace(/"/g,'\\"');var frag=field+'="'+safe+'"';var input=document.getElementById("queryInput"),cur=input.value.trim();if(!cur)input.value=frag;else if(/(&&|\|\|)\s*$/.test(cur))input.value=cur+" "+frag;else input.value=cur+" && "+frag;input.focus();if(document.getElementById("instantAutoQuery").checked)executeSearch()}
function addExclusion(field,value){for(var i=0;i<excludedFilters.length;i++){if(excludedFilters[i].field===field&&excludedFilters[i].value===value)return}excludedFilters.push({field:field,value:value});renderCurrentView()}
function removeExclusion(index){if(index<0||index>=excludedFilters.length)return;excludedFilters.splice(index,1);renderCurrentView()}
function renderExclusionChips(){var c=document.getElementById("exclusionChips");if(!c)return;var h="";excludedFilters.forEach(function(f,i){h+='<span class="exc-chip">不看 '+escHtml(f.field)+'="'+escHtml(f.value)+'"<span class="exc-x" onclick="removeExclusion('+i+')">&times;</span></span>'});c.innerHTML=h}
function renderCurrentView(){var view=currentResults,ips={};if(excludedFilters.length){view=currentResults.filter(function(r){return !excludedFilters.some(function(f){return String(r[f.field]||"")===String(f.value)})})}view.forEach(function(r){if(r.ip)ips[r.ip]=1});renderResults({results:view,columns:currentColumns,total:currentResults.length,unique_ips:Object.keys(ips).length});renderExclusionChips();if(excludedFilters.length)showPreviewStatus("已排除 "+excludedFilters.length+" 项，显示 "+view.length+"/"+currentResults.length)}
function toggleSettings(e){if(e)e.stopPropagation();var p=document.getElementById("settingsPopup");p.classList.toggle("show")}
function clearResults(){exitPickMode();excludedFilters=[];currentView=[];rowHeight=0;renderExclusionChips();previewRendered=false;document.getElementById("resultsArea").style.display="none";document.getElementById("resultsTable").style.display="table";document.getElementById("emptyState").style.display="none";document.querySelector("#resultsTable thead").innerHTML="";document.querySelector("#resultsTable tbody").innerHTML="";currentResults=[];currentColumns=[];sortColumn=null;updateLayout()}
function updateShellHeight(){var header=document.querySelector(".header");if(header)document.documentElement.style.setProperty("--header-height",Math.ceil(header.getBoundingClientRect().height)+"px")}
function updateLayout(){syncModeContent();updateShellHeight();fitHistoryDropdown();fitResultsHeight()}
function shellBottom(){var shell=document.querySelector(".container");return shell?shell.getBoundingClientRect().bottom:window.innerHeight}
function fitResultsHeight(){var area=document.getElementById("resultsArea"),box=document.querySelector("#resultsArea .table-container");if(!area||!box||area.style.display==="none")return;var rect=box.getBoundingClientRect(),pad=window.innerWidth<=760?12:24,minH=window.innerHeight<560?120:180,msgEl=document.getElementById("messageArea"),msgH=msgEl&&msgEl.offsetHeight?msgEl.offsetHeight+12:0,available=shellBottom()-rect.top-pad-2-msgH;box.style.maxHeight=Math.max(minH,available)+"px"}
function showMessage(type,text){document.getElementById("messageArea").innerHTML='<div class="message '+type+'">'+escHtml(text)+"</div>";updateLayout()}
function clearMessage(){document.getElementById("messageArea").innerHTML="";updateLayout()}
function getHistory(){try{return JSON.parse(localStorage.getItem("fofa_query_history")||"[]")}catch(e){return[]}}
function saveHistory(history){localStorage.setItem("fofa_query_history",JSON.stringify(history))}
function addToHistory(query){try{var history=getHistory();history=history.filter(function(h){return h.query!==query});history.unshift({query:query,mode:currentMode,time:Date.now()});if(history.length>50)history=history.slice(0,50);saveHistory(history);updateHistoryCount()}catch(e){}}
function updateHistoryCount(){var el=document.getElementById("historyCount");if(el)el.textContent=getHistory().length}
function fitHistoryDropdown(){var dd=document.getElementById("historyDropdown");if(!dd||!dd.classList.contains("show"))return;var rect=dd.getBoundingClientRect(),minH=window.innerHeight<520?120:160,maxH=Math.max(minH,shellBottom()-rect.top-12);dd.style.maxHeight=Math.min(320,maxH)+"px"}
function renderHistorySuggestions(showAll){var dd=document.getElementById("historyDropdown"),input=document.getElementById("queryInput");if(!dd||!input)return false;var q=showAll?"":input.value.trim().toLowerCase(),history=getHistory(),items=[];history.forEach(function(h,i){if(!q||String(h.query||"").toLowerCase().indexOf(q)>-1)items.push({item:h,index:i})});historyVisibleItems=items.slice(0,20);historyActiveIndex=-1;if(!historyVisibleItems.length){closeHistorySuggestions();return false}var html="";historyVisibleItems.forEach(function(entry){var h=entry.item,ml=h.mode==="instant"?"即":(h.mode==="export"?"深":"批");html+='<div class="history-item" data-history-index="'+entry.index+'" onclick="insertHistory('+entry.index+')"><span class="query-text" title="'+escHtml(h.query)+'">['+ml+"] "+escHtml(h.query)+'</span><span class="history-actions"><button class="h-act del" onclick="event.stopPropagation();deleteHistory('+entry.index+')">删除</button></span></div>'});dd.innerHTML=html;dd.classList.add("show");fitHistoryDropdown();return true}
function closeHistorySuggestions(){var dd=document.getElementById("historyDropdown");if(dd){dd.classList.remove("show");dd.style.maxHeight="";dd.innerHTML=""}historyActiveIndex=-1;historyVisibleItems=[]}
function moveHistorySelection(step){if(!historyVisibleItems.length)return;historyActiveIndex=(historyActiveIndex+step+historyVisibleItems.length)%historyVisibleItems.length;document.querySelectorAll("#historyDropdown .history-item").forEach(function(el,i){el.classList.toggle("active",i===historyActiveIndex);if(i===historyActiveIndex)el.scrollIntoView({block:"nearest"})})}
function pickActiveHistory(){if(historyActiveIndex<0||!historyVisibleItems[historyActiveIndex])return false;insertHistory(historyVisibleItems[historyActiveIndex].index);return true}
function toggleHistory(){var dd=document.getElementById("historyDropdown");if(dd&&dd.classList.contains("show"))closeHistorySuggestions();else renderHistorySuggestions(true)}
function insertHistory(index){try{var history=getHistory();if(history[index]){document.getElementById("queryInput").value=history[index].query;switchMode(history[index].mode||"instant");closeHistorySuggestions();document.getElementById("queryInput").focus()}}catch(e){}}
function deleteHistory(index){try{var history=getHistory();history.splice(index,1);saveHistory(history);updateHistoryCount();renderHistorySuggestions()}catch(e){}}
document.addEventListener("click",function(e){if(!e.target.closest(".search-input-wrap"))closeHistorySuggestions();if(!e.target.closest(".settings-wrap"))document.getElementById("settingsPopup").classList.remove("show")});
function escHtml(str){var div=document.createElement("div");div.appendChild(document.createTextNode(str));return div.innerHTML}
</script>
</body>
</html>"""


def render_web_html() -> str:
    return (
        WEB_HTML_TEMPLATE.replace("__APP_VERSION__", APP_VERSION)
        .replace("__GITHUB_URL__", GITHUB_URL)
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
        placeholder_keys = {DEFAULT_CONFIG["key"], "your-api-key"}
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
        result = asdict(self)
        result.update(self._extra)
        for key in list(result.keys()):
            if key.startswith("_"):
                del result[key]
                continue
            if result[key] == "" and key not in self._extra:
                del result[key]
        return result


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


def _field_names(fields: str) -> list[str]:
    return [f.strip() for f in fields.split(",") if f.strip()]


def _append_missing_fields(fields: str, required_fields: list[str]) -> str:
    requested = set(_field_names(fields))
    missing = [f for f in required_fields if f not in requested]
    if missing:
        fields = fields + "," + ",".join(missing)
    return fields


def _ensure_fields_for_url(fields: str) -> str:
    """当请求包含 url 字段时，确保 host,ip,port,protocol 字段存在"""
    requested = set(_field_names(fields))
    if "url" in requested:
        fields = _append_missing_fields(fields, ["host", "ip", "port", "protocol"])
    return fields


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
            return template.replace("{base_url}", base_url.rstrip("/")).replace("{key}", key)
    return ""


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
        api_url = f"{self.base_url}/api/v1/info/my?key={self.key}"
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
    ) -> SearchStats:
        """
        执行 FOFA 查询

        Args:
            query: FOFA 查询语句
            size: 返回数量（最大 10000）
            page: 页码（默认为1）
            fields: 返回字段，默认为 DEFAULT_FIELDS
            full: 是否搜索全部数据（不止一年）

        Returns:
            SearchStats 对象，包含结果列表、总匹配数和独立 IP 数
        """
        if fields is None:
            fields = DEFAULT_FIELDS
        else:
            fields = _ensure_fields_for_url(fields)

        qbase64 = base64.b64encode(query.encode()).decode()
        url = (
            f"{self.base_url}/api/v1/search/all"
            f"?key={self.key}"
            f"&qbase64={qbase64}&size={size}&page={page}&fields={fields}"
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
                time.sleep(_retry_sleep_seconds(e, attempt))
                continue

            if data.get("error"):
                errmsg = data.get("errmsg", "未知错误")
                api_error = FofaAPIError(f"API 错误: {errmsg}")
                if attempt < max_retries and _is_retryable_api_error(errmsg):
                    if retry_callback:
                        retry_callback(attempt, max_retries, api_error)
                    time.sleep(_retry_sleep_seconds(api_error, attempt))
                    continue
                raise api_error

            break

        results = []
        fields_list = (
            [f.strip() for f in fields.split(",")]
            if fields
            else [
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
        )
        known_fields = {
            "host",
            "ip",
            "port",
            "protocol",
            "domain",
            "title",
            "server",
            "country",
            "city",
            "lastupdatetime",
            "asn",
            "org",
            "os",
            "icp",
            "jarm",
            "header",
            "banner",
            "cert",
            "product",
            "product_category",
            "version",
            "cname",
            "latitude",
            "longitude",
            "region",
            "country_name",
            "base_protocol",
            "link",
        }
        unique_ips = set()
        for item in data.get("results", []):
            if isinstance(item, str):
                item = [item]
            result = FofaResult()
            result._extra = {}
            for i, field in enumerate(fields_list):
                value = item[i] if len(item) > i else ""
                if field in known_fields:
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

        Returns:
            SearchStats 对象
        """
        if fields is None:
            fields = DEFAULT_FIELDS
        else:
            fields = _ensure_fields_for_url(fields)
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
        )
        total_quota_used += 1
        total_estimated = count_stats.total

        time.sleep(current_rate_limit)

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

                time.sleep(current_rate_limit)

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
            if hasattr(r, f):
                key_tuple.append(getattr(r, f, "") or "")
            elif f == "host":
                key_tuple.append(r.host or "")
            elif f == "ip":
                key_tuple.append(r.ip or "")
            elif f == "port":
                key_tuple.append(r.port or "")
            elif f == "domain":
                key_tuple.append(r.domain or "")
            elif f == "protocol":
                key_tuple.append(r.protocol or "")
            elif f == "url":
                key_tuple.append(build_url(r) or "")
        key = tuple(key_tuple)
        if key not in seen:
            seen.add(key)
            unique_results.append(r)
    return unique_results


class Exporter:
    """导出管理器"""

    BASE_FIELDS = [
        "host",
        "ip",
        "port",
        "protocol",
        "domain",
        "title",
        "server",
        "country",
        "city",
        "lastupdatetime",
        "asn",
        "org",
        "os",
        "icp",
        "jarm",
        "header",
        "banner",
        "cert",
        "product",
        "product_category",
        "version",
        "cname",
        "latitude",
        "longitude",
        "region",
        "country_name",
        "base_protocol",
        "link",
    ]

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
            fieldnames = self.BASE_FIELDS.copy()

        all_keys = set()
        data = self._prepare_dict_data()
        for d in data:
            all_keys.update(d.keys())

        dynamic_extra = [
            f
            for f in all_keys
            if f not in self.BASE_FIELDS
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
  %(prog)s -c                                      # 快速检测账户状态
        """,
    )
    parser.add_argument("query", nargs="?", help="FOFA 查询语句，如: domain=baidu.com")
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
_EXPORT_TASK_TTL = 1800  # 30 分钟后自动清理已完成任务


def _cleanup_export_tasks():
    """清理过期的导出任务及其临时文件，防止内存和磁盘泄漏"""
    now = time.time()
    expired = []
    with _export_lock:
        for tid, task in list(_export_tasks.items()):
            if task.status in ("done", "error") and (now - task.created_at) > _EXPORT_TASK_TTL:
                expired.append((tid, dict(task.output_files)))
                del _export_tasks[tid]
    for tid, files in expired:
        for filepath in files.values():
            try:
                Path(filepath).unlink(missing_ok=True)
            except Exception:
                pass


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
    results: list = field(default_factory=list)
    output_files: dict = field(default_factory=dict)
    error: str = ""
    partial: bool = False
    partial_error: str = ""
    created_at: float = field(default_factory=time.time)
    cancelled: bool = False
    discard: bool = False


def _redact_sensitive(text: str, *secrets: str) -> str:
    safe_text = str(text)
    for secret in secrets:
        if secret:
            safe_text = safe_text.replace(secret, "***")
    safe_text = re.sub(r"(key=)[^&\s]+", r"\1***", safe_text)
    return safe_text


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


class FofaWebHandler(http.server.BaseHTTPRequestHandler):
    """FOFA Web UI 请求处理器"""

    client: Optional[FofaClient] = None
    config_manager: Optional[ConfigManager] = None

    def log_message(self, format, *args):
        sys.stderr.write(f"[web] {format % args}\n")

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
        length = int(self.headers.get("Content-Length", 0))
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
            with _export_lock:
                _export_tasks[task_id] = task

            thread = threading.Thread(
                target=self._run_export_task,
                args=(task_id, query, fields, fill_percent, max_size, full),
                daemon=True,
            )
            thread.start()

            self._send_json({"success": True, "task_id": task_id})
        except Exception as e:
            self._send_error(e)

    def _run_export_task(self, task_id, query, fields, fill_percent, max_size, full):
        client = self._current_client()
        if not client:
            with _export_lock:
                task = _export_tasks.get(task_id)
                if task:
                    task.status = "error"
                    task.error = "未配置有效的 FOFA API Key"
            return
        try:
            stats = client.search_all_efficient(
                query,
                max_size=max_size,
                fields=fields,
                fill_percent=fill_percent,
                full=full,
                progress_callback=_create_web_progress_callback(task_id, max_size),
            )

            cancelled = False
            discard = False
            with _export_lock:
                task = _export_tasks.get(task_id)
                if task:
                    cancelled = task.cancelled
                    discard = task.discard

            if discard:
                with _export_lock:
                    task = _export_tasks.get(task_id)
                    if task:
                        task.status = "error"
                        task.error = "Cancelled by user"
                return

            if not stats.results and cancelled:
                with _export_lock:
                    task = _export_tasks.get(task_id)
                    if task:
                        task.status = "error"
                        task.error = "Cancelled by user"
                return

            output_dir = Path(tempfile.gettempdir()) / "fofa_web_exports"
            output_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            exporter = Exporter(stats.results, fields=fields)
            output_files = {}

            csv_path = unique_path(output_dir / f"fofa_export_{timestamp}.csv")
            exporter.export_csv(csv_path)
            output_files["csv"] = str(csv_path)

            json_path = unique_path(output_dir / f"fofa_export_{timestamp}.json")
            exporter.export_json(json_path)
            output_files["json"] = str(json_path)

            txt_path = unique_path(output_dir / f"fofa_export_{timestamp}.txt")
            exporter.export_txt(txt_path)
            output_files["txt"] = str(txt_path)

            with _export_lock:
                task = _export_tasks.get(task_id)
                if task:
                    task.status = "done"
                    task.progress = 1.0
                    task.partial = cancelled or stats.partial
                    task.partial_error = (
                        "Cancelled by user"
                        if cancelled
                        else stats.partial_error
                    )
                    task.message = (
                        "已取消，已保留部分结果"
                        if cancelled
                        else (
                            "部分导出完成，已保留可用结果"
                            if stats.partial
                            else "导出文件已生成"
                        )
                    )
                    task.fetched = len(stats.results)
                    task.total_estimated = stats.total
                    task.total_quota_used = stats.total_quota_used
                    task.unique_ips = stats.unique_ips
                    task.output_files = output_files
        except KeyboardInterrupt:
            with _export_lock:
                task = _export_tasks.get(task_id)
                if task:
                    task.status = "error"
                    task.error = "Cancelled by user"
        except Exception as e:
            with _export_lock:
                task = _export_tasks.get(task_id)
                if task:
                    task.status = "error"
                    task.error = self._safe_error(e)

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

        if not task or task.status != "done":
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
            with _export_lock:
                _export_tasks[task_id] = task

            thread = threading.Thread(
                target=self._run_batch_task,
                args=(task_id, queries, fields, fill_percent),
                daemon=True,
            )
            thread.start()

            self._send_json({"success": True, "task_id": task_id})
        except Exception as e:
            self._send_error(e)

    def _run_batch_task(self, task_id, queries, fields, fill_percent):
        client = self._current_client()
        if not client:
            with _export_lock:
                task = _export_tasks.get(task_id)
                if task:
                    task.status = "error"
                    task.error = "未配置有效的 FOFA API Key"
            return
        try:
            all_results = []
            total_queries = len(queries)
            failed_count = 0

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
                        task.current_target_count = 0
                        task.message = f"Target {batch_idx + 1}/{total_queries}"

                stats = None
                try:
                    stats = client.search_all_efficient(
                        query,
                        max_size=0,
                        fields=fields,
                        fill_percent=fill_percent,
                        progress_callback=_create_web_batch_progress_callback(
                            task_id, batch_idx, total_queries, base_count
                        ),
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
                    time.sleep(2)

            output_dir = Path(tempfile.gettempdir()) / "fofa_web_exports"
            output_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            exporter = Exporter(all_results, fields=fields)
            output_files = {}

            csv_path = unique_path(output_dir / f"fofa_batch_{timestamp}.csv")
            exporter.export_csv(csv_path)
            output_files["csv"] = str(csv_path)

            json_path = unique_path(output_dir / f"fofa_batch_{timestamp}.json")
            exporter.export_json(json_path)
            output_files["json"] = str(json_path)

            txt_path = unique_path(output_dir / f"fofa_batch_{timestamp}.txt")
            exporter.export_txt(txt_path)
            output_files["txt"] = str(txt_path)

            with _export_lock:
                task = _export_tasks.get(task_id)
                if task:
                    task.status = "done"
                    task.progress = 1.0
                    task.fetched = len(all_results)
                    task.output_files = output_files
                    task.failed_count = failed_count
                    if failed_count:
                        task.message = f"Partial: {failed_count}/{total_queries} failed"
        except KeyboardInterrupt:
            with _export_lock:
                task = _export_tasks.get(task_id)
                if task and task.discard:
                    task.status = "error"
                    task.error = "Cancelled by user"
                    return
            if all_results:
                output_dir = Path(tempfile.gettempdir()) / "fofa_web_exports"
                output_dir.mkdir(exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                exporter = Exporter(all_results, fields=fields)
                output_files = {}
                csv_path = unique_path(output_dir / f"fofa_batch_{timestamp}.csv")
                exporter.export_csv(csv_path)
                output_files["csv"] = str(csv_path)
                json_path = unique_path(output_dir / f"fofa_batch_{timestamp}.json")
                exporter.export_json(json_path)
                output_files["json"] = str(json_path)
                txt_path = unique_path(output_dir / f"fofa_batch_{timestamp}.txt")
                exporter.export_txt(txt_path)
                output_files["txt"] = str(txt_path)
                with _export_lock:
                    task = _export_tasks.get(task_id)
                    if task:
                        task.status = "done"
                        task.progress = 1.0
                        task.partial = True
                        task.partial_error = "Cancelled by user"
                        task.message = "已取消，已保留部分结果"
                        task.fetched = len(all_results)
                        task.output_files = output_files
            else:
                with _export_lock:
                    task = _export_tasks.get(task_id)
                    if task:
                        task.status = "error"
                        task.error = "Cancelled by user"
        except Exception as e:
            with _export_lock:
                task = _export_tasks.get(task_id)
                if task:
                    task.status = "error"
                    task.error = self._safe_error(e)

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
    start_port: int = DEFAULT_WEB_PORT, max_attempts: int = 20
) -> int:
    for offset in range(max_attempts):
        port = start_port + offset
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    raise OSError(
        f"未找到可用端口（尝试 {start_port}-{start_port + max_attempts - 1}）"
    )


class FofaWebServer:
    """FOFA Web UI 服务器"""

    def __init__(
        self,
        client: Optional[FofaClient],
        config_manager: Optional[ConfigManager] = None,
        port: int = 0,
    ):
        self.client = client
        self.config_manager = config_manager
        self.port = port or _find_available_port()
        self.httpd = None

    def start(self):
        FofaWebHandler.client = self.client
        FofaWebHandler.config_manager = self.config_manager

        class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
            allow_reuse_address = True
            daemon_threads = True

        self.httpd = ThreadingServer(("127.0.0.1", self.port), FofaWebHandler)

        print(f"\n{GREEN}[*] Web UI 已启动: {CYAN}http://127.0.0.1:{self.port}{RESET}")
        print(f"[*] 按 {RED}Ctrl+C{RESET} 停止服务器\n")

        try:
            webbrowser.open(f"http://127.0.0.1:{self.port}")
        except Exception:
            pass

        try:
            self.httpd.serve_forever()
        except KeyboardInterrupt:
            print(f"\n[*] 服务器已停止")
            self.httpd.shutdown()


# ============ 主函数 ============


def main():
    # 检查是否显示帮助
    if "-h" in sys.argv or "--help" in sys.argv:
        build_parser().print_help()
        sys.exit(0)

    parser = build_parser()
    args = parser.parse_args()
    web_mode = args.web or (not args.query and not args.batch_file and not args.check)

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
        server = FofaWebServer(client, config_manager=config_manager, port=args.port)
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

    for idx, (query, line_no) in enumerate(queries, 1):
        query = query.strip()
        if not query:
            continue

        print(f"\n{CYAN}[{idx}/{total_queries}] 查询:{RESET} {query}")

        try:
            is_max, limit_value = parse_limit_value(args.limit)

            query_fields = _merge_dedup_fields(args.fields, args.dedup)

            if limit_value > 10000 or is_max:
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
