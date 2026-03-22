#!/usr/bin/env python3
"""
FOFA 查询工具 - 单文件工具

用法:
    python fofatoto.py "protocol=http"                    # 基本查询
    python fofatoto.py "domain=baidu.com" -o results      # 指定输出文件名
    python fofatoto.py "ip=1.1.1.1/24" --json             # 输出 JSON 格式
    python fofatoto.py "port=80,443" -l 50000             # 指定返回 50000 条
    python fofatoto.py "domain=baidu.com" -l max          # 导出所有匹配数据
    python fofatoto.py "domain=baidu.com" -f "ip,port"    # 指定查询字段
    python fofatoto.py "domain=baidu.com" -l max --full   # 导出超过一年的全部数据

高效模式说明:
    当 -l 参数 > 10000 或为 max 时，自动使用 after 时间范围查询
    该模式每次获取 10000 条，自动根据 lastupdatetime 继续获取下一批
    数据会自动去重，确保唯一性
"""

import argparse
import json
import csv
import os
import sys
import base64
import time
import urllib.request
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Callable


# ============ Banner ============

BANNER = r"""
  _____ ___  _____ _      _____ ___ _____ ___  
 |  ___/ _ \|  ___/ \    |_   _/ _ \_   _/ _ \ 
 | |_ | | | | |_ / _ \     | || | | || || | | |
 |  _|| |_| |  _/ ___ \    | || |_| || || |_| |
 |_|   \___/|_|/_/   \_\   |_| \___/ |_| \___/ 
                                               

        			FOFA Query Tool v1.0
        			https://fofa.info
"""

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def highlight(text: str, value: str) -> str:
    return f"{text}: {BOLD}{value}{RESET}"


# ============ 配置相关 ============

CONFIG_FILE = Path(__file__).parent / "config.json"


@dataclass
class Config:
    url: str = ""
    key: str = ""

    @classmethod
    def load(cls) -> "Config":
        """从配置文件加载配置"""
        config = cls()

        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                config.url = data.get("url", "")
                config.key = data.get("key", "")
            except Exception as e:
                print(f"[警告] 读取 config.json 失败: {e}", file=sys.stderr)

        return config


def ensure_config_exists() -> bool:
    """
    检测配置文件是否存在，如不存在则自动生成默认配置文件

    Returns:
        配置文件是否已存在（True=已存在，False=新生成）
    """
    if CONFIG_FILE.exists():
        return True

    default_config = {
        "url": "https://fofa.icu",
        "key": "your-fofa-key-here"
    }

    try:
        CONFIG_FILE.write_text(
            json.dumps(default_config, ensure_ascii=False, indent=4),
            encoding="utf-8"
        )
        print(f"[*] 已自动生成配置文件: {CONFIG_FILE}")
        print("[*] 请编辑配置文件填入你的 FOFA API Key 后重试")
        return False
    except Exception as e:
        print(f"[!] 创建配置文件失败: {e}", file=sys.stderr)
        return False


def _config_validate(self) -> bool:
    """验证配置是否有效"""
    return bool(self.url and self.key)


Config.validate = _config_validate


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
            if result[key] == "" and key not in self._extra:
                if key.startswith("_"):
                    del result[key]
        return result


@dataclass
class SearchStats:
    """查询统计信息"""
    total: int = 0
    unique_ips: int = 0
    results: list = None

    def __post_init__(self):
        if self.results is None:
            self.results = []


class FofaAPIError(Exception):
    """FOFA API 错误"""
    pass


