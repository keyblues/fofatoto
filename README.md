# fofatoto

FOFA 查询工具，支持单次查询和多次查询模式。

## 下载

从 [Releases](https://github.com/keyblues/fofatoto/releases) 下载编译好的二进制文件：

| 平台 | 架构 | 文件名 |
|------|------|--------|
| Windows | amd64 | fofatoto.exe |
| Linux | amd64 | fofatoto |
| Linux | arm64 | fofatoto_arm64 |
| macOS | amd64 | fofatoto_mac |
| macOS | arm64 (M芯片) | fofatoto_mac_arm64 |

## 配置

首次运行时会自动创建 `config.json`，填入你的 FOFA API 地址和密钥：

```json
{
    "url": "https://fofa.info",
    "key": "your-api-key"
}
```

## 使用方法

```bash
./fofatoto "查询语句" [选项]
```

### 选项

| 选项 | 说明 |
|------|------|
| `-o, --output` | 输出文件名（含后缀），如 results.csv |
| `-l, --limit` | 最大返回数量，支持 >10000 或 max（导出全部） |
| `--fill` | 多次查询完成百分比（0.0-1.0），仅 -l>10000 或 max 时生效 |
| `-csv` | 导出 CSV 格式 |
| `-txt` | 导出 TXT 格式（URL/IP/Domain 列表） |
| `-json` | 导出 JSON 格式 |
| `-f, --fields` | 查询字段，控制 FOFA API 返回哪些字段，默认 host,ip,port,protocol |
| `--dedup` | 根据指定字段去重，多个字段用逗号分隔 |
| `-b, --batch FILE | 批量查询文件，每行一个查询语句 |
| `--full` | 搜索全部数据（不止一年） |
| `-v, --verbose` | 显示详细信息 |

### 示例

```bash
# 基本查询
./fofatoto "domain=baidu.com"

# 指定输出文件
./fofatoto "domain=baidu.com" -o results.csv

# 导出全部匹配数据
./fofatoto "domain=baidu.com" -l max -o all.csv

# 输出 JSON 格式
./fofatoto "ip=1.1.1.1/24" -json -o ips.json

# 指定查询字段
./fofatoto "domain=baidu.com" -f "ip,port"

# 根据 IP 去重
./fofatoto "domain=baidu.com" --dedup ip

# 根据多个字段组合去重
./fofatoto "domain=baidu.com" --dedup ip,host

# 搜索超过一年的全部数据
./fofatoto "domain=baidu.com" -l max --full -o all.csv

# 批量查询模式
./fofatoto -b queries.txt -o batch_results.csv
```

## 多次查询模式

当 `-l` 参数大于 10000 或为 `max` 时，自动启用多次查询模式：

- 每次从 FOFA API 获取最多 10000 条数据
- 通过 `lastupdatetime` 字段递进获取下一批数据
- 默认完成 80% 的数据，可通过 `--fill` 调整

## 批量查询模式

使用 `-b` 或 `--batch` 参数指定包含多个查询语句的文件，逐个执行查询并合并结果：

```bash
# queries.txt 内容示例
domain=baidu.com
domain=qq.com
ip=1.1.1.1/24
protocol=http
```

```bash
# 执行批量查询
./fofatoto -b queries.txt -o batch_results.csv

# 批量查询时使用 max 模式
./fofatoto -b queries.txt -l max -o batch_all.csv
```

批量查询特性：
- 自动跳过空行和 `#` 开头的注释行
- 显示每个查询的执行进度
- 所有结果合并后统一导出
- 查询间隔 2 秒，避免 API 限流

## TXT 导出格式

TXT 导出根据查询字段自动判断输出格式：

| 查询字段 | 输出格式 |
|----------|----------|
| `-f ip` | IP 列表 |
| `-f domain` | Domain 列表 |
| 其他 | URL 列表 |

## 去重说明

- 默认根据所有导出字段组合去重
- 可通过 `--dedup` 指定单一字段去重
- 可通过 `--dedup ip,host` 指定多字段组合去重
- 去重字段会自动添加到查询请求中

## 构建

```bash
pip install nuitka zstandard
apt install python3-dev patchelf

python -m nuitka --onefile \
  --lto=yes --remove-output --assume-yes-for-downloads \
  --python-flag=no_docstrings \
  --noinclude-pytest-mode=nofollow \
  --noinclude-setuptools-mode=nofollow \
  --noinclude-unittest-mode=nofollow \
  --noinclude-pydoc-mode=nofollow \
  --output-filename=fofatoto \
  fofatoto.py
```
