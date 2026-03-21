#!/usr/bin/env python3
"""
FOFA 查询工具 - 单文件工具

用法:
    python fofaoutput.py "protocol=http"                    # 基本查询
    python fofaoutput.py "domain=baidu.com" -o results      # 指定输出文件名
    python fofaoutput.py "ip=1.1.1.1/24" --json             # 输出 JSON 格式
    python fofaoutput.py "port=80,443" -l 100               # 指定返回数量
"""

import argparse
import json
import csv
import os
import sys
import base64
import time
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional


# ============ Banner ============

BANNER = r"""
    ____  ______________________  ___________
   / __ \/ ____/ ____/_  __/ __ \/ ____/ ___/
  / /_/ / __/ / __/   / / / /_/ / __/  \__ \
 / _, _/ /___/ /___  / / / _, _/ /___ ___/ /
/_/ |_/_____/_____/ /_/ /_/ |_/_____//____/

    ____  ___________ __________  ___________
   / __ \/ __ \__  __/_  __/ __ \/ ____/ ___/
  / /_/ / /_/ / / /   / / / /_/ / __/  \__ \
 / _, _/ _, _/ / /   / / / _, _/ /___ ___/ /
/_/ |_/_/ |_| /_/   /_/ /_/ |_/_____//____/

        FOFA Query Tool v1.0
        https://fofa.info
"""


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

    # 自动生成默认配置文件
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
    host: str
    ip: str
    port: str
    protocol: str
    domain: str = ""
    title: str = ""
    server: str = ""
    country: str = ""
    city: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


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
            import urllib.request
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
            import urllib.request
            resp = urllib.request.urlopen(api_url, timeout=10)
            data = json.loads(resp.read().decode())
            if data.get("error"):
                raise FofaAPIError(f"获取用量失败: {data.get('errmsg', '未知错误')}")
            return data.get("data", {})
        except Exception as e:
            raise FofaAPIError(f"获取用量失败: {e}")

    def search(
        self,
        query: str,
        size: int = 100,
        skip: int = 0,
        fields: Optional[str] = None,
    ) -> list[FofaResult]:
        """
        执行 FOFA 查询

        Args:
            query: FOFA 查询语句
            size: 返回数量（最大 10000）
            skip: 跳过前 N 条结果
            fields: 返回字段，默认为 host,ip,port,protocol,domain,title,server,country,city

        Returns:
            结果列表
        """
        if fields is None:
            fields = "host,ip,port,protocol,domain,title,server,country,city"

        qbase64 = base64.b64encode(query.encode()).decode()
        url = (
            f"{self.base_url}/api/v1/search/all"
            f"?key={self.key}"
            f"&qbase64={qbase64}&size={size}&skip={skip}&fields={fields}"
        )

        try:
            import urllib.request
            resp = urllib.request.urlopen(url, timeout=30)
            data = json.loads(resp.read().decode())
        except Exception as e:
            raise FofaAPIError(f"请求失败: {e}")

        if data.get("error"):
            raise FofaAPIError(f"API 错误: {data.get('errmsg', '未知错误')}")

        results = []
        for item in data.get("results", []):
            # fields 顺序与 fields 参数一致
            result = FofaResult(
                host=item[0] if len(item) > 0 else "",
                ip=item[1] if len(item) > 1 else "",
                port=item[2] if len(item) > 2 else "",
                protocol=item[3] if len(item) > 3 else "",
                domain=item[4] if len(item) > 4 else "",
                title=item[5] if len(item) > 5 else "",
                server=item[6] if len(item) > 6 else "",
                country=item[7] if len(item) > 7 else "",
                city=item[8] if len(item) > 8 else "",
            )
            results.append(result)

        return results

    def search_all(self, query: str, max_size: int = 1000, page_size: int = 100) -> list[FofaResult]:
        """
        查询所有结果（自动分页）

        Args:
            query: FOFA 查询语句
            max_size: 最大返回数量
            page_size: 每页数量

        Returns:
            所有结果列表
        """
        all_results = []
        skip = 0

        while skip < max_size:
            batch_size = min(page_size, max_size - skip)
            results = self.search(query, size=batch_size, skip=skip)

            if not results:
                break

            all_results.extend(results)
            skip += len(results)

            # 避免请求过快
            time.sleep(0.5)

            # 如果返回数量小于请求数量，说明没有更多数据了
            if len(results) < batch_size:
                break

        return all_results