class FofaClient:
    """FOFA API 客户端"""

    def __init__(self, url: str, key: str):
        self.base_url = url.rstrip("/")
        self.key = key
        self._validate_credential()

    def _validate_credential(self) -> None:
        """验证凭证有效性"""
        query = base64.b64encode(b"test").decode()
        api_url = f"{self.base_url}/api/v1/search/all?key={self.key}&qbase64={query}&size=1"
        try:
            resp = urllib.request.urlopen(api_url, timeout=10)
            data = json.loads(resp.read().decode())
            if data.get("error"):
                raise FofaAPIError(f"API 凭证验证失败: {data.get('errmsg', '未知错误')}")
        except Exception as e:
            raise FofaAPIError(f"API 凭证验证失败: {e}")

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
            return data if not data.get("error") else {}
        except Exception as e:
            raise FofaAPIError(f"获取用量失败: {e}")

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
            raise FofaAPIError(f"请求失败: {e}")

        if data.get("error"):
            raise FofaAPIError(f"API 错误: {data.get('errmsg', '未知错误')}")

        results = []
        fields_list = [f.strip() for f in fields.split(",")] if fields else ["host", "ip", "port", "protocol", "domain", "title", "server", "country", "city"]
        known_fields = {"host", "ip", "port", "protocol", "domain", "title", "server", "country", "city", "lastupdatetime", "asn", "org", "os", "icp", "jarm", "header", "banner", "cert", "product", "product_category", "version", "cname", "latitude", "longitude", "region", "country_name", "base_protocol", "link"}
        unique_ips = set()
        for item in data.get("results", []):
            result = FofaResult()
            result._extra = {}
            for i, field in enumerate(fields_list):
                value = item[i] if len(item) > i else ""
                if field in known_fields:
                    setattr(result, field, value)
                else:
                    result._extra[field] = value
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
        fill_percent: float = 0.9,
        api_rate_limit: float = 5.0,
        full: bool = False,
    ) -> SearchStats:
        """
        高效查询所有结果：使用 before 递进策略

        策略：
        1. 用 before 从最新时间往前查，每次最多 10000 条
        2. 每批记录本批中最小的 lastupdatetime，作为下次查询的 before 值
        3. 直到某批数据不足 10000 条或达到目标数量
        4. 合并所有结果并去重

        Args:
            query: FOFA 查询语句
            max_size: 最大返回数量（0 表示不限制）
            fields: 返回字段
            fill_percent: 完成百分比（0.0-1.0），默认 0.9
            api_rate_limit: API 频率限制（秒），默认 5 秒
            full: 是否搜索全部数据

        Returns:
            SearchStats 对象
        """
        if fields is None:
            fields = "host,ip,port,protocol,domain,title,server,country,city,lastupdatetime"
        elif "lastupdatetime" not in fields:
            fields += ",lastupdatetime"

        all_results = []
        seen_hosts = set()
        unique_ips = set()
        api_used = 0
        total_estimated = 0
        bar_width = 25

        def print_progress(msg=""):
            if total_estimated <= 0:
                return
            fetched = len(all_results)
            percent = fetched / total_estimated
            filled = int(bar_width * percent)
            bar = f"{GREEN}{'=' * filled}{RESET}{'~' if filled < bar_width else ''}{' ' * (bar_width - filled - 1)}"
            pct_color = YELLOW if percent < 50 else GREEN
            print(f"\r[{bar}] {pct_color}{percent*100:5.1f}%{RESET} | {GREEN}{fetched:>6}{RESET}/{target_count:<6} | {RED}配额:{api_used:>6}{RESET} | {msg}", end="", flush=True)

        def print_done():
            percent = int(len(all_results) / total_estimated * 100) if total_estimated > 0 else 0
            print()
            print(f"[*] {GREEN}查询完成{RESET} (API消耗: {RED}{api_used}{RESET} 配额)")
            print(f"[*] 获取数据: {GREEN}{len(all_results):,}{RESET} 条 (覆盖率 ~{percent}%)")
            print(f"[*] 独立 IP: {CYAN}{len(unique_ips):,}{RESET}")

        count_stats = self.search(query, size=1, page=1, fields=fields, full=full)
        api_used += 1
        total_estimated = count_stats.total

        time.sleep(api_rate_limit)

        if total_estimated == 0:
            print("  [*] 无匹配数据")
            return SearchStats(total=0, unique_ips=0, results=[])

        target_count = int(total_estimated * fill_percent)
        print(f"\n[*] 匹配总量: {total_estimated:,}")
        print(f"[*] 目标数量: {target_count:,} ({int(fill_percent*100)}%)")
        print()
        print_progress("开始查询...")

        before_time = None
        batch_num = 0

        while True:
            if before_time:
                range_query = f'{query} && before="{before_time}"'
            else:
                range_query = query

            slice_stats = self.search(range_query, size=10000, page=1, fields=fields, full=full)
            api_used += len(slice_stats.results)

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
            print_progress(f"批次 {batch_num} (新增:{new_count} 重复:{dup_rate:.0f}%)")

            if len(all_results) >= target_count:
                print()
                print(f"[*] 已达到 {int(fill_percent*100)}% 目标，停止")
                break

            if len(slice_stats.results) < 10000:
                break

            if batch_min_time:
                from datetime import datetime, timedelta
                try:
                    dt = datetime.strptime(batch_min_time, "%Y-%m-%d %H:%M:%S")
                    dt -= timedelta(seconds=1)
                    before_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    before_time = None
                except:
                    before_time = batch_min_time
            else:
                before_time = None

            time.sleep(api_rate_limit)

            if max_size > 0 and len(all_results) >= max_size:
                break

        print_done()
        return SearchStats(total=len(all_results), unique_ips=len(unique_ips), results=all_results)


