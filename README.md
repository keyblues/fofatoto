# fofatoto

> 轻量级 FOFA 网络空间资产查询工具，支持全量抓取、批量查询、字段定制、智能去重与多格式导出，零第三方依赖。

## 特性

- **零依赖** — 基于 Python 标准库构建，无需安装任何第三方包
- **跨平台** — 支持 Windows / Linux / macOS，提供开箱即用的编译二进制
- **全量导出** — 突破 FOFA 单次 10000 条限制，通过 `before` 递进策略自动分页拉取全部结果
- **批量查询** — 从文件读取多个目标，自动替换占位符并行查询并合并结果
- **字段定制** — 精确控制导出字段，支持 FOFA 全部可用字段
- **智能去重** — 支持单字段、多字段组合及 `url` 字段去重，去重字段自动补充到查询请求
- **多种格式** — 支持 CSV (UTF-8-BOM)、JSON、TXT 三种导出格式

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

**Windows 用户**：下载后双击运行即可，程序会自动在所在目录创建配置文件。

**Linux / macOS 用户**：赋予执行权限后运行：
```bash
chmod +x fofatoto
./fofatoto --help
```

### 2. 配置

首次运行时会自动生成 `config.json`，编辑该文件填入 FOFA API Key：

```json
{
    "url": "https://fofa.info",
    "key": "your-api-key"
}
```

> 未配置有效 API Key 时程序将无法执行查询，配置文件路径可通过设置 `NUITKA_ONEFILE_PARENT` 环境变量自定义（Nuitka 编译模式）。

## 使用指南

### 基本用法

```bash
./fofatoto "FOFA 查询语法" [选项]
```

> 查询语法参考 [FOFA 官方文档](https://fofa.info/help/doc)。

```bash
# 查询百度域名资产
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

### 全量导出

将 `-l` 设为大于 10000 的值或 `max` 即可启用分页模式，自动拉取所有匹配结果：

```bash
# 导出前 50000 条（约 50% 数据）
./fofatoto "domain=baidu.com" -l 50000 -o partial.csv

# 导出全部匹配 - 默认 80% 覆盖率
./fofatoto "domain=baidu.com" -l max -o all.csv

# 覆盖 90% 的数据
./fofatoto "domain=baidu.com" -l max --fill 0.9 -o cover90.csv
```

分页模式工作流程：
1. 先用 `size=1` 探测总匹配数
2. 按 `before` 时间递进，每批拉取最多 10000 条
3. 自动去重，实时显示进度和配额消耗

### 批量查询

使用 `-b` 指定目标文件，结合占位符 `{}` 执行批量查询：

```bash
# targets.txt 内容：
# baidu.com
# qq.com
# google.com

./fofatoto "host={}" -b targets.txt -o batch.csv
```

等价于依次执行：
```
host=baidu.com
host=qq.com
host=google.com
```

> 所有查询的结果会自动合并后统一导出。查询之间间隔 2 秒，避免触发 API 限流。

#### 批量查询行为说明

- 查询语句中包含占位符时，文件每行的值替换占位符后逐条执行
- 查询语句中**不包含**占位符时，文件每行作为独立的 FOFA 查询语句执行
- 自动跳过空行和 `#` 开头的注释行
- 支持自定义占位符：

```bash
./fofatoto "domain=\$TARGET" -b targets.txt -p '\$TARGET' -o results.csv
```

### 字段定制

默认查询字段为 `host,ip,port,protocol`，可通过 `-f` 参数指定。

#### FOFA 可用字段

| 字段名 | 说明 |
|--------|------|
| `host` | 域名 / IP:端口 |
| `ip` | IP 地址 |
| `port` | 端口号 |
| `protocol` | 协议类型 |
| `domain` | 域名 |
| `title` | 网页标题 |
| `server` | Web 服务器 |
| `country` | 国家代码 |
| `country_name` | 国家名称 |
| `city` | 城市 |
| `region` | 地区 |
| `latitude` | 纬度 |
| `longitude` | 经度 |
| `asn` | ASN |
| `org` | 机构名称 |
| `os` | 操作系统 |
| `icp` | ICP 备案 |
| `jarm` | Jarm 指纹 |
| `header` | HTTP 响应头 |
| `banner` | 协议 Banner |
| `cert` | 证书信息 |
| `product` | 产品名 |
| `product_category` | 产品分类 |
| `version` | 版本号 |
| `cname` | CNAME |
| `base_protocol` | 基础协议 (tcp/udp) |
| `link` | URL 链接 |
| `url` | 根据 host/port/protocol 自动拼接的完整 URL |

```bash
# 只查询并导出 IP 和端口
./fofatoto "domain=baidu.com" -f "ip,port" -o ips.csv

# 包含 URL 时自动补充 host、ip、port、protocol
./fofatoto "domain=baidu.com" -f "url,title" -o urls.csv

# JSON 模式 - 仅输出请求的字段
./fofatoto "domain=baidu.com" -f "host,title" -json -o results.json
```

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

> CSV 和 JSON 在 `requested_has_url` 时，若 API 未返回 `url` 字段，会自动通过 `build_url()` 从 host/port/protocol 拼接。

### TXT 导出

TXT 模式根据查询字段自动决定输出格式：

| 查询字段 | 输出内容 |
|----------|----------|
| `-f ip` | IP 地址列表 |
| `-f domain` | 域名列表 |
| 其他 | URL 列表 (自动补全协议和端口) |

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

## 命令行参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | 位置参数 | - | FOFA 查询语法字符串 |
| `-o, --output` | 值 | 自动生成 | 输出文件路径（含后缀） |
| `-l, --limit` | 值 | `100` | 最大返回数量，支持数字、`max` |
| `-f, --fields` | 值 | `host,ip,port,protocol` | 控制 API 返回及导出字段 |
| `-csv` | 标志 | 否 | 导出 CSV 格式 (UTF-8-BOM) |
| `-txt` | 标志 | 否 | 导出 TXT 格式 |
| `-json` | 标志 | 否 | 导出 JSON 格式 |
| `--dedup` | 值 | - | 按指定字段去重，逗号分隔 |
| `-b, --batch` | 值 | - | 批量查询目标文件路径 |
| `-p, --placeholder` | 值 | `{}` | 批量查询占位符格式 |
| `--fill` | 值 | `0.8` | 分页模式完成百分比 (0.0-1.0) |
| `--full` | 标志 | 否 | 搜索全部历史数据 |
| `-v, --verbose` | 标志 | 否 | 显示详细查询信息 |
| `-h, --help` | 标志 | - | 显示帮助信息 |

> 未指定导出格式时，默认输出 CSV。未指定输出文件名时，自动生成 `fofa_results_YYYYMMDD_HHMMSS.csv`。

## 架构

```
+-----------------+
|   用户输入       |  查询语句 (FOFA 语法)
+--------+--------+
         |
+--------v--------+        +----------+
|  参数解析器      |  --->  |  配置加载 |  (config.json)
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

项目使用 GitHub Actions 自动构建多平台二进制，配置见 `.github/workflows/build.yml`。

## 许可证

[GNU GPL v3](LICENSE)
