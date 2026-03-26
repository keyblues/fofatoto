#!/usr/bin/env python3
"""
FOFA 查询工具 - 单文件工具
"""

import argparse
import json
import csv
import sys
import base64
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional
from urllib.parse import urlparse


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

def get_config_dir():
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

CONFIG_FILE = get_config_dir() / "config.json"


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
        "url": "https://fofa.info",
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
            if "domain" in fields_list and result.host:
                if result.host.startswith("http"):
                    parsed = urlparse(result.host)
                    netloc = parsed.netloc
                    if ":" in netloc:
                        netloc = netloc.split(":")[0]
                    result.domain = netloc
                elif result.host.replace(".", "").replace(":", "").isdigit():
                    result.domain = ""
                else:
                    result.domain = result.host
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
        total_estimated = 0
        bar_width = 25
        total_quota_used = 0

        def print_progress(msg=""):
            if total_estimated <= 0:
                return
            fetched = len(all_results)
            percent = fetched / total_estimated
            filled = int(bar_width * percent)
            bar = f"{GREEN}{'=' * filled}{RESET}{'~' if filled < bar_width else ''}{' ' * (bar_width - filled - 1)}"
            pct_color = YELLOW if percent < 50 else GREEN
            print(f"\r[{bar}] {pct_color}{percent*100:5.1f}%{RESET} | {GREEN}{fetched:>6}{RESET}/{total_estimated:<6} | {RED}配额:{total_quota_used:>6}{RESET} | {msg}", end="", flush=True)

        def print_done():
            percent = int(len(all_results) / total_estimated * 100) if total_estimated > 0 else 0
            print()
            print(f"[*] {GREEN}查询完成{RESET} (API消耗: {RED}{total_quota_used}{RESET} 配额)")
            print(f"[*] 获取数据: {GREEN}{len(all_results):,}{RESET} 条 (覆盖率 ~{percent}%)")
            print(f"[*] 独立 IP: {CYAN}{len(unique_ips):,}{RESET}")

        count_stats = self.search(query, size=1, page=1, fields=fields, full=full)
        total_quota_used += 1
        total_estimated = count_stats.total

        time.sleep(api_rate_limit)

        if total_estimated == 0:
            print("  [*] 无匹配数据")
            return SearchStats(total=0, unique_ips=0, results=[])

        target_count = int(total_estimated * fill_percent)
        print(f"\n[*] 匹配总量: {total_estimated:,} | 目标: {target_count:,} ({int(fill_percent*100)}%)")
        print()
        print_progress("开始...")

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
                total_quota_used += 10000

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
                    percent = len(all_results) / total_estimated * 100
                    print(f"\r[*] {GREEN}已达{int(fill_percent*100)}%目标{RESET} ({len(all_results):,}/{total_estimated:,})    ")
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
                    before_time = None

                time.sleep(api_rate_limit)

                if max_size > 0 and len(all_results) >= max_size:
                    break
        except KeyboardInterrupt:
            interrupted = True
            print()
            print(f"[*] 已中断，保存已获取的数据...")

        if interrupted:
            print(f"[*] 获取数据: {GREEN}{len(all_results):,}{RESET} 条")
            print(f"[*] 独立 IP: {CYAN}{len(unique_ips):,}{RESET}")
        else:
            print_done()
        return SearchStats(total=len(all_results), unique_ips=len(unique_ips), results=all_results)


# ============ 导出相关 ============

def export_csv(results: list[FofaResult], output_path: Path, fields: Optional[str] = None, dedup_field: Optional[str] = None) -> int:
    """导出为 CSV 文件"""
    if not results:
        return 0

    results = dedup_results(results, fields, dedup_field)

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


def export_json(results: list[FofaResult], output_path: Path, fields: Optional[str] = None, dedup_field: Optional[str] = None) -> int:
    """导出为 JSON 文件"""
    if not results:
        return 0

    results = dedup_results(results, fields, dedup_field)

    data = []
    for r in results:
        d = r.to_dict()
        d = {k: v for k, v in d.items() if v != "" and v is not None}
        data.append(d)
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
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


def dedup_results(results: list[FofaResult], fields: Optional[str], dedup_field: Optional[str] = None) -> list[FofaResult]:
    """去重"""
    user_fields = set(f.strip() for f in (fields or "").split(",") if f.strip())

    if dedup_field:
        dedup_fields = set(f.strip() for f in dedup_field.split(",") if f.strip())
    else:
        dedup_fields = user_fields

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
        key = tuple(key_tuple)
        if any(key_tuple) and key not in seen:
            seen.add(key)
            unique_results.append(r)
    return unique_results