# ============ 导出相关 ============

def export_csv(results: list[FofaResult], output_path: Path, fields: Optional[str] = None) -> int:
    """导出为 CSV 文件"""
    if not results:
        return 0

    base_fields = ["host", "ip", "port", "protocol", "domain", "title", "server", "country", "city",
                  "lastupdatetime", "asn", "org", "os", "icp", "jarm", "header", "banner", "cert",
                  "product", "product_category", "version", "cname", "latitude", "longitude", "region",
                  "country_name", "base_protocol", "link"]

    if fields:
        requested = [f.strip() for f in fields.split(",")]
        fieldnames = [f for f in requested if f in base_fields]
        extra_fields = [f for f in requested if f not in base_fields]
    else:
        fieldnames = base_fields
        extra_fields = []

    all_keys = set()
    for r in results:
        all_keys.update(r.to_dict().keys())
    dynamic_extra = [f for f in all_keys if f not in base_fields and not f.startswith("_") and f not in fieldnames]

    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames + extra_fields + dynamic_extra, extrasaction='ignore')
        writer.writeheader()
        for r in results:
            writer.writerow(r.to_dict())

    return len(results)


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


def export_txt(results: list[FofaResult], output_path: Path) -> int:
    """导出为 TXT 文件（URL 列表）"""
    if not results:
        return 0

    count = 0
    with output_path.open("w", encoding="utf-8", newline="\n") as f:
        for r in results:
            if r.host:
                if r.host.startswith("http"):
                    url = r.host
                else:
                    protocol = r.protocol or "http"
                    if r.port and r.port not in ("80", "443"):
                        url = f"{protocol}://{r.host}:{r.port}"
                    else:
                        url = f"{protocol}://{r.host}"
                f.write(f"{url}\n")
                count += 1
            elif r.ip:
                protocol = r.protocol or "http"
                if r.port and r.port not in ("80", "443"):
                    url = f"{protocol}://{r.ip}:{r.port}"
                else:
                    url = f"{protocol}://{r.ip}"
                f.write(f"{url}\n")
                count += 1

    return count


def export_json(results: list[FofaResult], output_path: Path) -> int:
    """导出为 JSON 文件"""
    data = [r.to_dict() for r in results]
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(results)


# ============ 主函数 ============

