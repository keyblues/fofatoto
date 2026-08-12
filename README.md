# fofatoto

> 轻量级 FOFA 网络空间资产查询工具：命令行 + 本地 Web UI，支持全量导出、批量查询、字段定制、智能去重与多格式输出，零第三方依赖。

## 特性

- **零依赖** — 仅使用 Python 标准库，Python ≥ 3.11，无需安装任何第三方包
- **双入口** — 命令行（CLI）+ 本地 Web UI（即时预览 / 深度导出 / 批量模式），Windows 双击二进制即可打开 Web UI
- **全量导出** — 突破 FOFA 单次 10000 条限制，`before` 时间游标分批拉取，遇到限流/超时自动放慢节奏
- **批量查询** — 从文件读取多个目标，支持占位符替换，逐条执行并合并导出
- **字段定制** — CLI `-f` 指定返回字段；Web UI 字段 chip 支持搜索、增删与拖拽排序
- **智能去重** — 单字段、多字段组合及 `url` 去重，去重字段自动追加到查询请求
- **多格式导出** — CSV（UTF-8-BOM）/ JSON / TXT 三种格式
- **配置热更新** — 修改 `config.json` 后下一个请求即生效，无需重启服务
- **中转站适配** — 自动识别第三方中转站（内置 `fafaapi.info`），账户信息统一展示
- **跨平台** — 提供 Windows / Linux / macOS 编译二进制，开箱即用

## 快速开始

### 1. 下载