def export_txt(results: list[FofaResult], output_path: Path, fields: Optional[str] = None, dedup_field: Optional[str] = None) -> int:
    """导出为 TXT 文件（URL/IP/Domain 列表）"""
    if not results:
        return 0

    results = dedup_results(results, fields, dedup_field)

    user_fields = set(f.strip() for f in (fields or "").split(",") if f.strip())

    if user_fields == {"ip"}:
        output_type = "ip"
    elif user_fields == {"domain"}:
        output_type = "domain"
    else:
        output_type = "url"

    count = 0
    with output_path.open("w", encoding="utf-8", newline="\n") as f:
        for r in results:
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
                    if r.host.startswith("http"):
                        f.write(f"{r.host}\n")
                    else:
                        protocol = r.protocol or "http"
                        if r.port and r.port not in ("80", "443"):
                            f.write(f"{protocol}://{r.host}:{r.port}\n")
                        else:
                            f.write(f"{protocol}://{r.host}\n")
                    count += 1
                elif r.ip:
                    f.write(f"{r.ip}\n")
                    count += 1

    return count


# ============ 主函数 ============

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
    parser.add_argument("-b", "--batch", dest="batch_file", metavar="FILE", help="批量查询文件，每行一个查询语句")
    parser.add_argument("--fill", type=float, default=0.8, help="多次查询完成百分比（0.0-1.0），仅 -l>10000 或 max 时生效")
    parser.add_argument("-csv", action="store_true", help="导出 CSV 格式")
    parser.add_argument("-txt", action="store_true", help="导出 TXT 格式（URL 列表）")
    parser.add_argument("-json", action="store_true", help="导出 JSON 格式")
    parser.add_argument("-f", "--fields", help="查询字段，控制 FOFA API 返回哪些字段及导出字段，默认 host,ip,port,protocol", default="host,ip,port,protocol")
    parser.add_argument("--dedup", help="根据指定字段去重，多个字段用逗号分隔，如 --dedup ip 或 --dedup ip,host")
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

    # 批量查询模式
    if args.batch_file:
        try:
            batch_queries = load_batch_queries(Path(args.batch_file))
            print(f"[*] 批量模式: 已加载 {len(batch_queries)} 个查询")

            if not any([args.csv, args.txt, args.json]):
                args.csv = True

            if not args.output:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                if args.json:
                    args.output = f"fofa_batch_{timestamp}.json"
                elif args.txt:
                    args.output = f"fofa_batch_{timestamp}.txt"
                else:
                    args.output = f"fofa_batch_{timestamp}.csv"

            all_results = run_batch_search(client, batch_queries, args)
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

    # 没有查询语句时显示 usage
    if not args.query:
        sys.stderr.write(parser.format_usage())
        sys.exit(1)

    # 没有指定格式时，默认导出 CSV
    if not any([args.csv, args.txt, args.json]):
        args.csv = True

    # 没有指定输出文件名时自动生成
    if not args.output:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if args.json:
            args.output = f"fofa_results_{timestamp}.json"
        elif args.txt:
            args.output = f"fofa_results_{timestamp}.txt"
        else:
            args.output = f"fofa_results_{timestamp}.csv"

    # 执行查询
    results = None
    try:
        limit_str = str(args.limit)
        is_max = limit_str.lower() == "max"
        limit_value = 0 if is_max else int(limit_str)

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


def load_batch_queries(file_path: Path) -> list[tuple[str, int]]:
    """
    加载批量查询文件

    Args:
        file_path: 批量查询文件路径

    Returns:
        [(查询语句, 行号), ...]
    """
    if not file_path.exists():
        raise FileNotFoundError(f"批量查询文件不存在: {file_path}")

    queries = []
    for line_no, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        queries.append((line, line_no))

    if not queries:
        raise ValueError("批量查询文件中没有有效的查询语句")

    return queries


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
    bar_width = 30

    for idx, (query, line_no) in enumerate(queries, 1):
        query = query.strip()
        if not query:
            continue

        print(f"\n{CYAN}[{idx}/{total_queries}] 第 {line_no} 行查询:{RESET} {query}")

        try:
            limit_str = str(args.limit)
            is_max = limit_str.lower() == "max"
            limit_value = 0 if is_max else int(limit_str)

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

    if args.csv:
        csv_path = unique_path(output_path)
        count = export_csv(results, csv_path, fields=args.fields, dedup_field=args.dedup)
        print(f"[+] 已导出 CSV: {csv_path} ({count} 条)")
        exported += 1

    if args.txt:
        txt_path = unique_path(output_path)
        count = export_txt(results, txt_path, fields=args.fields, dedup_field=args.dedup)
        print(f"[+] 已导出 TXT: {txt_path} ({count} 条)")
        exported += 1

    if args.json:
        json_path = unique_path(output_path)
        count = export_json(results, json_path, fields=args.fields, dedup_field=args.dedup)
        print(f"[+] 已导出 JSON: {json_path} ({count} 条)")
        exported += 1

    if exported == 0:
        print("[-] 没有导出任何文件（请指定输出格式）")


if __name__ == "__main__":
    main()