def build_parser():
    parser = argparse.ArgumentParser(
        description="FOFA 查询工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("query", nargs="?", help="FOFA 查询语句，如: domain=baidu.com")
    parser.add_argument("-o", "--output", help="输出文件名（不含后缀），默认为 fofa_results", default="fofa_results")
    parser.add_argument("-l", "--limit", help="最大返回数量，支持 >10000 的数值或 'max'（导出所有匹配数据）", default="100")
    parser.add_argument("--fill", type=float, default=0.9, help="高效模式完成百分比（0.0-1.0），默认 0.9（90%%），设为 1.0 则查完所有数据")
    parser.add_argument("-csv", action="store_true", help="导出 CSV 格式")
    parser.add_argument("-txt", action="store_true", help="导出 TXT 格式（URL 列表）")
    parser.add_argument("-json", action="store_true", help="导出 JSON 格式")
    parser.add_argument("-f", "--fields", help="指定查询字段，默认为 host,ip,port,protocol,domain,title,server,country,city", default="host,ip,port,protocol,domain,title,server,country,city")
    parser.add_argument("--full", action="store_true", help="搜索全部数据（不止一年）")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细信息")
    return parser


def main():
    # 检查是否显示帮助
    if "-h" in sys.argv or "--help" in sys.argv:
        build_parser().print_help()
        sys.exit(0)

    # 自动检测并生成配置文件
    if not ensure_config_exists():
        sys.exit(1)

    # 显示 Banner
    print(BANNER)

    # 加载配置
    config = Config.load()

    if not config.validate():
        print("错误: 未找到有效的 FOFA API 凭证", file=sys.stderr)
        print(f"\n请在 {CONFIG_FILE} 配置:", file=sys.stderr)
        print('  {"url": "https://fofa.info", "key": "your-api-key"}', file=sys.stderr)
        sys.exit(1)

    # 创建客户端并检查用量
    try:
        client = FofaClient(config.url, config.key)
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

    parser = build_parser()
    args = parser.parse_args()

    # 如果没有指定格式，默认全部导出
    if not any([args.csv, args.txt, args.json]):
        args.csv = True

    # 没有查询语句时显示 usage
    if not args.query:
        sys.stderr.write(parser.format_usage())
        sys.exit(1)

    # 执行查询
    try:
        limit_str = str(args.limit)
        is_max = limit_str.lower() == "max"
        limit_value = 0 if is_max else int(limit_str)

        if args.verbose:
            print(f"[*] 查询: {args.query}")
            print(f"[*] 数量限制: {'无限制(max)' if is_max else limit_value}")

        if is_max:
            if args.verbose:
                print(f"[*] 使用高效 before 模式查询...")
                print(f"[*] 完成百分比: {int(args.fill*100)}%")
                if args.full:
                    print(f"[*] 搜索全部数据（不止一年）")
            stats = client.search_all_efficient(
                args.query,
                max_size=0,
                fields=args.fields,
                fill_percent=args.fill,
                full=args.full,
            )
        elif limit_value > 10000:
            if args.verbose:
                print(f"[*] 使用高效 before 模式查询...")
                print(f"[*] 完成百分比: {int(args.fill*100)}%")
                if args.full:
                    print(f"[*] 搜索全部数据（不止一年）")
            stats = client.search_all_efficient(
                args.query,
                max_size=limit_value,
                fields=args.fields,
                fill_percent=args.fill,
                full=args.full,
            )
        else:
            stats = client.search(args.query, size=limit_value, fields=args.fields, full=args.full)

        results = stats.results

        print(f"[*] 找到 {YELLOW}{stats.total:,}{RESET} 条匹配结果")

        if not results:
            print("[-] 没有找到结果")
            sys.exit(0)

        # 导出文件
        output_path = Path(args.output)
        exported = 0

        if args.csv:
            csv_path = unique_path(output_path.with_suffix(".csv"))
            count = export_csv(results, csv_path, fields=args.fields)
            print(f"[+] 已导出 CSV: {csv_path} ({count} 条)")
            exported += 1

        if args.txt:
            txt_path = unique_path(output_path.with_suffix(".txt"))
            count = export_txt(results, txt_path)
            print(f"[+] 已导出 TXT: {txt_path} ({count} 条)")
            exported += 1

        if args.json:
            json_path = unique_path(output_path.with_suffix(".json"))
            count = export_json(results, json_path)
            print(f"[+] 已导出 JSON: {json_path} ({count} 条)")
            exported += 1

        if exported == 0:
            print("[-] 没有导出任何文件（请指定输出格式）")

    except FofaAPIError as e:
        print(f"[-] API 错误: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[-] 已取消")
        sys.exit(1)
    except Exception as e:
        print(f"[-] 错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