# ============ 导出相关 ============

def export_csv(results: list[FofaResult], output_path: Path) -> int:
    """导出为 CSV 文件"""
    if not results:
        return 0

    fieldnames = ["host", "ip", "port", "protocol", "domain", "title", "server", "country", "city"]

    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(r.to_dict())

    return len(results)


def export_txt(results: list[FofaResult], output_path: Path) -> int:
    """导出为 TXT 文件（URL 列表）"""
    if not results:
        return 0

    count = 0
    with output_path.open("w", encoding="utf-8", newline="\n") as f:
        for r in results:
            protocol = r.protocol or "http"
            if r.host:
                if r.port and r.port not in ("80", "443"):
                    url = f"{protocol}://{r.host}:{r.port}"
                else:
                    url = f"{protocol}://{r.host}"
                f.write(f"{url}\n")
                count += 1
            elif r.ip:
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

def main():
    # 检查是否显示帮助（帮助时不显示 banner）
    if "-h" in sys.argv or "--help" in sys.argv:
        parser = argparse.ArgumentParser(
            description="FOFA 查询工具",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=__doc__,
        )
        parser.parse_args()
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
            print(f"[*] 用户: {user_info.get('username', 'N/A')}")
            print(f"[*] 套餐: {user_info.get('vip_level', 'N/A')}")
            print(f"[*] 剩余积分: {user_info.get('remain_points', 'N/A')}")
            print(f"[*] 今日已用: {user_info.get('daily_used', 'N/A')}")
            print(f"[*] 今日限额: {user_info.get('daily_limit', 'N/A')}")
            print()
    except FofaAPIError as e:
        print(f"[!] 用量检查失败: {e}", file=sys.stderr)

    parser = argparse.ArgumentParser(
        description="FOFA 查询工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # 查询语句（位置参数）
    parser.add_argument("query", nargs="?", help="FOFA 查询语句，如: domain=baidu.com")

    # 输出相关
    parser.add_argument(
        "-o", "--output",
        help="输出文件名（不含后缀），默认为 fofa_results",
        default="fofa_results"
    )

    # 数量限制
    parser.add_argument(
        "-l", "--limit",
        type=int,
        help="最大返回数量，默认 100",
        default=100
    )
    parser.add_argument(
        "-a", "--all",
        action="store_true",
        help="查询所有结果（可能很慢）",
    )

    # 输出格式
    parser.add_argument(
        "--csv",
        action="store_true",
        help="导出 CSV 格式",
    )
    parser.add_argument(
        "--txt",
        action="store_true",
        help="导出 TXT 格式（URL 列表）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="导出 JSON 格式",
    )

    # 其他
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="显示详细信息",
    )

    args = parser.parse_args()

    # 如果没有指定格式，默认全部导出
    if not any([args.csv, args.txt, args.json]):
        args.csv = args.txt = args.json = True

    # 没有查询语句时显示帮助
    if not args.query:
        parser.print_help()
        sys.exit(1)

    # 执行查询
    try:
        if args.verbose:
            print(f"[*] 查询: {args.query}")
            print(f"[*] 数量限制: {'无限制' if args.all else args.limit}")

        if args.all:
            results = client.search_all(args.query, max_size=10000)
        else:
            results = client.search(args.query, size=args.limit)

        if args.verbose:
            print(f"[*] 找到 {len(results)} 条结果")

        if not results:
            print("[-] 没有找到结果")
            sys.exit(0)

        # 导出文件
        output_path = Path(args.output)
        exported = 0

        if args.csv:
            csv_path = output_path.with_suffix(".csv")
            count = export_csv(results, csv_path)
            print(f"[+] 已导出 CSV: {csv_path} ({count} 条)")
            exported += 1

        if args.txt:
            txt_path = output_path.with_suffix(".txt")
            count = export_txt(results, txt_path)
            print(f"[+] 已导出 TXT: {txt_path} ({count} 条)")
            exported += 1

        if args.json:
            json_path = output_path.with_suffix(".json")
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