从 [Releases](https://github.com/keyblues/fofatoto/releases) 下载对应平台的二进制文件：

| 平台 | 架构 | 文件名 |
|------|------|--------|
| Windows | amd64 | `fofatoto.exe` |
| Linux | amd64 | `fofatoto` |
| Linux | arm64 | `fofatoto_arm64` |
| macOS | amd64 | `fofatoto_mac` |
| macOS | arm64 (M 芯片) | `fofatoto_mac_arm64` |

**Windows 用户**：下载后双击运行即可启动本地 Web UI。首次运行会自动在程序所在目录创建 `config.json`，页面会提示需要填写的配置文件路径。

**Linux / macOS 用户**：赋予执行权限后运行：

```bash
chmod +x fofatoto
./fofatoto --help
```

### 2. 配置

首次运行会自动生成 `config.json`，编辑该文件填入 FOFA API Key：

```json
{
    "url": "https://fofa.info",
    "key": "your-api-key"
}
```

- `config.json` 固定放在脚本或可执行文件所在目录。
- 未配置有效 API Key 时，Web UI 仍会启动并显示配置引导；CLI 查询会打印配置模板后退出。
- 修改配置后无需重启：Web UI 每次请求都会重新读取 `config.json`。
- 使用第三方中转站时，把 `url` 改为中转站地址即可；内置了 `fafaapi.info` 的账户接口适配，其余地址按标准 FOFA 接口处理。

## 使用指南

### Web UI 模式

无参数运行或双击二进制文件时，程序会启动本地 Web UI：

```bash
./fofatoto
```

也可以显式指定 Web 模式、端口和监听地址：

```bash
./fofatoto -w                  # 显式进入 Web 模式
./fofatoto -w --port 8090      # 指定端口（默认从 17380 自动探测，被占用则递增）
./fofatoto -w --host 0.0.0.0   # 监听所有网卡，供局域网访问
```

Web UI 默认监听 `127.0.0.1`（仅本机可访问），启动后自动打开系统浏览器。无图形环境（SSH 会话、Linux 无 DISPLAY）会自动跳过打开并提示手动访问地址；WSL 环境会调起 Windows 默认浏览器；显式指定 `--host` 后也不自动打开浏览器，按启动时打印的地址访问即可。

> 注意：Web UI 无访问鉴权。非回环监听时，局域网内任何人都能访问并使用你的 FOFA 配额，请谨慎使用。

Web UI 提供三种模式：

| 模式 | 说明 |
|------|------|
| 即时预览 | 快速查询并在页面表格中查看结果：虚拟滚动承载最多 10000 条、字段 chip 拖拽排序、点击表头排序、URL 跳转、当前预览 CSV / JSON / TXT 导出 |
| 深度导出 | 后台按 `before` 时间游标分批拉取，页面展示进度、目标、配额、耗时，完成后下载 CSV / JSON / TXT |
| 批量模式 | 占位符批量替换目标，复用深度导出流程合并结果 |

主要交互功能：

- **字段选取器**：结果区操作栏「不看」和「选取查询」按钮——点击单元格将字段值排除（本地过滤，红底 chip 可单独移除）或追加为 `字段="值"` 查询条件（可配合自动搜索）
- **查询历史**：基于浏览器 localStorage，支持内联建议、过滤、点击插入、删除与键盘上下选择；设置弹窗中的「显示历史记录」开关可关闭下拉框（记录照常写入）
- **设置弹窗**：适应窗口宽度（开 = 表格贴合窗口无横向滚动，关 = 按内容自然列宽可横向滚动）、全部数据（搜索近一年之外的历史数据）、选取查询后自动搜索、显示历史记录
- **账户信息**：顶栏展示 VIP 状态、剩余查询、过期时间等，每 3 分钟自动刷新（页面隐藏时暂停）
- **超长查询语句**：输入框聚焦时自动展开换行（浮起不挤动布局），失焦收起为单行，`Enter` 搜索、`Shift+Enter` 换行

<img width="2160" height="1247" alt="Web UI 界面" src="https://github.com/user-attachments/assets/f2c4cd6a-c1f0-42ae-b165-5c33501339f7" />

### CLI 基本用法

```bash
./fofatoto "FOFA 查询语法" [选项]
```

> 查询语法参考 [FOFA 官方文档](https://fofa.info/help/doc)。

```bash
# 查询百度域名资产（默认 100 条，输出 CSV）
./fofatoto "domain=baidu.com"

# 指定输出文件
./fofatoto "domain=baidu.com" -o results.csv

# 限制返回数量
./fofatoto "domain=baidu.com" -l 1000 -o results.csv

# 指定输出格式
./fofatoto "domain=baidu.com" -json -o results.json
./fofatoto "domain=baidu.com" -txt -o results.txt
./fofatoto "domain=baidu.com" -csv -json -o results
```

未指定导出格式时默认输出 CSV；未指定输出文件名时自动生成 `fofa_results_YYYYMMDD_HHMMSS.csv`（后缀跟随格式）。

### 全量导出

将 `-l` 设为大于 10000 的值或 `max` 即可启用深度抓取，按 `before` 时间游标自动拉取匹配结果：

```bash
# 导出前 50000 条
./fofatoto "domain=baidu.com" -l 50000 -o partial.csv

# 导出全部匹配 - 默认 80% 覆盖率
./fofatoto "domain=baidu.com" -l max -o all.csv

# 覆盖 90% 的数据
./fofatoto "domain=baidu.com" -l max --fill 0.9 -o cover90.csv
```

深度抓取工作流程：

1. 先用 `size=1` 探测总匹配数
2. 按 `before` 时间递进，每批最多拉取 10000 条
3. 自动去重合并，实时显示进度与配额消耗；遇到 `[-501]`、超时等临时失败自动放慢请求节奏

### 批量查询

使用 `-b` 指定目标文件，配合占位符 `{}` 执行批量查询：

```bash
# targets.txt 内容：
# baidu.com
# qq.com
# google.com

./fofatoto "host={}" -b targets.txt -o batch.csv
```

等价于依次执行 `host=baidu.com`、`host=qq.com`、`host=google.com`，结果合并后统一导出。

批量查询行为：

- 查询语句中包含占位符时，文件每行的值替换占位符后逐条执行
- 查询语句中**不包含**占位符时，文件每行作为独立的 FOFA 查询语句执行
- 自动跳过空行和 `#` 开头的注释行
- 查询之间间隔 2 秒，避免触发 API 限流
- 支持自定义占位符：

```bash
./fofatoto "domain=\$TARGET" -b targets.txt -p '\$TARGET' -o results.csv
```

### 字段定制

默认查询字段为 `host,ip,port,protocol,domain,title,server,country,city`，通过 `-f` 指定：

```bash
# 只查询并导出 IP 和端口
./fofatoto "domain=baidu.com" -f "ip,port" -o ips.csv

# 包含 URL 时自动补充 host、ip、port、protocol
./fofatoto "domain=baidu.com" -f "url,title" -o urls.csv

# JSON 模式 - 仅输出请求的字段
./fofatoto "domain=baidu.com" -f "host,title" -json -o results.json
```

`-f` 支持 FOFA 全部可用字段。Web UI 字段选择器内置以下字段（按分类）：

| 分类 | 字段 |
|------|------|
| 核心 | `host` 域名/IP:端口 · `ip` · `port` · `protocol` · `domain` |
| 服务 | `title` 网页标题 · `server` Web 服务器 · `product` 产品名 · `version` 版本号 |
| 位置 | `country` 国家代码 · `city` 城市 · `region` 地区 · `country_name` 国家名称 · `latitude` 纬度 · `longitude` 经度 |
| 网络 | `asn` · `org` 机构名称 · `base_protocol` 基础协议 (tcp/udp) · `link` URL 链接 · `url` 按 host/port/protocol 自动拼接的完整 URL |
| 证书 | `cert` 证书信息 · `jarm` Jarm 指纹 · `icp` ICP 备案 · `cname` · `header` HTTP 响应头 · `banner` 协议 Banner |
| 时间 | `lastupdatetime` 最后更新时间 |
| 系统 | `os` 操作系统 · `product_category` 产品分类 |

### 结果去重

使用 `--dedup` 指定去重字段，去重字段会自动追加到查询请求中：

```bash
# 按 IP 去重
./fofatoto "domain=baidu.com" --dedup ip -o deduped.csv

# 按 IP + 端口组合去重
./fofatoto "domain=baidu.com" --dedup ip,port -o deduped.csv

# 按完整 URL 去重（自动调用 build_url 拼接）
./fofatoto "domain=baidu.com" --dedup url -o deduped.csv
```

### TXT 导出

TXT 模式根据查询字段自动决定输出内容：

| 查询字段 | 输出内容 |
|----------|----------|
| `-f ip` | IP 地址列表 |
| `-f domain` | 域名列表 |
| 其他 | URL 列表（自动补全协议和端口） |

```bash
./fofatoto "domain=baidu.com" -f ip -txt -o ips.txt
./fofatoto "domain=baidu.com" -f domain -txt -o domains.txt
./fofatoto "domain=baidu.com" -txt -o urls.txt
```

### 搜索历史数据

默认仅搜索 FOFA 近一年内数据，使用 `--full` 可搜索全部历史：

```bash
./fofatoto "domain=baidu.com" -l max --full -o historical.csv
```

### 账户状态检测

`-c` / `--check` 快速检测账户：仅显示 Banner 与账户状态（VIP 等级、剩余查询、过期时间等）后退出，不执行查询：

```bash
./fofatoto -c
```

## 命令行参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | 位置参数 | - | FOFA 查询语法字符串 |
| `-o, --output` | 值 | 自动生成 | 输出文件路径（含后缀） |
| `-l, --limit` | 值 | `100` | 最大返回数量，支持数字、`max` |
| `-f, --fields` | 值 | `host,ip,port,protocol,domain,title,server,country,city` | 控制 API 返回及导出字段 |
| `-csv` | 标志 | 否 | 导出 CSV 格式（UTF-8-BOM） |
| `-txt` | 标志 | 否 | 导出 TXT 格式 |
| `-json` | 标志 | 否 | 导出 JSON 格式 |
| `--dedup` | 值 | - | 按指定字段去重，逗号分隔 |
| `-b, --batch` | 值 | - | 批量查询目标文件路径 |
| `-p, --placeholder` | 值 | `{}` | 批量查询占位符格式 |
| `--fill` | 值 | `0.8` | 深度抓取完成百分比（0.0-1.0，仅 `-l`>10000 或 `max` 时生效） |
| `--full` | 标志 | 否 | 搜索全部历史数据 |
| `-v, --verbose` | 标志 | 否 | 显示详细查询信息 |
| `-w, --web` | 标志 | 否 | 启动 Web UI 模式（无参数时自动进入） |
| `--port` | 值 | 自动 | Web UI 端口号，默认从 17380 自动探测 |
| `--host` | 值 | `127.0.0.1` | Web UI 监听地址；`0.0.0.0` 监听所有网卡；指定后不再自动打开浏览器 |
| `-c, --check` | 标志 | 否 | 快速检测：仅显示账户信息后退出 |
| `-h, --help` | 标志 | - | 显示帮助信息 |

## 从源码运行

无需安装任何第三方依赖，Python ≥ 3.11 直接运行：

```bash
# 克隆仓库或只下载 fofatoto.py（单文件）
git clone https://github.com/keyblues/fofatoto.git
cd fofatoto

# CLI 查询
python fofatoto.py "domain=baidu.com" -l 10

# Web UI
python fofatoto.py -w
```

Windows 下若 `python` 不在 PATH，可用 `py -3` 代替：

```powershell
py -3 fofatoto.py "domain=baidu.com" -l 10
```

### 使用 uv

项目自带 `pyproject.toml` 与 `uv.lock`，可用 [uv](https://docs.astral.sh/uv/) 一键准备正确的 Python 版本并运行，无需手动安装 Python：

```bash
# 安装 uv 后直接运行（uv 按 requires-python 自动下载 ≥ 3.11 的解释器）
uv run fofatoto.py "domain=baidu.com" -l 10
uv run fofatoto.py -w

# 指定 Python 版本
uv run --python 3.12 fofatoto.py "ip=1.1.1.1" -l 5
```

`uv run` 会按 `pyproject.toml` 自动创建并同步项目环境；本项目零第三方依赖，环境里只有解释器本身。

## 架构

```
+-----------------+
|   用户输入       |  查询语句 (FOFA 语法)
+--------+--------+
         |
+--------v--------+        +----------+
|  参数解析器      |  --->  |  配置加载 |  (config.json，按请求热更新)
+--------+--------+        +----------+
         |
+--------v--------+
|  FofaClient     |  +--------+
|  · search()     |  | FOFA   |  API v1/search/all
|  · search_all() |  |  API   |  API v1/info/my
+--------+--------+  +--------+
         |
+--------v--------+
|  数据处理层      |  · 去重 / 字段补全 / URL 拼接
+--------+--------+
         |
+--------v--------+
|  导出层         |  · CSV / JSON / TXT
+-----------------+
```

Web UI 由 `http.server` 提供：仅监听本机（默认 `127.0.0.1`，可用 `--host` 变更），前端为内联 HTML/CSS/JS（无外部资源），通过 `/api/search`、`/api/export`、`/api/batch`、`/api/progress`、`/api/info` 等接口与后端交互，多线程处理请求。

## 构建指南

从源码构建需要先安装 Nuitka 和系统依赖：

```bash
# 安装依赖
pip install nuitka zstandard

# Linux 需要
apt install python3-dev patchelf
```

### 编译命令

```bash
# Linux / macOS
python3 -m nuitka --onefile \
  --lto=yes --static-libpython=yes --remove-output --assume-yes-for-downloads \
  --python-flag=no_site,no_docstrings \
  --noinclude-pytest-mode=nofollow \
  --noinclude-setuptools-mode=nofollow \
  --noinclude-unittest-mode=nofollow \
  --noinclude-pydoc-mode=nofollow \
  --output-filename=fofatoto \
  fofatoto.py

# Windows (PowerShell 需要单行命令)
python -m nuitka --onefile --lto=yes --remove-output --assume-yes-for-downloads --python-flag=no_site,no_docstrings --noinclude-pytest-mode=nofollow --noinclude-setuptools-mode=nofollow --noinclude-unittest-mode=nofollow --noinclude-pydoc-mode=nofollow --noinclude-IPython-mode=nofollow --noinclude-dask-mode=nofollow --noinclude-numba-mode=nofollow --noinclude-default-mode=nofollow --output-dir=dist --output-filename=fofatoto.exe fofatoto.py
```

项目使用 GitHub Actions 自动构建多平台二进制（push `v*` 标签或手动触发），配置见 `.github/workflows/build.yml`。

## 许可证

[GNU GPL v3](LICENSE)
