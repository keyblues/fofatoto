#!/usr/bin/env python3
"""
FOFA 查询工具 - 单文件
"""

from __future__ import annotations

import argparse
import json
import csv
import ipaddress
import os
import sys
import base64
import time
import uuid
import socket
import tempfile
import threading
import webbrowser
import http.server
import socketserver
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional, Callable
from urllib.parse import urlparse, parse_qs


# ============ Banner ============

BANNER = r"""
  _____ ___  _____ _      _____ ___ _____ ___  
 |  ___/ _ \|  ___/ \    |_   _/ _ \_   _/ _ \ 
 | |_ | | | | |_ / _ \     | || | | || || | | |
 |  _|| |_| |  _/ ___ \    | || |_| || || |_| |
 |_|   \___/|_|/_/   \_\   |_| \___/ |_| \___/ 
                                               
				FOFA Query Tool v1.2.0
        			https://github.com/keyblues/fofatoto
"""

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


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
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--text);font-size:13px;line-height:1.5;min-height:100vh}
.header{background:var(--primary-dark);color:#fff;padding:0 28px;height:52px;display:flex;align-items:center;justify-content:space-between;font-size:13px;border-bottom:2px solid var(--primary)}
.header .logo{font-weight:700;font-size:17px;letter-spacing:1.5px;color:#e2e8f0}
.header .account{display:flex;gap:20px;align-items:center;font-size:12px;color:#a0aec0}
.header .account strong{color:#e2e8f0}
.vip-badge{padding:2px 8px;border-radius:2px;font-size:11px;font-weight:600}
.vip-badge.active{background:var(--success);color:#fff}
.vip-badge.inactive{background:var(--danger);color:#fff}
.container{max-width:1400px;margin:0 auto;padding:16px 24px}
.mode-tabs{display:flex;border-bottom:2px solid var(--border);margin-bottom:16px;background:var(--card-bg);border-radius:2px 2px 0 0}
.mode-tab{padding:10px 20px;font-size:13px;font-weight:600;color:var(--text-secondary);cursor:pointer;border:none;background:none;border-bottom:2px solid transparent;margin-bottom:-2px;transition:all 0.15s ease}
.mode-tab:hover{color:var(--primary)}
.mode-tab.active{color:var(--primary);border-bottom-color:var(--accent)}
.card{background:var(--card-bg);border:1px solid var(--border);border-left:3px solid var(--accent-border);border-radius:2px;padding:16px;margin-bottom:16px}
.search-row{display:flex;gap:8px}
.search-row input[type=text]{flex:1;padding:8px 12px;font-size:13px;font-family:"SF Mono","Fira Code",Consolas,Monaco,monospace;border:1px solid var(--border);border-radius:2px;background:#fafbfc;color:var(--text);outline:none;transition:all 0.15s ease}
.search-row input[type=text]:focus{border-color:var(--accent);background:#fff}
.btn{padding:8px 20px;font-size:13px;font-weight:600;border:1px solid transparent;border-radius:2px;cursor:pointer;white-space:nowrap;transition:all 0.15s ease}
.btn-primary{background:var(--accent);color:#fff;border-color:var(--accent)}
.btn-primary:hover{background:var(--accent-hover)}
.btn-secondary{background:var(--card-bg);color:var(--text);border-color:var(--border)}
.btn-secondary:hover{background:#f1f5f9}
.btn-danger{background:var(--danger);color:#fff;border-color:var(--danger)}
.btn-danger:hover{background:#b91c1c}
.field-row{display:flex;gap:8px;margin-top:10px;position:relative}
.field-row>label{font-size:12px;color:var(--text-secondary);font-weight:600;padding-top:5px;min-width:40px;flex-shrink:0}
.field-control{flex:1;display:flex;flex-wrap:wrap;gap:4px;align-items:center;min-height:28px}
.chip{display:inline-flex;align-items:center;gap:3px;background:var(--chip-bg);border:1px solid var(--chip-border);border-radius:2px;padding:2px 6px;font-size:11px;font-family:"SF Mono","Fira Code",Consolas,Monaco,monospace;cursor:default;transition:all 0.15s ease}
.chip:hover{border-color:var(--accent)}
.chip-label{line-height:1.4}
.chip-remove{cursor:pointer;color:var(--text-secondary);font-size:13px;line-height:1;width:14px;height:14px;display:inline-flex;align-items:center;justify-content:center;border-radius:1px;transition:all 0.15s ease}
.chip-remove:hover{color:var(--danger);background:rgba(220,38,38,0.08)}
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
.options-row select:focus,.options-row input[type=number]:focus{border-color:var(--accent);background:#fff;outline:none}
.options-row input[type=number]{width:80px}
.options-row input[type=text]{padding:4px 8px;font-size:12px;border:1px solid var(--border);border-radius:2px;background:#fafbfc;margin-left:4px;transition:all 0.15s ease}
.options-row input[type=text]:focus{border-color:var(--accent);background:#fff;outline:none}
.batch-textarea{width:100%;min-height:160px;margin-top:12px;padding:10px;font-size:12px;font-family:"SF Mono","Fira Code",Consolas,Monaco,monospace;border:1px solid var(--border);border-radius:2px;background:#fafbfc;resize:vertical;outline:none;transition:all 0.15s ease}
.batch-textarea:focus{border-color:var(--accent);background:#fff}
.history-area{position:relative;margin-bottom:16px}
.history-toggle{font-size:12px;color:var(--text-secondary);cursor:pointer;padding:4px 0;user-select:none;transition:all 0.15s ease}
.history-toggle:hover{color:var(--accent)}
.history-dropdown{display:none;position:absolute;top:100%;left:0;right:0;background:var(--card-bg);border:1px solid var(--border);border-radius:2px;z-index:100;max-height:240px;overflow-y:auto;box-shadow:0 4px 12px rgba(0,0,0,0.08)}
.history-dropdown.show{display:block}
.history-item{display:flex;justify-content:space-between;align-items:center;padding:6px 12px;font-size:12px;font-family:"SF Mono","Fira Code",Consolas,Monaco,monospace;border-bottom:1px solid var(--border);cursor:pointer}
.history-item:last-child{border-bottom:none}
.history-item:hover{background:var(--table-stripe)}
.history-item .query-text{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.history-actions{display:flex;gap:4px;margin-left:12px}
.h-act{font-size:11px;color:var(--text-secondary);cursor:pointer;padding:2px 6px;border:1px solid var(--border);border-radius:2px;background:var(--card-bg);transition:all 0.15s ease}
.h-act:hover{background:var(--table-header);color:var(--text)}
.h-act.del:hover{color:var(--danger);border-color:var(--danger)}
.stats-bar{display:flex;gap:28px;padding:10px 16px;background:var(--table-header);border:1px solid var(--border);border-radius:2px;margin-bottom:12px;font-size:12px;color:var(--text-secondary)}
.stat-item{display:inline-flex;align-items:center;gap:6px}
.stat-dot{display:inline-block;width:7px;height:7px;border-radius:50%;flex-shrink:0}
.stat-value{font-weight:700;color:var(--text)}
.table-container{background:var(--card-bg);border:1px solid var(--border);border-radius:2px;overflow:auto;max-height:60vh}
table{width:100%;border-collapse:collapse;font-size:12px}
thead{position:sticky;top:0;z-index:1}
th{background:var(--table-header);padding:7px 12px;text-align:left;font-weight:600;font-size:11px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:.5px;border-bottom:2px solid var(--border);white-space:nowrap;cursor:pointer;user-select:none;transition:all 0.15s ease}
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
.message{padding:10px 14px;border-radius:2px;font-size:12px;margin-bottom:12px}
.message.error{background:#fef2f2;border:1px solid #fecaca;color:var(--danger)}
.message.info{background:#eff6ff;border:1px solid #bfdbfe;color:var(--primary-light)}
.empty-state{text-align:center;padding:40px 20px;color:var(--text-secondary);font-size:13px}
.spinner{display:inline-block;width:14px;height:14px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .6s linear infinite;vertical-align:middle;margin-right:6px}
@keyframes spin{to{transform:rotate(360deg)}}
.footer{text-align:center;padding:16px;font-size:11px;color:var(--text-secondary);border-top:1px solid var(--border);margin-top:24px}
</style>
</head>
<body>
<div class="header">
<div class="logo">FOFATOTO</div>
<div class="account" id="accountInfo">加载中...</div>
</div>
<div class="container">
<div class="mode-tabs">
<button class="mode-tab active" data-mode="instant">即时预览</button>
<button class="mode-tab" data-mode="export">深度导出</button>
<button class="mode-tab" data-mode="batch">批量模式</button>
</div>
<div class="card">
<div class="search-row">
<input type="text" id="queryInput" placeholder="FOFA 查询语法，如 domain=baidu.com" autofocus>
<button class="btn btn-primary" id="searchBtn" onclick="executeSearch()">搜索</button>
</div>
<div class="field-row">
<label>字段</label>
<div class="field-control" id="fieldControl"></div>
<div class="field-panel" id="fieldPanel">
<div class="fp-search-wrap"><input type="text" class="fp-search" id="fpSearch" placeholder="搜索字段..." spellcheck="false"></div>
<div class="fp-body" id="fpBody"></div>
</div>
</div>
<div class="options-row" id="instantOptions">
<label>数量:<select id="instantSize"><option value="100">100</option><option value="300">300</option><option value="500">500</option><option value="1000">1000</option></select></label>
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
<div class="history-area">
<div class="history-toggle" onclick="toggleHistory()">历史记录 (<span id="historyCount">0</span>) &#9662;</div>
<div class="history-dropdown" id="historyDropdown"></div>
</div>
<div id="resultsArea" style="display:none">
<div class="stats-bar" id="statsBar"></div>
<div class="table-container"><table id="resultsTable"><thead></thead><tbody></tbody></table></div>
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
<div class="footer">FOFA Query Tool v1.2.0</div>
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
var selectedFields=["host","ip","port","protocol","domain","title","server","country","city","lastupdatetime","url"];
var currentMode="instant",currentResults=[],currentColumns=[],exportTaskId=null,exportPollTimer=null,sortColumn=null,sortAsc=true;
function initFieldSelector(){renderChips();renderFieldPanel();var ctrl=document.getElementById("fieldControl");var trig=document.createElement("div");trig.className="field-trigger";trig.id="fieldTrigger";trig.textContent="+";trig.addEventListener("click",function(e){e.stopPropagation();toggleFieldPanel()});ctrl.appendChild(trig);document.getElementById("fpSearch").addEventListener("input",filterFields);document.addEventListener("click",function(e){var p=document.getElementById("fieldPanel");if(p.classList.contains("open")&&!e.target.closest(".field-row"))p.classList.remove("open")});document.addEventListener("keydown",function(e){if(e.key==="Escape")document.getElementById("fieldPanel").classList.remove("open")})}
function renderChips(){var c=document.getElementById("fieldControl");c.innerHTML="";selectedFields.forEach(function(f){var ch=document.createElement("span");ch.className="chip";ch.innerHTML='<span class="chip-label">'+escHtml(f)+'</span><span class="chip-remove">&times;</span>';ch.querySelector(".chip-remove").addEventListener("click",function(e){e.stopPropagation();removeField(f)});c.appendChild(ch)})}
function renderFieldPanel(){var body=document.getElementById("fpBody");body.innerHTML="";fieldCategories.forEach(function(cat){var div=document.createElement("div");div.className="fp-category";var hdr=document.createElement("div");hdr.className="fp-cat-name";hdr.textContent=cat.name;div.appendChild(hdr);var fd=document.createElement("div");fd.className="fp-cat-fields";cat.fields.forEach(function(f){var btn=document.createElement("button");btn.className="fp-field"+(selectedFields.indexOf(f)>-1?" selected":"");btn.dataset.field=f;btn.textContent=f;btn.addEventListener("click",function(){toggleField(f)});fd.appendChild(btn)});div.appendChild(fd);body.appendChild(div)})}
function toggleFieldPanel(){var p=document.getElementById("fieldPanel");p.classList.toggle("open");if(p.classList.contains("open")){document.getElementById("fpSearch").value="";filterFields();document.getElementById("fpSearch").focus()}}
function toggleField(f){var i=selectedFields.indexOf(f);if(i>-1)selectedFields.splice(i,1);else selectedFields.push(f);renderChips();renderFieldPanel()}
function removeField(f){var i=selectedFields.indexOf(f);if(i>-1){selectedFields.splice(i,1);renderChips();renderFieldPanel()}}
function filterFields(){var q=document.getElementById("fpSearch").value.trim().toLowerCase();document.querySelectorAll("#fpBody .fp-category").forEach(function(cat){var v=0;cat.querySelectorAll(".fp-field").forEach(function(b){var m=!q||b.dataset.field.indexOf(q)>-1;b.classList.toggle("hidden",!m);if(m)v++});cat.style.display=v>0?"":"none"})}
function getSelectedFields(){return selectedFields.join(",")}
document.addEventListener("DOMContentLoaded",function(){initFieldSelector();loadAccountInfo();setupModeTabs();setupSearchShortcut();updateHistoryCount()});
function setupModeTabs(){document.querySelectorAll(".mode-tab").forEach(function(t){t.addEventListener("click",function(){switchMode(this.dataset.mode)})})}
function switchMode(mode){currentMode=mode;document.querySelectorAll(".mode-tab").forEach(function(t){t.classList.toggle("active",t.dataset.mode===mode)});var btn=document.getElementById("searchBtn");document.getElementById("instantOptions").style.display=mode==="instant"?"":"none";document.getElementById("exportOptions").style.display=mode==="export"?"":"none";document.getElementById("batchOptions").style.display=mode==="batch"?"":"none";if(mode==="instant"){btn.textContent="搜索";btn.className="btn btn-primary"}else if(mode==="export"){btn.textContent="导出";btn.className="btn btn-primary"}else{btn.textContent="批量查询";btn.className="btn btn-primary"}clearResults();document.getElementById("queryInput").focus()}
function setupSearchShortcut(){document.getElementById("queryInput").addEventListener("keydown",function(e){if(e.key==="Enter")executeSearch()})}
function loadAccountInfo(){fetch("/api/info").then(function(r){return r.json()}).then(function(data){if(data.success){var d=data.data,vipClass=d.isvip?"active":"inactive",vipText=d.isvip?"VIP "+(d.vip_level||""):"未激活";var healthDot=d.server_ok?'<span style="color:#16a34a;font-size:16px">&#9679;</span>':'<span style="color:#dc2626;font-size:16px">&#9679;</span>';document.getElementById("accountInfo").innerHTML='<span class="vip-badge '+vipClass+'">'+vipText+'</span> 服务器 '+healthDot+' | 剩余查询: <strong>'+(d.remain_api_query||"N/A")+"</strong> | 过期: "+(d.expiration||"N/A")}}).catch(function(){document.getElementById("accountInfo").textContent="账户信息不可用"})}
function executeSearch(){var q=document.getElementById("queryInput").value.trim();if(!q)return;addToHistory(q);if(currentMode==="instant")doInstantSearch(q);else if(currentMode==="export")doDeepExport(q);else doBatchSearch(q)}
function doInstantSearch(query){var size=parseInt(document.getElementById("instantSize").value)||100,fields=getSelectedFields();clearResults();showMessage("info","搜索中...");fetch("/api/search",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query:query,size:size,fields:fields,full:false})}).then(function(r){return r.json()}).then(function(data){clearMessage();if(data.success){currentResults=data.data.results||[];currentColumns=data.data.columns||[];renderResults(data.data)}else showMessage("error",data.error||"搜索失败")}).catch(function(e){showMessage("error","网络错误: "+e.message)})}
function doDeepExport(query){var fill=parseFloat(document.getElementById("exportFill").value)||0.8,maxSize=parseInt(document.getElementById("exportMaxSize").value)||0,fields=getSelectedFields(),full=document.getElementById("exportFull").checked;showOverlay("深度导出进行中");fetch("/api/export",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query:query,fill_percent:fill,max_size:maxSize,fields:fields,full:full})}).then(function(r){return r.json()}).then(function(data){if(data.success){exportTaskId=data.task_id;pollProgress()}else{hideOverlay();showMessage("error",data.error||"导出失败")}}).catch(function(e){hideOverlay();showMessage("error","网络错误: "+e.message)})}
function doBatchSearch(baseQuery){var ph=document.getElementById("batchPlaceholder").value||"{}",targets=document.getElementById("batchTargets").value.trim(),fill=parseFloat(document.getElementById("batchFill").value)||0.8,fields=getSelectedFields();if(!targets){showMessage("error","请输入批量目标");return}if(baseQuery.indexOf(ph)===-1){showMessage("error","基础查询必须包含占位符: "+ph);return}var targetLines=targets.replace(/\r/g,"").split("\n").filter(function(l){return l.trim()});showOverlay("批量导出进行中");fetch("/api/batch",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({base_query:baseQuery,targets:targetLines,placeholder:ph,fill_percent:fill,fields:fields})}).then(function(r){return r.json()}).then(function(data){if(data.success){exportTaskId=data.task_id;pollProgress()}else{hideOverlay();showMessage("error",data.error||"批量导出失败")}}).catch(function(e){hideOverlay();showMessage("error","网络错误: "+e.message)})}
function pollProgress(){if(!exportTaskId)return;exportPollTimer=setInterval(function(){fetch("/api/progress?task_id="+exportTaskId).then(function(r){return r.json()}).then(function(data){if(!data.success)return;var d=data.data,pct=(d.progress*100).toFixed(1);document.getElementById("progressFill").style.width=pct+"%";document.getElementById("progressDetails").innerHTML="进度: <span>"+pct+"%</span><br>已获取: <span>"+(d.fetched||0).toLocaleString()+"</span> / ~"+(d.total_estimated||0).toLocaleString()+"<br>独立IP: <span>"+(d.unique_ips||0).toLocaleString()+"</span> | 配额: <span>"+(d.total_quota_used||0).toLocaleString()+"</span>";if(d.status==="done"){clearInterval(exportPollTimer);exportPollTimer=null;document.getElementById("progressTitle").textContent="导出完成";document.getElementById("progressActions").innerHTML='<button class="btn btn-primary" onclick="downloadExport(\'csv\')">下载 CSV</button><button class="btn btn-secondary" onclick="downloadExport(\'json\')">下载 JSON</button><button class="btn btn-secondary" onclick="downloadExport(\'txt\')">下载 TXT</button><button class="btn btn-secondary" onclick="hideOverlay()">关闭</button>'}else if(d.status==="error"){clearInterval(exportPollTimer);exportPollTimer=null;document.getElementById("progressTitle").textContent="导出失败";document.getElementById("progressDetails").innerHTML='<span style="color:#dc2626">'+(d.error||"未知错误")+"</span>";document.getElementById("progressActions").innerHTML='<button class="btn btn-secondary" onclick="hideOverlay()">关闭</button>'}})},800)}
function cancelExport(){if(exportTaskId){fetch("/api/progress/cancel?task_id="+exportTaskId,{method:"POST"}).then(function(){if(exportPollTimer)clearInterval(exportPollTimer);hideOverlay()})}}
function downloadExport(format){if(exportTaskId)window.open("/api/export/download?task_id="+exportTaskId+"&format="+format,"_blank")}
function showOverlay(title){document.getElementById("progressTitle").textContent=title;document.getElementById("progressFill").style.width="0%";document.getElementById("progressDetails").innerHTML="初始化中...";document.getElementById("progressActions").innerHTML='<button class="btn btn-secondary" onclick="cancelExport()">取消</button>';document.getElementById("progressOverlay").classList.add("show")}
function hideOverlay(){document.getElementById("progressOverlay").classList.remove("show")}
function renderResults(data){var area=document.getElementById("resultsArea");area.style.display="block";document.getElementById("statsBar").innerHTML='<span class="stat-item"><span class="stat-dot" style="background:var(--accent)"></span>总计: <span class="stat-value">'+(data.total||0).toLocaleString()+'</span></span><span class="stat-item"><span class="stat-dot" style="background:var(--success)"></span>独立IP: <span class="stat-value">'+(data.unique_ips||0).toLocaleString()+'</span></span><span class="stat-item"><span class="stat-dot" style="background:var(--warning)"></span>结果: <span class="stat-value">'+(data.results?data.results.length:0).toLocaleString()+'</span></span>';var cols=data.columns||[];if(cols.length===0&&data.results&&data.results.length>0)cols=Object.keys(data.results[0]);currentColumns=cols;var thead="";cols.forEach(function(col){thead+="<th onclick=\"sortBy('"+escHtml(col)+"')\">"+escHtml(col)+"</th>"});document.querySelector("#resultsTable thead").innerHTML="<tr>"+thead+"</tr>";var tbody="";(data.results||[]).forEach(function(row){tbody+="<tr>";cols.forEach(function(col){var val=row[col]!==undefined?row[col]:"",cls=(col==="ip"||col==="port"||col==="host")?" mono":"";if((col==="host"||col==="url")&&val){var url=val.indexOf("http")===0?val:"http://"+val;tbody+='<td class="'+cls+'"><a href="'+escHtml(url)+'" target="_blank" rel="noopener">'+escHtml(val)+"</a></td>"}else tbody+='<td class="'+cls+'" title="'+escHtml(val)+'">'+escHtml(val)+"</td>"});tbody+="</tr>"});document.querySelector("#resultsTable tbody").innerHTML=tbody}
function sortBy(col){if(sortColumn===col){sortAsc=!sortAsc}else{sortColumn=col;sortAsc=true}currentResults.sort(function(a,b){var va=a[col]||"",vb=b[col]||"";if(va<vb)return sortAsc?-1:1;if(va>vb)return sortAsc?1:-1;return 0});renderResults({results:currentResults,columns:currentColumns,total:currentResults.length,unique_ips:0})}
function clearResults(){document.getElementById("resultsArea").style.display="none";document.querySelector("#resultsTable thead").innerHTML="";document.querySelector("#resultsTable tbody").innerHTML="";currentResults=[];currentColumns=[];sortColumn=null}
function showMessage(type,text){document.getElementById("messageArea").innerHTML='<div class="message '+type+'">'+escHtml(text)+"</div>"}
function clearMessage(){document.getElementById("messageArea").innerHTML=""}
function addToHistory(query){try{var history=JSON.parse(localStorage.getItem("fofa_query_history")||"[]");history=history.filter(function(h){return h.query!==query});history.unshift({query:query,mode:currentMode,time:Date.now()});if(history.length>50)history=history.slice(0,50);localStorage.setItem("fofa_query_history",JSON.stringify(history));updateHistoryCount()}catch(e){}}
function updateHistoryCount(){try{var history=JSON.parse(localStorage.getItem("fofa_query_history")||"[]");document.getElementById("historyCount").textContent=history.length}catch(e){document.getElementById("historyCount").textContent="0"}}
function toggleHistory(){var dd=document.getElementById("historyDropdown");if(dd.classList.contains("show")){dd.classList.remove("show");return}try{var history=JSON.parse(localStorage.getItem("fofa_query_history")||"[]"),html="";history.forEach(function(h,i){var ml=h.mode==="instant"?"即":(h.mode==="export"?"深":"批");html+='<div class="history-item"><span class="query-text" title="'+escHtml(h.query)+'">['+ml+"] "+escHtml(h.query)+'</span><span class="history-actions"><button class="h-act" onclick="insertHistory('+i+')">插入</button><button class="h-act del" onclick="deleteHistory('+i+')">删除</button></span></div>'});if(!html)html='<div class="history-item" style="color:#94a3b8">无历史记录</div>';dd.innerHTML=html;dd.classList.add("show")}catch(e){}}
function insertHistory(index){try{var history=JSON.parse(localStorage.getItem("fofa_query_history")||"[]");if(history[index]){document.getElementById("queryInput").value=history[index].query;switchMode(history[index].mode||"instant");document.getElementById("historyDropdown").classList.remove("show");document.getElementById("queryInput").focus()}}catch(e){}}
function deleteHistory(index){try{var history=JSON.parse(localStorage.getItem("fofa_query_history")||"[]");history.splice(index,1);localStorage.setItem("fofa_query_history",JSON.stringify(history));updateHistoryCount();toggleHistory();toggleHistory()}catch(e){}}
document.addEventListener("click",function(e){if(!e.target.closest(".history-area"))document.getElementById("historyDropdown").classList.remove("show")});
function escHtml(str){var div=document.createElement("div");div.appendChild(document.createTextNode(str));return div.innerHTML}
</script>
</body>
</html>"""


# ============ 配置相关 ============

class ConfigManager:
    """配置管理器"""
    def __init__(self):
        self.config_dir = self._get_config_dir()
        self.config_file = self.config_dir / "config.json"
        self.url = ""
        self.key = ""

    def _get_config_dir(self) -> Path:
        """获取配置目录（支持 Nuitka onefile 模式）"""
        import os
        nuitka_parent = os.environ.get('NUITKA_ONEFILE_PARENT')
        if nuitka_parent:
            return Path(nuitka_parent).parent
        script_dir = Path(sys.argv[0] if sys.argv[0] else __file__).resolve().parent
        if str(script_dir).startswith('/tmp') or str(script_dir).startswith('/var'):
            exe_dir = Path(sys.executable).parent
            if not str(exe_dir).startswith('/tmp'):
                return exe_dir
        return script_dir

    def ensure_exists(self) -> bool:
        """检测配置文件是否存在，如不存在则自动生成默认配置文件"""
        if self.config_file.exists():
            return True

        default_config = {
            "url": "https://fofa.info",
            "key": "your-fofa-key-here"
        }

        try:
            self.config_file.write_text(
                json.dumps(default_config, ensure_ascii=False, indent=4),
                encoding="utf-8"
            )
            print(f"[*] 已自动生成配置文件: {self.config_file}")
            print("[*] 请编辑配置文件填入你的 FOFA API Key 后重试")
            return False
        except Exception as e:
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
                print(f"[警告] 读取 config.json 失败: {e}", file=sys.stderr)
        return self

    def is_valid(self) -> bool:
        """验证配置是否有效"""
        return bool(self.url and self.key)

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
    _extra: dict = None

    def __post_init__(self):
        self._extra = {}

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


class FofaAPIError(Exception):
    """FOFA API 错误"""
    pass


def _ensure_fields_for_url(fields: str) -> str:
    """当请求包含 url 字段时，确保 host,ip,port,protocol 字段存在"""
    requested = {f.strip() for f in fields.split(",")}
    if "url" in requested:
        needed = {"host", "ip", "port", "protocol"}
        missing = needed - requested
        if missing:
            fields = fields + "," + ",".join(missing)
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


class FofaClient:
    """FOFA API 客户端"""

    def __init__(self, url: str, key: str):
        self.base_url = url.rstrip("/")
        self.key = key

    def get_usage(self) -> dict:
        """
        获取 FOFA API 使用量信息

        Returns:
            包含用户信息的字典
        """
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

    def search(
        self,
        query: str,
        size: int = 100,
        page: int = 1,
        fields: Optional[str] = None,
        full: bool = False,
    ) -> SearchStats:
        """
        执行 FOFA 查询

        Args:
            query: FOFA 查询语句
            size: 返回数量（最大 10000）
            page: 页码（默认为1）
            fields: 返回字段，默认为 host,ip,port,protocol,domain,title,server,country,city
            full: 是否搜索全部数据（不止一年）

        Returns:
            SearchStats 对象，包含结果列表、总匹配数和独立 IP 数
        """
        if fields is None:
            fields = "host,ip,port,protocol,domain,title,server,country,city"
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

        try:
            resp = urllib.request.urlopen(url, timeout=30)
            data = json.loads(resp.read().decode())
        except Exception as e:
            err_msg = str(e).replace(self.key, "***") if self.key else str(e)
            raise FofaAPIError(f"请求失败: {err_msg}")

        if data.get("error"):
            raise FofaAPIError(f"API 错误: {data.get('errmsg', '未知错误')}")

        results = []
        fields_list = [f.strip() for f in fields.split(",")] if fields else ["host", "ip", "port", "protocol", "domain", "title", "server", "country", "city"]
        known_fields = {"host", "ip", "port", "protocol", "domain", "title", "server", "country", "city", "lastupdatetime", "asn", "org", "os", "icp", "jarm", "header", "banner", "cert", "product", "product_category", "version", "cname", "latitude", "longitude", "region", "country_name", "base_protocol", "link"}
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
            fields = "host,ip,port,protocol,domain,title,server,country,city,lastupdatetime"
        else:
            if "lastupdatetime" not in fields:
                fields += ",lastupdatetime"
            fields = _ensure_fields_for_url(fields)
            if "host" not in [f.strip() for f in fields.split(",")]:
                fields += ",host"

        all_results = []
        seen_hosts = set()
        unique_ips = set()
        total_estimated = 0
        total_quota_used = 0

        def trigger_cb(event, **kwargs):
            if progress_callback:
                progress_callback({"event": event, **kwargs})

        count_stats = self.search(query, size=1, page=1, fields=fields, full=full)
        total_quota_used += 1
        total_estimated = count_stats.total

        time.sleep(api_rate_limit)

        if total_estimated == 0:
            trigger_cb("no_match")
            return SearchStats(total=0, unique_ips=0, results=[])

        target_count = int(total_estimated * fill_percent)
        trigger_cb("init", total_estimated=total_estimated, target_count=target_count, fill_percent=fill_percent)

        if target_count <= 0:
            trigger_cb("skip_zero_target")
            return SearchStats(total=total_estimated, unique_ips=0, results=[])

        trigger_cb("start")

        before_time = None
        batch_num = 0
        interrupted = False

        try:
            while True:
                if before_time:
                    range_query = f'{query} && before="{before_time}"'
                else:
                    range_query = query

                slice_stats = self.search(range_query, size=10000, page=1, fields=fields, full=full)
                total_quota_used += len(slice_stats.results)

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
                dup_rate = (len(slice_stats.results) - new_count) / len(slice_stats.results) * 100 if len(slice_stats.results) > 0 else 0
                
                trigger_cb("progress", 
                           batch_num=batch_num, 
                           new_count=new_count, 
                           dup_rate=dup_rate, 
                           fetched=len(all_results), 
                           total_estimated=total_estimated, 
                           total_quota_used=total_quota_used)

                if len(all_results) >= target_count:
                    trigger_cb("target_reached", fetched=len(all_results), total_estimated=total_estimated, fill_percent=fill_percent)
                    break

                if len(slice_stats.results) < 10000:
                    break

                if batch_min_time:
                    try:
                        dt = datetime.strptime(batch_min_time, "%Y-%m-%d %H:%M:%S")
                        dt -= timedelta(seconds=1)
                        before_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        before_time = None
                    except Exception:
                        before_time = batch_min_time
                else:
                    break

                time.sleep(api_rate_limit)

                if max_size > 0 and len(all_results) >= max_size:
                    break
        except KeyboardInterrupt:
            interrupted = True
            trigger_cb("interrupted")

        if max_size > 0 and len(all_results) > max_size:
            all_results = all_results[:max_size]
            unique_ips = set(r.ip for r in all_results if r.ip)

        trigger_cb("done", 
                   interrupted=interrupted, 
                   fetched=len(all_results), 
                   total_estimated=total_estimated, 
                   unique_ips=len(unique_ips), 
                   total_quota_used=total_quota_used)
                   
        return SearchStats(total=total_estimated, unique_ips=len(unique_ips), results=all_results)


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

    protocol = r.protocol.lower() if r.protocol else ("https" if r.port == "443" else "http")
    # 处理协议字段中的脏数据，例如 "http,https" 或 "socks5"
    if "," in protocol:
        protocol = protocol.split(",")[0]
        
    if not host_has_port and r.port:
        if (protocol == "http" and r.port == "80") or (protocol == "https" and r.port == "443"):
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


def dedup_results(results: list[FofaResult], fields: Optional[str], dedup_field: Optional[str] = None) -> list[FofaResult]:
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
        if not key:
            unique_results.append(r)
            continue
        if key not in seen:
            seen.add(key)
            unique_results.append(r)
    return unique_results


class Exporter:
    """导出管理器"""
    
    BASE_FIELDS = ["host", "ip", "port", "protocol", "domain", "title", "server", "country", "city",
                  "lastupdatetime", "asn", "org", "os", "icp", "jarm", "header", "banner", "cert",
                  "product", "product_category", "version", "cname", "latitude", "longitude", "region",
                  "country_name", "base_protocol", "link"]

    def __init__(self, results: list[FofaResult], fields: Optional[str] = None, dedup_field: Optional[str] = None):
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
        if not self.results:
            return 0

        if self.requested_fields:
            fieldnames = self.requested_fields.copy()
        else:
            fieldnames = self.BASE_FIELDS.copy()

        all_keys = set()
        data = self._prepare_dict_data()
        for d in data:
            all_keys.update(d.keys())
            
        dynamic_extra = [f for f in all_keys if f not in self.BASE_FIELDS and not f.startswith("_") and f not in fieldnames]

        with output_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames + dynamic_extra, extrasaction='ignore')
            writer.writeheader()
            for row in data:
                writer.writerow(row)

        return len(self.results)

    def export_json(self, output_path: Path) -> int:
        if not self.results:
            return 0

        data = self._prepare_dict_data()
        processed_data = []
        
        for d in data:
            # 过滤空值
            d = {k: v for k, v in d.items() if v != "" and v is not None}
            # 如果指定了字段，仅保留指定的字段
            if self.requested_fields:
                d = {k: d[k] for k in self.requested_fields if k in d}
            processed_data.append(d)
            
        output_path.write_text(json.dumps(processed_data, ensure_ascii=False, indent=2), encoding="utf-8")
        return len(self.results)

    def export_txt(self, output_path: Path) -> int:
        if not self.results:
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
    def progress_callback(state: dict):
        event = state.get("event")
        
        if event == "no_match":
            print("  [*] 无匹配数据")
        
        elif event == "init":
            total_estimated = state.get("total_estimated", 0)
            target_count = state.get("target_count", 0)
            fill_percent = state.get("fill_percent", 0)
            print(f"\n[*] 匹配总量: {total_estimated:,} | 目标: {target_count:,} ({int(fill_percent*100)}%)")
            print()
            
        elif event == "skip_zero_target":
            print("[*] 目标为 0，跳过批量抓取")
            
        elif event == "start":
            pass # 可以在这里打印"开始..."，目前推迟到第一个progress事件
            
        elif event == "progress":
            fetched = state.get("fetched", 0)
            total_estimated = state.get("total_estimated", 1)
            total_quota_used = state.get("total_quota_used", 0)
            batch_num = state.get("batch_num", 0)
            new_count = state.get("new_count", 0)
            dup_rate = state.get("dup_rate", 0)
            
            percent = fetched / total_estimated if total_estimated > 0 else 0
            filled = int(bar_width * percent)
            bar = f"{GREEN}{'=' * filled}{RESET}{'~' if filled < bar_width else ''}{' ' * (bar_width - filled - 1)}"
            pct_color = YELLOW if percent < 0.5 else GREEN
            msg = f"批次 {batch_num} (新增:{new_count} 重复:{dup_rate:.0f}%)"
            
            print(f"\r[{bar}] {pct_color}{percent*100:5.1f}%{RESET} | {GREEN}{fetched:>6}{RESET}/{total_estimated:<6} | {RED}配额:{total_quota_used:>6}{RESET} | {msg}", end="", flush=True)
            
        elif event == "target_reached":
            fetched = state.get("fetched", 0)
            total_estimated = state.get("total_estimated", 0)
            fill_percent = state.get("fill_percent", 0)
            print(f"\r[*] {GREEN}已达{int(fill_percent*100)}%目标{RESET} ({fetched:,}/{total_estimated:,})    ")
            
        elif event == "interrupted":
            print("\n[*] 已中断，保存已获取的数据...")
            
        elif event == "done":
            interrupted = state.get("interrupted", False)
            fetched = state.get("fetched", 0)
            total_estimated = state.get("total_estimated", 0)
            unique_ips = state.get("unique_ips", 0)
            total_quota_used = state.get("total_quota_used", 0)
            
            if not interrupted:
                percent = int(fetched / total_estimated * 100) if total_estimated > 0 else 0
                print()
                print(f"[*] {GREEN}查询完成{RESET} (API消耗: {RED}{total_quota_used}{RESET} 配额)")
                print(f"[*] 获取数据: {GREEN}{fetched:,}{RESET} 条 (覆盖率 ~{percent}%)")
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
        """,
    )
    parser.add_argument("query", nargs="?", help="FOFA 查询语句，如: domain=baidu.com")
    parser.add_argument("-o", "--output", help="输出文件名（含后缀），如 results.csv")
    parser.add_argument("-l", "--limit", help="最大返回数量，支持 >10000 或 'max'（导出全部）", default="100")
    parser.add_argument("-b", "--batch", dest="batch_file", metavar="FILE", help="批量查询文件，每行一个查询语句（配合占位符使用）")
    parser.add_argument("--fill", type=float, default=0.8, help="多次查询完成百分比（0.0-1.0），仅 -l>10000 或 max 时生效")
    parser.add_argument("-p", "--placeholder", default="{}", help="占位符格式，默认 {}，配合 -b 使用，如: python fofatoto.py \"host={}\" -b targets.txt")
    parser.add_argument("-csv", action="store_true", help="导出 CSV 格式")
    parser.add_argument("-txt", action="store_true", help="导出 TXT 格式（URL 列表）")
    parser.add_argument("-json", action="store_true", help="导出 JSON 格式")
    parser.add_argument("-f", "--fields", help="查询字段，控制 FOFA API 返回哪些字段及导出字段，默认 host,ip,port,protocol", default="host,ip,port,protocol")
    parser.add_argument("--dedup", help="根据指定字段去重，多个字段用逗号分隔，如 --dedup ip 或 --dedup ip,host")
    parser.add_argument("--full", action="store_true", help="搜索全部数据（不止一年）")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细信息")
    parser.add_argument("-w", "--web", action="store_true", help="启动 Web UI 模式（默认无参数时自动进入）")
    parser.add_argument("--port", type=int, default=0, help="Web UI 端口号（默认 8080，被占用则自动递增）")
    return parser


def print_account_status(client: FofaClient):
    """检查并打印账号状态"""
    try:
        user_info = client.get_usage()
        if user_info:
            is_vip = user_info.get('isvip', False)
            vip_status = f"{GREEN}正常{RESET}" if is_vip else f"{RED}无效{RESET}"
            print(highlight("[*] 服务器", f"{GREEN}正常{RESET}" if user_info.get('fofa_server') else f"{RED}异常{RESET}"))
            print(highlight("[*] Key状态", vip_status))
            print(highlight(f"{RED}[*] 剩余查询{RESET}", user_info.get('remain_api_query', 'N/A')))
            print(highlight("[*] 过期时间", user_info.get('expiration', 'N/A')))
            print(highlight("[*] VIP等级", user_info.get('vip_level', 'N/A')))
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
            queries = expand_placeholder_query(args.query, [t[0] for t in targets], placeholder)
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

        query_fields = args.fields
        if args.dedup:
            dedup_fields = set(f.strip() for f in args.dedup.split(",") if f.strip())
            user_fields = set(f.strip() for f in (args.fields or "").split(",") if f.strip())
            extra_fields = dedup_fields - user_fields
            if extra_fields:
                query_fields = args.fields + "," + ",".join(extra_fields)

        if limit_value > 10000 or is_max:
            max_size = 0 if is_max else limit_value
            if args.full:
                print(f"[*] 搜索全部数据（不止一年）")
            if args.verbose:
                print(f"[*] 目标: {int(args.fill*100)}%")
            stats = client.search_all_efficient(
                args.query,
                max_size=max_size,
                fields=query_fields,
                fill_percent=args.fill,
                full=args.full,
                progress_callback=create_console_progress_callback()
            )
        else:
            stats = client.search(args.query, size=limit_value, fields=query_fields, full=args.full)

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


@dataclass
class ExportTask:
    task_id: str
    status: str = "running"
    progress: float = 0.0
    message: str = ""
    fetched: int = 0
    total_estimated: int = 0
    unique_ips: int = 0
    total_quota_used: int = 0
    results: list = field(default_factory=list)
    output_files: dict = field(default_factory=dict)
    error: str = ""
    created_at: float = field(default_factory=time.time)
    cancelled: bool = False


def _create_web_progress_callback(task_id: str):
    def progress_callback(state: dict):
        cancelled = False
        with _export_lock:
            task = _export_tasks.get(task_id)
            if not task:
                return
            cancelled = task.cancelled
            event = state.get("event")
            if event == "no_match":
                task.status = "done"
                task.message = "No matching data"
                task.progress = 1.0
            elif event == "init":
                task.total_estimated = state.get("total_estimated", 0)
                task.message = "Fetching..."
            elif event == "progress":
                task.fetched = state.get("fetched", 0)
                task.total_estimated = state.get("total_estimated", 1)
                task.total_quota_used = state.get("total_quota_used", 0)
                if not cancelled:
                    task.progress = min(task.fetched / max(task.total_estimated, 1), 0.99)
            elif event == "target_reached":
                task.progress = state.get("fill_percent", 0.8)
                task.fetched = state.get("fetched", 0)
                task.message = "Target reached"
            elif event == "interrupted":
                if cancelled:
                    task.status = "error"
                    task.error = "Cancelled by user"
                task.message = "Interrupted"
            elif event == "done":
                if not cancelled:
                    task.status = "done"
                    task.progress = 1.0
                task.fetched = state.get("fetched", 0)
                task.unique_ips = state.get("unique_ips", 0)
                task.total_quota_used = state.get("total_quota_used", 0)
        if cancelled:
            raise KeyboardInterrupt()
    return progress_callback


class FofaWebHandler(http.server.BaseHTTPRequestHandler):
    """FOFA Web UI 请求处理器"""

    client: FofaClient = None

    def log_message(self, format, *args):
        sys.stderr.write(f"[web] {args[0]}\n")

    def _send_json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

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
            self._send_html(WEB_HTML_TEMPLATE)
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
        try:
            info = self.client.get_usage()
            info["server_ok"] = True
            self._send_json({"success": True, "data": info})
        except FofaAPIError as e:
            self._send_json({"success": False, "error": str(e), "data": {"server_ok": False}})

    def _handle_search(self):
        try:
            body = self._read_body()
            query = body.get("query", "")
            if not query:
                self._send_json({"success": False, "error": "Query is required"})
                return

            size = int(body.get("size", 100))
            fields = body.get("fields", "host,ip,port,protocol,domain,title,server,country,city,lastupdatetime")
            full = body.get("full", False)

            stats = self.client.search(query, size=min(size, 10000), fields=fields, full=full)

            columns = [f.strip() for f in fields.split(",") if f.strip()]
            has_url = "url" in columns
            results = []
            for r in stats.results:
                d = r.to_dict()
                if has_url:
                    d["url"] = build_url(r)
                results.append(d)

            self._send_json({
                "success": True,
                "data": {
                    "total": stats.total,
                    "unique_ips": stats.unique_ips,
                    "columns": columns,
                    "results": results
                }
            })
        except FofaAPIError as e:
            self._send_json({"success": False, "error": str(e)})
        except Exception as e:
            self._send_json({"success": False, "error": str(e)})

    def _handle_export(self):
        try:
            body = self._read_body()
            query = body.get("query", "")
            if not query:
                self._send_json({"success": False, "error": "Query is required"})
                return

            fields = body.get("fields", "host,ip,port,protocol,domain,title,server,country,city,lastupdatetime")
            fill_percent = float(body.get("fill_percent", 0.8))
            max_size = int(body.get("max_size", 0))
            full = body.get("full", False)

            task_id = uuid.uuid4().hex[:12]
            task = ExportTask(task_id=task_id)

            with _export_lock:
                _export_tasks[task_id] = task

            thread = threading.Thread(
                target=self._run_export_task,
                args=(task_id, query, fields, fill_percent, max_size, full),
                daemon=True
            )
            thread.start()

            self._send_json({"success": True, "task_id": task_id})
        except Exception as e:
            self._send_json({"success": False, "error": str(e)})

    def _run_export_task(self, task_id, query, fields, fill_percent, max_size, full):
        try:
            stats = self.client.search_all_efficient(
                query,
                max_size=max_size,
                fields=fields,
                fill_percent=fill_percent,
                full=full,
                progress_callback=_create_web_progress_callback(task_id)
            )

            with _export_lock:
                task = _export_tasks.get(task_id)
                if task and task.cancelled:
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
                    task.fetched = len(stats.results)
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
                    task.error = str(e)

    def _handle_progress(self, parsed):
        params = parse_qs(parsed.query)
        task_id = params.get("task_id", [None])[0]

        if not task_id:
            self._send_json({"success": False, "error": "task_id required"})
            return

        with _export_lock:
            task = _export_tasks.get(task_id)

        if not task:
            self._send_json({"success": False, "error": "Task not found"})
            return

        self._send_json({
            "success": True,
            "data": {
                "status": task.status,
                "progress": task.progress,
                "message": task.message,
                "fetched": task.fetched,
                "total_estimated": task.total_estimated,
                "unique_ips": task.unique_ips,
                "total_quota_used": task.total_quota_used,
                "error": task.error
            }
        })

    def _handle_export_download(self, parsed):
        params = parse_qs(parsed.query)
        task_id = params.get("task_id", [None])[0]
        fmt = params.get("format", ["csv"])[0]

        with _export_lock:
            task = _export_tasks.get(task_id)

        if not task or task.status != "done":
            self._send_json({"success": False, "error": "Export not ready"}, 404)
            return

        filepath = task.output_files.get(fmt)
        if not filepath:
            self._send_json({"success": False, "error": f"No {fmt} file"}, 404)
            return

        path = Path(filepath)
        self._send_file(path, path.name)

    def _handle_batch(self):
        try:
            body = self._read_body()
            base_query = body.get("base_query", "")
            targets = body.get("targets", [])
            placeholder = body.get("placeholder", "{}")
            fields = body.get("fields", "host,ip,port,protocol,domain,title,server,country,city,lastupdatetime")
            fill_percent = float(body.get("fill_percent", 0.8))

            if not base_query or not targets:
                self._send_json({"success": False, "error": "Base query and targets required"})
                return

            queries = expand_placeholder_query(base_query, targets, placeholder)

            task_id = uuid.uuid4().hex[:12]
            task = ExportTask(task_id=task_id)

            with _export_lock:
                _export_tasks[task_id] = task

            thread = threading.Thread(
                target=self._run_batch_task,
                args=(task_id, queries, fields, fill_percent),
                daemon=True
            )
            thread.start()

            self._send_json({"success": True, "task_id": task_id})
        except Exception as e:
            self._send_json({"success": False, "error": str(e)})

    def _run_batch_task(self, task_id, queries, fields, fill_percent):
        try:
            all_results = []
            total_queries = len(queries)
            failed_count = 0

            for batch_idx, (query, _) in enumerate(queries):
                with _export_lock:
                    task = _export_tasks.get(task_id)
                    if task and task.cancelled:
                        raise KeyboardInterrupt()

                try:
                    stats = self.client.search_all_efficient(
                        query,
                        max_size=0,
                        fields=fields,
                        fill_percent=fill_percent,
                        progress_callback=None
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
                        task.message = f"Target {batch_idx + 1}/{total_queries}"

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
                    if failed_count:
                        task.message = f"Partial: {failed_count}/{total_queries} failed"
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
                    task.error = str(e)

    def _handle_cancel(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        task_id = params.get("task_id", [None])[0]

        with _export_lock:
            task = _export_tasks.get(task_id)
            if task:
                task.cancelled = True

        self._send_json({"success": True})


def _find_available_port(start_port: int = 8080, max_attempts: int = 20) -> int:
    for offset in range(max_attempts):
        port = start_port + offset
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return start_port


class FofaWebServer:
    """FOFA Web UI 服务器"""

    def __init__(self, client: FofaClient, port: int = 0):
        self.client = client
        self.port = port or _find_available_port()
        self.httpd = None

    def start(self):
        FofaWebHandler.client = self.client

        class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
            allow_reuse_address = True
            daemon_threads = True

        self.httpd = ThreadingServer(("127.0.0.1", self.port), FofaWebHandler)

        print(f"\n{GREEN}[*] Web UI 已启动: {CYAN}http://127.0.0.1:{self.port}{RESET}")
        print(f"[*] 按 {RED}Ctrl+C{RESET} 停止服务器\n")

        webbrowser.open(f"http://127.0.0.1:{self.port}")

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

    config_manager = ConfigManager()

    # 自动检测并生成配置文件
    if not config_manager.ensure_exists():
        sys.exit(1)

    # 显示 Banner
    print(BANNER)

    # 加载配置
    config_manager.load()

    if not config_manager.is_valid():
        print("错误: 未找到有效的 FOFA API 凭证", file=sys.stderr)
        print(f"\n请在 {config_manager.config_file} 配置:", file=sys.stderr)
        print('  {"url": "https://fofa.info", "key": "your-api-key"}', file=sys.stderr)
        sys.exit(1)

    client = FofaClient(config_manager.url, config_manager.key)
    print_account_status(client)

    parser = build_parser()
    args = parser.parse_args()

    # Web UI 模式: -w 参数 或 无参数直接运行
    if args.web or (not args.query and not args.batch_file):
        server = FofaWebServer(client, port=args.port)
        server.start()
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


def expand_placeholder_query(base_query: str, targets: list[str], placeholder: str) -> list[tuple[str, int]]:
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
    for line_no, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        targets.append((line, line_no))

    if not targets:
        raise ValueError("批量目标文件中没有有效的目标值")

    return targets


def run_batch_search(client: FofaClient, queries: list[tuple[str, int]], args) -> list[FofaResult]:
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

            query_fields = args.fields
            if args.dedup:
                dedup_fields = set(f.strip() for f in args.dedup.split(",") if f.strip())
                user_fields = set(f.strip() for f in (args.fields or "").split(",") if f.strip())
                extra_fields = dedup_fields - user_fields
                if extra_fields:
                    query_fields = args.fields + "," + ",".join(extra_fields)

            if limit_value > 10000 or is_max:
                max_size = 0 if is_max else limit_value
                stats = client.search_all_efficient(
                    query,
                    max_size=max_size,
                    fields=query_fields,
                    fill_percent=args.fill,
                    full=args.full,
                    progress_callback=create_console_progress_callback()
                )
            else:
                stats = client.search(query, size=limit_value, fields=query_fields, full=args.full)

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
