#!/usr/bin/env python3
"""fofatoto 单元测试 — 仅标准库 unittest，覆盖纯函数与关键路径。

运行: python -m unittest test_fofatoto -v
（在本文件所在目录执行；不发起任何真实网络请求，FOFA API 通过
monkeypatch urlopen 模拟。）
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import fofatoto


def make_result(**kwargs) -> fofatoto.FofaResult:
    return fofatoto.FofaResult(**kwargs)


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()


class FieldConstantsTest(unittest.TestCase):
    """字段清单单一来源（ALL_FIELD_NAMES/KNOWN_FIELDS/CUSTOM_FIELDS）"""

    def test_all_field_names_matches_dataclass(self):
        expected = [
            n for n in fofatoto.FofaResult.__dataclass_fields__ if n != "_extra"
        ]
        self.assertEqual(fofatoto.ALL_FIELD_NAMES, expected)
        self.assertEqual(fofatoto.ALL_FIELD_NAMES[0], "host")
        self.assertEqual(len(fofatoto.ALL_FIELD_NAMES), 28)

    def test_known_fields_is_frozenset(self):
        self.assertIsInstance(fofatoto.KNOWN_FIELDS, frozenset)
        self.assertEqual(fofatoto.KNOWN_FIELDS, frozenset(fofatoto.ALL_FIELD_NAMES))
        self.assertEqual(fofatoto.CUSTOM_FIELDS, frozenset({"url"}))

    def test_web_categories_validation_catches_drift(self):
        import copy

        saved = copy.deepcopy(fofatoto.WEB_FIELD_CATEGORIES)
        try:
            fofatoto.WEB_FIELD_CATEGORIES.append({"name": "x", "fields": ["bogus"]})
            with self.assertRaises(ValueError):
                fofatoto._validate_web_field_categories()
            fofatoto.WEB_FIELD_CATEGORIES.pop()
            fofatoto.WEB_FIELD_CATEGORIES[0]["fields"].append("bogus2")
            with self.assertRaises(ValueError):
                fofatoto._validate_web_field_categories()
        finally:
            fofatoto.WEB_FIELD_CATEGORIES[:] = saved


class FieldHelpersTest(unittest.TestCase):
    def test_field_names(self):
        self.assertEqual(fofatoto._field_names("a, b,,c"), ["a", "b", "c"])
        self.assertEqual(fofatoto._field_names(""), [])

    def test_append_missing_fields(self):
        self.assertEqual(
            fofatoto._append_missing_fields("ip", ["host", "ip"]), "ip,host"
        )
        self.assertEqual(fofatoto._append_missing_fields("", ["host"]), "host")
        self.assertEqual(fofatoto._append_missing_fields("host,ip", ["ip"]), "host,ip")

    def test_api_fields_strips_url_and_backfills(self):
        # url 剥离 + 拼接所需字段补齐
        self.assertEqual(
            fofatoto._api_fields("url,ip"), "ip,host,port,protocol"
        )
        # 已含所需字段时只剥离 url
        self.assertEqual(
            fofatoto._api_fields("ip,port,url,host,protocol"),
            "ip,port,host,protocol",
        )

    def test_api_fields_noop_without_url(self):
        self.assertEqual(fofatoto._api_fields("ip,port"), "ip,port")

    def test_infer_domain_from_host(self):
        self.assertEqual(fofatoto._infer_domain_from_host("baidu.com"), "baidu.com")
        self.assertEqual(fofatoto._infer_domain_from_host("www.a.com:8080"), "www.a.com")
        self.assertEqual(fofatoto._infer_domain_from_host("https://x.y.com/path"), "x.y.com")
        self.assertEqual(fofatoto._infer_domain_from_host("1.2.3.4"), "")
        self.assertEqual(fofatoto._infer_domain_from_host("1.2.3.4:443"), "")


class RelayDetectTest(unittest.TestCase):
    def test_standard_fofa_returns_empty(self):
        self.assertEqual(fofatoto._detect_relay_info_api("https://fofa.info", "k"), "")

    def test_relay_domain_match(self):
        self.assertEqual(
            fofatoto._detect_relay_info_api("https://fafaapi.info", "k"),
            "https://fafaapi.info/fofaapi/v1/validate-key?key=k",
        )

    def test_relay_subdomain_suffix_match(self):
        self.assertEqual(
            fofatoto._detect_relay_info_api("https://api.fafaapi.info/", "k"),
            "https://api.fafaapi.info/fofaapi/v1/validate-key?key=k",
        )

    def test_relay_key_url_encoded(self):
        url = fofatoto._detect_relay_info_api("https://fafaapi.info", "a+b=c")
        self.assertIn("key=a%2Bb%3Dc", url)


class BuildUrlTest(unittest.TestCase):
    def test_empty_host(self):
        self.assertEqual(fofatoto.build_url(make_result()), "")

    def test_http_prefix_passthrough(self):
        self.assertEqual(
            fofatoto.build_url(make_result(host="http://x.com")), "http://x.com"
        )

    def test_default_port_omitted(self):
        r = make_result(host="1.2.3.4", port="80", protocol="http")
        self.assertEqual(fofatoto.build_url(r), "http://1.2.3.4")

    def test_port_appended(self):
        r = make_result(host="1.2.3.4", port="8080")
        self.assertEqual(fofatoto.build_url(r), "http://1.2.3.4:8080")

    def test_https_port_inference(self):
        for port in ("443", "8443", "4443"):
            r = make_result(host="a.com", port=port)
            expected = "https://a.com" if port == "443" else f"https://a.com:{port}"
            self.assertEqual(fofatoto.build_url(r), expected)

    def test_host_already_has_port(self):
        r = make_result(host="example.com:8080", port="8080", protocol="http")
        self.assertEqual(fofatoto.build_url(r), "http://example.com:8080")

    def test_dirty_protocol_takes_first(self):
        r = make_result(host="a.com", port="80", protocol="http,https")
        self.assertEqual(fofatoto.build_url(r), "http://a.com")


class DedupTest(unittest.TestCase):
    def test_dedup_by_user_fields(self):
        rows = [make_result(host="a", ip="1"), make_result(host="a", ip="2")]
        out = fofatoto.dedup_results(rows, fields="host")
        self.assertEqual(len(out), 1)

    def test_dedup_by_explicit_field(self):
        rows = [make_result(host="a", ip="1"), make_result(host="b", ip="1")]
        out = fofatoto.dedup_results(rows, fields="host,ip", dedup_field="ip")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].host, "a")

    def test_dedup_by_url(self):
        rows = [make_result(host="a.com", port="80"), make_result(host="a.com", port="80")]
        out = fofatoto.dedup_results(rows, fields="url", dedup_field="url")
        self.assertEqual(len(out), 1)

    def test_dedup_by_extra_field(self):
        same_a = make_result(host="a")
        same_b = make_result(host="b")
        other = make_result(host="c")
        same_a._extra["fid"] = "one"
        same_b._extra["fid"] = "one"
        other._extra["fid"] = "two"
        out = fofatoto.dedup_results(
            [same_a, same_b, other], fields="host", dedup_field="fid"
        )
        self.assertEqual([r.host for r in out], ["a", "c"])

    def test_dedup_extra_does_not_collapse_known_field(self):
        a = make_result(host="a", ip="1")
        b = make_result(host="b", ip="2")
        a._extra["fid"] = "same"
        b._extra["fid"] = "same"
        out = fofatoto.dedup_results([a, b], fields="ip", dedup_field="ip")
        self.assertEqual(len(out), 2)

    def test_no_dedup_fields_returns_all(self):
        rows = [make_result(host="a"), make_result(host="a")]
        out = fofatoto.dedup_results(rows, fields="")
        self.assertEqual(len(out), 2)


class MergeDedupFieldsTest(unittest.TestCase):
    def test_appends_missing(self):
        self.assertEqual(fofatoto._merge_dedup_fields("ip,port", "ip,host"), "ip,port,host")

    def test_noop_when_covered(self):
        self.assertEqual(fofatoto._merge_dedup_fields("ip,host", "ip"), "ip,host")

    def test_no_dedup(self):
        self.assertEqual(fofatoto._merge_dedup_fields("ip", None), "ip")


class ParseLimitTest(unittest.TestCase):
    def test_plain_number(self):
        self.assertEqual(fofatoto.parse_limit_value("100"), (False, 100))

    def test_max(self):
        self.assertEqual(fofatoto.parse_limit_value("max"), (True, 0))
        self.assertEqual(fofatoto.parse_limit_value("MAX"), (True, 0))

    def test_invalid(self):
        for bad in ("abc", "0", "-5", "1.5"):
            with self.assertRaises(ValueError):
                fofatoto.parse_limit_value(bad)


class PlaceholderTest(unittest.TestCase):
    def test_expand_placeholder_query(self):
        out = fofatoto.expand_placeholder_query("host={}", ["a.com", "b.com"], "{}")
        self.assertEqual(out, [("host=a.com", 1), ("host=b.com", 2)])

    def test_load_batch_targets(self):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("# comment\n\na.com\n  b.com  \n")
            path = Path(f.name)
        try:
            targets = fofatoto.load_batch_targets(path)
            self.assertEqual(targets, [("a.com", 3), ("b.com", 4)])
        finally:
            path.unlink(missing_ok=True)

    def test_load_batch_targets_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            fofatoto.load_batch_targets(Path("Z:/nonexistent/xx.txt"))


class RetryHelpersTest(unittest.TestCase):
    def test_retryable_errors(self):
        for msg in ("[-501] 服务器内部错误", "timeout", "please try again later"):
            self.assertTrue(fofatoto._is_retryable_api_error(msg))

    def test_non_retryable(self):
        self.assertFalse(fofatoto._is_retryable_api_error("[-700] 无效key"))

    def test_retry_sleep_capped(self):
        err = fofatoto.FofaAPIError("[-501] 服务错误")
        self.assertEqual(fofatoto._retry_sleep_seconds(err, 99), 30)
        self.assertEqual(fofatoto._retry_sleep_seconds("other", 99), 8)


class SleepInterruptibleTest(unittest.TestCase):
    def test_immediate_cancel_raises(self):
        with self.assertRaises(KeyboardInterrupt):
            fofatoto._sleep_interruptible(10, lambda: True)

    def test_cancel_during_sleep(self):
        flag = {"v": False}
        import threading

        threading.Timer(0.3, lambda: flag.update(v=True)).start()
        t0 = time.monotonic()
        with self.assertRaises(KeyboardInterrupt):
            fofatoto._sleep_interruptible(30, lambda: flag["v"])
        self.assertLess(time.monotonic() - t0, 2)

    def test_plain_sleep_completes(self):
        t0 = time.monotonic()
        fofatoto._sleep_interruptible(0.05, lambda: False)
        self.assertGreaterEqual(time.monotonic() - t0, 0.04)


class RedactTest(unittest.TestCase):
    def test_secret_replaced(self):
        self.assertEqual(
            fofatoto._redact_sensitive("boom key=ABC123", "ABC123"), "boom key=***"
        )

    def test_key_pattern_redacted(self):
        self.assertEqual(
            fofatoto._redact_sensitive("http://x?key=SECRET&size=1", "other"),
            "http://x?key=***&size=1",
        )


class FofaResultTest(unittest.TestCase):
    def test_to_dict_drops_empty_known_fields(self):
        r = make_result(host="a.com")
        self.assertEqual(r.to_dict(), {"host": "a.com"})

    def test_to_dict_keeps_extra_even_if_empty(self):
        r = make_result(host="a.com")
        r._extra["custom"] = ""
        self.assertEqual(r.to_dict(), {"host": "a.com", "custom": ""})


class SearchUrlAndParseTest(unittest.TestCase):
    """search() 的 URL 编码与结果解析（模拟 urlopen，不发真实请求）"""

    def _search(self, fields, payload, **kwargs):
        captured = {}

        def fake_urlopen(url, timeout=None):
            captured["url"] = url
            return FakeResponse(payload)

        client = fofatoto.FofaClient("https://fofa.info", "abc+key=123")
        with mock.patch.object(urllib.request, "urlopen", fake_urlopen):
            stats = client.search('title="t+"', size=10, fields=fields, **kwargs)
        return captured["url"], stats

    def test_url_params_encoded(self):
        import base64
        from urllib.parse import parse_qs, urlparse

        url, _ = self._search(
            "ip,port,url",
            {"error": False, "size": 1, "results": [["1.1.1.1", "80", "a.com", "http"]]},
        )
        q = parse_qs(urlparse(url).query)
        self.assertEqual(q["key"][0], "abc+key=123")
        # qbase64 URL 解码后应还原为原始 base64，再解码还原查询语句
        self.assertEqual(base64.b64decode(q["qbase64"][0]).decode(), 'title="t+"')
        raw_plus = url.split("qbase64=", 1)[1].split("&", 1)[0]
        self.assertNotIn("+", raw_plus)  # 原始 URL 中无裸 +
        self.assertEqual(q["fields"][0], "ip,port,host,protocol")

    def test_result_parsing_and_domain_inference(self):
        _, stats = self._search(
            "host,domain,unknown_field",
            {"error": False, "size": 2, "results": [["a.com", "", "X"]]},
        )
        r = stats.results[0]
        self.assertEqual(r.host, "a.com")
        self.assertEqual(r.domain, "a.com")  # 由 host 推断
        self.assertEqual(r._extra["unknown_field"], "X")
        self.assertEqual(stats.total, 2)

    def test_short_row_pads_empty(self):
        _, stats = self._search(
            "ip,port", {"error": False, "size": 1, "results": [["1.1.1.1"]]}
        )
        self.assertEqual(stats.results[0].port, "")


class SearchRetryTest(unittest.TestCase):
    def test_api_error_raised_after_non_retryable(self):
        def fake_urlopen(url, timeout=None):
            return FakeResponse({"error": True, "errmsg": "[-700] 无效key"})

        client = fofatoto.FofaClient("https://fofa.info", "k")
        with mock.patch.object(urllib.request, "urlopen", fake_urlopen):
            with self.assertRaises(fofatoto.FofaAPIError) as ctx:
                client.search("q", fields="ip")
        self.assertIn("无效key", str(ctx.exception))

    def test_error_message_redacts_key(self):
        def fake_urlopen(url, timeout=None):
            raise OSError("conn to host SECRETKEY refused")

        client = fofatoto.FofaClient("https://fofa.info", "SECRETKEY")
        with mock.patch.object(urllib.request, "urlopen", fake_urlopen):
            with self.assertRaises(fofatoto.FofaAPIError) as ctx:
                client.search("q", fields="ip", max_retries=1)
        self.assertNotIn("SECRETKEY", str(ctx.exception))


class ExportTaskTest(unittest.TestCase):
    def _add_task(self, **overrides):
        task = fofatoto.ExportTask(task_id=overrides.pop("task_id", "t1"), **overrides)
        with fofatoto._export_lock:
            fofatoto._export_tasks[task.task_id] = task
        self.addCleanup(
            lambda: fofatoto._export_tasks.pop(task.task_id, None)
        )
        return task

    def test_running_task_guard(self):
        # 调用方须持有 _export_lock（与任务注册同一临界区）
        with fofatoto._export_lock:
            self.assertFalse(fofatoto._has_running_export_task())
        task = self._add_task(status="running")
        with fofatoto._export_lock:
            self.assertTrue(fofatoto._has_running_export_task())
        task.cancelled = True
        with fofatoto._export_lock:
            self.assertFalse(fofatoto._has_running_export_task())

    def test_done_task_not_counted(self):
        self._add_task(status="done")
        with fofatoto._export_lock:
            self.assertFalse(fofatoto._has_running_export_task())

    def test_finish_export_task_sets_fields_and_finished_at(self):
        self._add_task(status="running")
        fofatoto._finish_export_task("t1", "error", error="boom", progress=0.5)
        task = fofatoto._export_tasks["t1"]
        self.assertEqual(task.status, "error")
        self.assertEqual(task.error, "boom")
        self.assertEqual(task.progress, 0.5)
        self.assertGreater(task.finished_at, 0)

    def test_start_export_thread_failure_finishes_task(self):
        # start() 抛错（如线程资源耗尽）时，已注册的 running 任务必须
        # 被置为终态，否则会永久卡住并发守卫
        self._add_task(status="running")
        with mock.patch.object(
            fofatoto.threading.Thread, "start", side_effect=RuntimeError("no thread")
        ):
            with self.assertRaises(RuntimeError):
                fofatoto._start_export_thread("t1", lambda: None, ())
        task = fofatoto._export_tasks["t1"]
        self.assertEqual(task.status, "error")
        self.assertEqual(task.error, "任务线程启动失败")
        self.assertGreater(task.finished_at, 0)
        with fofatoto._export_lock:
            self.assertFalse(fofatoto._has_running_export_task())

    def test_cleanup_anchors_to_finished_at(self):
        # 运行超过 TTL 的长任务：完成后仍应保留满 30 分钟
        task = self._add_task(
            status="done", created_at=time.time() - 4000, finished_at=time.time() - 60
        )
        fofatoto._cleanup_export_tasks()
        self.assertIn("t1", fofatoto._export_tasks)
        task.finished_at = time.time() - 4000
        fofatoto._cleanup_export_tasks()
        self.assertNotIn("t1", fofatoto._export_tasks)

    def test_cleanup_removes_expired_and_files(self):
        fd, tmp_name = tempfile.mkstemp(suffix=".csv")
        os.close(fd)  # Windows 下句柄未关闭会阻止 unlink
        tmp = Path(tmp_name)
        tmp.write_text("x", encoding="utf-8")
        self._add_task(
            status="done", created_at=time.time() - 4000, output_files={"csv": str(tmp)}
        )
        fofatoto._cleanup_export_tasks()
        self.assertNotIn("t1", fofatoto._export_tasks)
        self.assertFalse(tmp.exists())

    def test_cleanup_keeps_fresh_tasks(self):
        self._add_task(status="done", created_at=time.time())
        fofatoto._cleanup_export_tasks()
        self.assertIn("t1", fofatoto._export_tasks)


class BatchPerTargetLimitTest(unittest.TestCase):
    def _run(self, task_id, max_size, search_side_effect=None, deep_side_effect=None):
        client = mock.Mock()
        if search_side_effect is not None:
            client.search.side_effect = search_side_effect
        if deep_side_effect is not None:
            client.search_all_efficient.side_effect = deep_side_effect
        handler = fofatoto.FofaWebHandler.__new__(fofatoto.FofaWebHandler)
        with fofatoto._export_lock:
            fofatoto._export_tasks[task_id] = fofatoto.ExportTask(
                task_id=task_id, kind="batch"
            )
        self.addCleanup(lambda: fofatoto._export_tasks.pop(task_id, None))
        with (
            mock.patch.object(handler, "_current_client", return_value=client),
            mock.patch.object(fofatoto, "_write_web_exports", return_value={"csv": "x"}),
            mock.patch.object(fofatoto, "_sleep_interruptible"),
        ):
            handler._run_batch_task(
                task_id,
                [("host=a.com", 1), ("host=b.com", 2)],
                "ip,port",
                0.8,
                max_size,
            )
        return client

    def _stats(self, query):
        return fofatoto.SearchStats(
            total=5000,
            unique_ips=1,
            results=[make_result(host=query, ip="1.1.1.1")],
        )

    def test_cap_within_single_request_uses_search(self):
        seen = []

        def fake_search(query, size=100, **kwargs):
            seen.append((query, size))
            return self._stats(query)

        client = self._run("batch-cap", 100, search_side_effect=fake_search)
        self.assertEqual(seen, [("host=a.com", 100), ("host=b.com", 100)])
        client.search_all_efficient.assert_not_called()
        task = fofatoto._export_tasks["batch-cap"]
        self.assertEqual(task.status, "done")
        self.assertEqual(task.fetched, 2)

    def test_unlimited_uses_deep_export(self):
        seen = []

        def fake_deep(query, max_size=0, **kwargs):
            seen.append((query, max_size))
            return self._stats(query)

        client = self._run("batch-deep", 0, deep_side_effect=fake_deep)
        self.assertEqual(seen, [("host=a.com", 0), ("host=b.com", 0)])
        client.search.assert_not_called()


class ExporterTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: [p.unlink(missing_ok=True) for p in self.tmpdir.iterdir()] or self.tmpdir.rmdir())
        self.results = [
            make_result(host="a.com", ip="1.1.1.1", port="80", protocol="http"),
            make_result(host="b.com", ip="2.2.2.2", port="443", protocol="https"),
        ]

    def test_export_csv_roundtrip(self):
        out = self.tmpdir / "x.csv"
        n = fofatoto.Exporter(self.results, fields="host,ip").export_csv(out)
        self.assertEqual(n, 2)
        text = out.read_text(encoding="utf-8-sig")
        lines = text.strip().splitlines()
        self.assertEqual(lines[0], "host,ip")
        self.assertEqual(lines[1], "a.com,1.1.1.1")

    def test_export_json_requested_fields(self):
        out = self.tmpdir / "x.json"
        fofatoto.Exporter(self.results, fields="host,ip").export_json(out)
        data = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(data, [
            {"host": "a.com", "ip": "1.1.1.1"},
            {"host": "b.com", "ip": "2.2.2.2"},
        ])

    def test_export_json_url_synthesis(self):
        out = self.tmpdir / "x.json"
        fofatoto.Exporter(self.results, fields="url").export_json(out)
        data = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(data[0]["url"], "http://a.com")
        self.assertEqual(data[1]["url"], "https://b.com")

    def test_export_txt_ip_mode(self):
        out = self.tmpdir / "x.txt"
        n = fofatoto.Exporter(self.results, fields="ip").export_txt(out)
        self.assertEqual(n, 2)
        self.assertEqual(out.read_text(encoding="utf-8"), "1.1.1.1\n2.2.2.2\n")

    def test_export_txt_domain_mode(self):
        out = self.tmpdir / "x.txt"
        r = make_result(host="x.com", domain="x.com")
        n = fofatoto.Exporter([r], fields="domain").export_txt(out)
        self.assertEqual(n, 1)
        self.assertEqual(out.read_text(encoding="utf-8"), "x.com\n")

    def test_export_txt_url_mode(self):
        out = self.tmpdir / "x.txt"
        n = fofatoto.Exporter(self.results, fields="host,ip,port").export_txt(out)
        self.assertEqual(n, 2)
        self.assertEqual(
            out.read_text(encoding="utf-8"), "http://a.com\nhttps://b.com\n"
        )

    def test_export_empty_results(self):
        out = self.tmpdir / "e.json"
        self.assertEqual(fofatoto.Exporter([], fields="ip").export_json(out), 0)
        self.assertEqual(out.read_text(encoding="utf-8"), "[]\n")


class WebHtmlRenderTest(unittest.TestCase):
    def test_placeholders_substituted(self):
        html = fofatoto.render_web_html()
        for ph in (
            "__APP_VERSION__",
            "__GITHUB_URL__",
            "__FIELD_CATEGORIES_JSON__",
            "__DEFAULT_FIELDS_JSON__",
        ):
            self.assertNotIn(ph, html)
        self.assertIn(f"v{fofatoto.APP_VERSION}", html)
        self.assertIn("var fieldCategories=", html)
        self.assertIn("function escAttr", html)  # 属性转义函数（buildRowsHtml 使用）
        self.assertIn("function sortValueCompare", html)  # 数值感知排序比较器
        self.assertIn("title=\"'+escAttr(h.query)+'\"", fofatoto.WEB_HTML_TEMPLATE)
        self.assertNotIn("title=\"'+escHtml(h.query)+'\"", fofatoto.WEB_HTML_TEMPLATE)
        self.assertIn("escHtml(d.remain_api_query||\"N/A\")", fofatoto.WEB_HTML_TEMPLATE)
        self.assertIn("escHtml(vipText)", fofatoto.WEB_HTML_TEMPLATE)
        # 批量模式与深度导出共用 exportPanel；只认 export 时面板会被 updateLayout 藏掉
        self.assertIn(
            '(currentMode==="export"||currentMode==="batch")&&panel.classList.contains("show")',
            fofatoto.WEB_HTML_TEMPLATE,
        )
        self.assertIn('id="batchMaxSize"', fofatoto.WEB_HTML_TEMPLATE)
        self.assertIn("max_size:maxSize", fofatoto.WEB_HTML_TEMPLATE)


class PlaceholderKeyTest(unittest.TestCase):
    def test_example_and_default_keys_are_not_configured(self):
        cm = fofatoto.ConfigManager()
        cm.url = "https://fofa.info"
        for key in (
            "your-fofa-key-here",
            "your-api-key",
            "your_fofa_api_key_here",
            "",
        ):
            cm.key = key
            self.assertFalse(cm.is_valid(), key)
        cm.key = "real-key"
        self.assertTrue(cm.is_valid())


class RequestBodyLimitTest(unittest.TestCase):
    def test_missing_and_zero(self):
        self.assertEqual(fofatoto._request_body_length(None), 0)
        self.assertEqual(fofatoto._request_body_length(""), 0)
        self.assertEqual(fofatoto._request_body_length("0"), 0)

    def test_accepts_normal_length(self):
        self.assertEqual(fofatoto._request_body_length("128"), 128)

    def test_rejects_negative_and_oversize_and_garbage(self):
        for bad in ("-1", str(fofatoto._MAX_REQUEST_BODY + 1), "nope"):
            with self.assertRaises(fofatoto.FofaAPIError):
                fofatoto._request_body_length(bad)


class WebExportPrivacyTest(unittest.TestCase):
    def test_export_files_written_and_restricted(self):
        files = fofatoto._write_web_exports("fofa_test_export", [], "ip")
        self.addCleanup(self._cleanup, files)
        self.assertEqual(set(files), {"csv", "json", "txt"})
        parent = Path(next(iter(files.values()))).parent
        self.assertEqual(parent.name, "fofa_web_exports")
        if os.name == "posix":
            self.assertEqual(parent.stat().st_mode & 0o777, 0o700)
            for path in files.values():
                self.assertEqual(Path(path).stat().st_mode & 0o777, 0o600)

    def _cleanup(self, files):
        for path in files.values():
            Path(path).unlink(missing_ok=True)


class VersionSyncTest(unittest.TestCase):
    """APP_VERSION / pyproject.toml / uv.lock 三处一致（AGENTS.md 约定）"""

    def test_versions_in_sync(self):
        root = Path(__file__).parent
        pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
        lock = (root / "uv.lock").read_text(encoding="utf-8")
        m_py = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M)
        m_lock = re.search(r'^version\s*=\s*"([^"]+)"', lock, re.M)
        self.assertIsNotNone(m_py)
        self.assertIsNotNone(m_lock)
        self.assertEqual(fofatoto.APP_VERSION, m_py.group(1))
        self.assertEqual(fofatoto.APP_VERSION, m_lock.group(1))


class FakeHTTPResponse:
    """图标抓取用 urlopen 返回替身（支持 with 上下文与 read(n)）"""

    def __init__(self, data: bytes, url: str, ctype: str = "text/html"):
        self._data = data
        self._url = url
        self.headers = {"Content-Type": ctype}

    def read(self, n: int = -1) -> bytes:
        return self._data if n is None or n < 0 else self._data[:n]

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class MurmurHashTest(unittest.TestCase):
    """纯 Python MurmurHash3 x86_32 与 icon_hash（对照 mmh3 输出的固定向量）"""

    VECTORS = [
        (b"", 0),
        (b"f", 728008763),
        (b"fo", 382126120),
        (b"foo", -156908512),
        (b"abcd", 1139631978),
        (b"abcde", -392455434),
        (b"abcdefgh", 1239272644),
    ]

    def test_murmur3_vectors(self):
        for data, expected in self.VECTORS:
            self.assertEqual(fofatoto._murmur3_32(data), expected, data)

    def test_favicon_hash_vectors(self):
        self.assertEqual(fofatoto.favicon_hash(b"f"), "1774577129")
        self.assertEqual(fofatoto.favicon_hash(b"fo"), "510855658")
        self.assertEqual(fofatoto.favicon_hash(b"foo"), "851989093")
        self.assertEqual(fofatoto.favicon_hash(b"abcd"), "1391944941")
        self.assertEqual(fofatoto.favicon_hash(b"abcde"), "-1251247445")
        self.assertEqual(fofatoto.favicon_hash(b"abcdefgh"), "1250291458")

    def test_favicon_hash_uses_newline_wrapped_base64(self):
        # Shodan/FOFA 约定：base64.encodebytes 产生 "Zm9v\n"（含换行），与 b64encode 的 "Zm9v" 哈希不同
        self.assertEqual(fofatoto.favicon_hash(b"foo"), str(fofatoto._murmur3_32(b"Zm9v\n")))
        self.assertNotEqual(fofatoto.favicon_hash(b"foo"), str(fofatoto._murmur3_32(b"Zm9v")))


class BuildIconQueryTest(unittest.TestCase):
    def test_without_extra(self):
        self.assertEqual(fofatoto.build_icon_query("-123"), 'icon_hash="-123"')

    def test_extra_or_never_escapes(self):
        self.assertEqual(
            fofatoto.build_icon_query("5", 'a="1" || b="2"'),
            'icon_hash="5" && (a="1" || b="2")',
        )


class IconLinkParserTest(unittest.TestCase):
    @staticmethod
    def parse(html):
        p = fofatoto._IconLinkParser()
        p.feed(html)
        p.close()
        return p.icon_href

    def test_shortcut_icon_wins(self):
        html = (
            '<link rel="apple-touch-icon" href="a.png">'
            '<link rel="icon" href="b.ico">'
            '<link rel="shortcut icon" href="c.ico">'
        )
        self.assertEqual(self.parse(html), "c.ico")

    def test_icon_over_apple_touch(self):
        html = '<link rel="apple-touch-icon" href="a.png"><link rel="icon" href="b.ico">'
        self.assertEqual(self.parse(html), "b.ico")

    def test_first_wins_same_rank(self):
        html = '<link rel="icon" href="first.ico"><link rel="icon" href="second.ico">'
        self.assertEqual(self.parse(html), "first.ico")

    def test_entity_in_href_decoded(self):
        self.assertEqual(self.parse('<link rel="icon" href="/i?a=1&amp;b=2">'), "/i?a=1&b=2")

    def test_ignores_non_icon(self):
        self.assertIsNone(self.parse('<link rel="stylesheet" href="s.css"><a href="x">y</a>'))
        self.assertIsNone(self.parse("<div>no links</div>"))


class DataUriAndSniffTest(unittest.TestCase):
    def test_decode_data_uri(self):
        self.assertEqual(fofatoto._decode_data_uri("data:image/png;base64,YQ=="), b"a")
        self.assertEqual(fofatoto._decode_data_uri("data:image/svg+xml,%3Csvg%3E"), b"<svg>")

    def test_decode_data_uri_invalid(self):
        # 严格校验：非法字符/截断/缺逗号/空内容/合法字串夹带非法字符显式报错，不再解出垃圾字节冒充成功
        for bad in (
            "data:image/png;base64,!!!",
            # 旧实现（未开 validate）会剥掉 !!! 后解出 b"hello" 冒充成功，此用例检测其回退
            "data:image/png;base64,!!!aGVsbG8=",
            "data:image/png;base64,Y",
            "data:image/png;base64",
            "data:image/png,",
        ):
            with self.assertRaises(fofatoto.IconExtractError):
                fofatoto._decode_data_uri(bad)
        self.assertIsNone(fofatoto._decode_data_uri("/relative.png"))

    def test_decode_data_uri_whitespace_tolerated(self):
        # 换行/空白先剥离再严格校验，合法 base64 不受影响
        b64 = base64.b64encode(b"icon-data").decode()
        wrapped = "\n".join(b64[i : i + 4] for i in range(0, len(b64), 4))
        self.assertEqual(fofatoto._decode_data_uri("data:image/png;base64," + wrapped), b"icon-data")

    def test_content_type_and_sniffing(self):
        self.assertEqual(fofatoto._guess_content_type(b"\x89PNG\r\n"), "image/png")
        self.assertEqual(fofatoto._guess_content_type(b"GIF89a"), "image/gif")
        self.assertEqual(fofatoto._guess_content_type(b"\xff\xd8\xff\xe0"), "image/jpeg")
        self.assertEqual(fofatoto._guess_content_type(b"RIFF\x00\x00\x00\x00WEBPVP8 "), "image/webp")
        self.assertEqual(fofatoto._guess_content_type(b"<svg xmlns=''></svg>"), "image/svg+xml")
        self.assertEqual(fofatoto._guess_content_type(b"\x00\x00\x01\x00rest"), "image/x-icon")
        self.assertTrue(fofatoto._looks_like_icon(b"\x89PNG\r\n", "application/octet-stream"))
        self.assertTrue(fofatoto._looks_like_icon(b"anything", "image/png"))
        self.assertTrue(fofatoto._looks_like_icon(b"<svg/>", ""))
        self.assertFalse(fofatoto._looks_like_icon(b"<!DOCTYPE html>rest", "text/html"))
        self.assertFalse(fofatoto._looks_like_icon(b"", ""))
        # 空响应体即使声明 image/* 也不是图标，避免产出空字节哈希
        self.assertFalse(fofatoto._looks_like_icon(b"", "image/png"))


class ResolveIconTest(unittest.TestCase):
    """resolve_icon 提取管线（monkeypatch urlopen，不发真实请求）"""

    PNG = b"\x89PNG\r\n\x1a\n" + b"rest-of-png"
    ICO = b"\x00\x00\x01\x00" + b"rest-of-ico"

    @staticmethod
    def _run(target, routes, allow_file=True, calls=None):
        def fake_urlopen(req, timeout=None, context=None):
            url = getattr(req, "full_url", req)
            if calls is not None:
                calls.append(url)
            val = routes.get(url)  # 精确匹配请求 URL，避免子串误路由
            if val is None:
                raise urllib.error.URLError("no route for " + url)
            if isinstance(val, Exception):
                raise val
            return val

        with mock.patch.object(urllib.request, "urlopen", fake_urlopen):
            return fofatoto.resolve_icon(target, allow_file=allow_file)

    def test_raw_hash_passthrough(self):
        calls = []
        info = self._run("-247388550", {}, calls=calls)
        self.assertEqual(info["icon_hash"], "-247388550")
        self.assertEqual(info["source"], "hash")
        self.assertEqual(info["icon_bytes"], b"")
        self.assertEqual(calls, [])

    def test_local_file(self):
        with tempfile.NamedTemporaryFile(suffix=".ico", delete=False) as fh:
            fh.write(self.ICO)
            path = fh.name
        try:
            info = self._run(path, {}, calls=[])
            self.assertEqual(info["source"], "file")
            self.assertEqual(info["icon_hash"], fofatoto.favicon_hash(self.ICO))
            self.assertEqual(info["icon_size"], len(self.ICO))
        finally:
            os.unlink(path)

    def test_local_file_read_oserror_wrapped_as_extract_error(self):
        # 文件占用/权限等 OSError 包装成 IconExtractError，调用方只需捕获这一种类型
        with tempfile.NamedTemporaryFile(suffix=".ico", delete=False) as fh:
            fh.write(self.ICO)
            path = fh.name
        try:
            with mock.patch.object(
                fofatoto.Path, "read_bytes", side_effect=PermissionError(13, "file locked")
            ):
                with self.assertRaises(fofatoto.IconExtractError) as cm:
                    self._run(path, {})
            self.assertIn("无法读取 icon 文件", str(cm.exception))
            self.assertIn("file locked", str(cm.exception))
        finally:
            os.unlink(path)

    def test_empty_local_file_rejected(self):
        # 零字节文件不产出空字节哈希（icon_hash="0"），与空响应体同规则
        with tempfile.NamedTemporaryFile(suffix=".ico", delete=False) as fh:
            path = fh.name
        try:
            with self.assertRaises(fofatoto.IconExtractError) as cm:
                self._run(path, {})
            self.assertIn("icon 文件为空", str(cm.exception))
        finally:
            os.unlink(path)

    def test_html_link_preferred_over_favicon_ico(self):
        routes = {
            "https://example.com": FakeHTTPResponse(
                b'<html><link rel="shortcut icon" href="/custom.png"></html>',
                "https://example.com/", "text/html",
            ),
            "https://example.com/custom.png": FakeHTTPResponse(
                self.PNG, "https://example.com/custom.png", "image/png"
            ),
        }
        info = self._run("https://example.com", routes)
        self.assertTrue(info["icon_url"].endswith("/custom.png"))
        self.assertEqual(info["icon_bytes"], self.PNG)
        self.assertEqual(info["icon_hash"], fofatoto.favicon_hash(self.PNG))

    def test_rel_priority_icon_over_apple_touch(self):
        routes = {
            "https://example.com": FakeHTTPResponse(
                b'<link rel="apple-touch-icon" href="a.png"><link rel="icon" href="b.png">',
                "https://example.com/", "text/html",
            ),
            "https://example.com/b.png": FakeHTTPResponse(
                self.PNG, "https://example.com/b.png", "image/png"
            ),
        }
        info = self._run("https://example.com", routes)
        self.assertTrue(info["icon_url"].endswith("/b.png"))

    def test_data_uri_link(self):
        b64 = base64.b64encode(self.PNG).decode()
        routes = {
            "https://example.com": FakeHTTPResponse(
                ('<link rel="icon" href="data:image/png;base64,%s">' % b64).encode(),
                "https://example.com/", "text/html",
            ),
        }
        info = self._run("https://example.com", routes)
        self.assertEqual(info["icon_url"], "(data: URI)")
        self.assertEqual(info["icon_bytes"], self.PNG)

    def test_favicon_ico_fallback(self):
        calls = []
        routes = {
            "https://example.com/favicon.ico": FakeHTTPResponse(
                self.ICO, "https://example.com/favicon.ico", "image/x-icon"
            ),
            "https://example.com": FakeHTTPResponse(b"<html>no icon</html>", "https://example.com/", "text/html"),
        }
        info = self._run("https://example.com", routes, calls=calls)
        self.assertTrue(info["icon_url"].endswith("/favicon.ico"))
        self.assertEqual(info["icon_bytes"], self.ICO)
        self.assertTrue(any("favicon.ico" in u for u in calls))

    def test_direct_image_url(self):
        routes = {
            "https://example.com/logo.ico": FakeHTTPResponse(
                self.ICO, "https://example.com/logo.ico", "image/x-icon"
            ),
        }
        info = self._run("https://example.com/logo.ico", routes)
        self.assertEqual(info["icon_bytes"], self.ICO)
        self.assertEqual(info["source"], "url")

    def test_https_falls_back_to_http(self):
        routes = {
            "https://bare-site.com": urllib.error.URLError("connection refused"),
            "http://bare-site.com": FakeHTTPResponse(self.PNG, "http://bare-site.com/icon.png", "image/png"),
        }
        info = self._run("bare-site.com", routes)
        self.assertTrue(info["icon_url"].startswith("http://bare-site.com"))
        self.assertEqual(info["icon_bytes"], self.PNG)

    def test_unsupported_scheme(self):
        with self.assertRaises(fofatoto.IconExtractError) as cm:
            self._run("ftp://example.com/x.ico", {}, allow_file=False)
        self.assertIn("仅支持 http/https", str(cm.exception))

    def test_allow_file_false_never_reads_local(self):
        with tempfile.NamedTemporaryFile(suffix=".ico", delete=False) as fh:
            fh.write(self.ICO)
            path = fh.name

        def fake_urlopen(req, timeout=None, context=None):
            raise urllib.error.URLError("network disabled")

        try:
            with mock.patch.object(urllib.request, "urlopen", fake_urlopen):
                with self.assertRaises(fofatoto.IconExtractError):
                    fofatoto.resolve_icon(path, allow_file=False)
        finally:
            os.unlink(path)

    def test_dns_error_classified(self):
        routes = {
            "https://does-not-exist.example": urllib.error.URLError(socket.gaierror(-2, "Name or service not known")),
        }
        with self.assertRaises(fofatoto.IconExtractError) as cm:
            self._run("does-not-exist.example", routes)
        self.assertIn("域名解析失败", str(cm.exception))

    def test_direct_image_uses_icon_limit_html_uses_html_limit(self):
        # PR #2 复核意见：2–5MB 直接图片按图标上限放行，HTML 单独施加小上限
        big_img = b"\x89PNG\r\n\x1a\n" + b"x" * 150
        big_html = b"<html>" + b"y" * 150 + b"</html>"
        routes = {
            "https://example.com/img.png": FakeHTTPResponse(big_img, "https://example.com/img.png", "image/png"),
            "https://example.com/page": FakeHTTPResponse(big_html, "https://example.com/page", "text/html"),
        }
        with mock.patch.object(fofatoto, "_MAX_HTML_BYTES", 100), mock.patch.object(
            fofatoto, "_MAX_ICON_BYTES", 1000
        ):
            info = self._run("https://example.com/img.png", routes)
            self.assertEqual(info["icon_size"], len(big_img))
            with self.assertRaises(fofatoto.IconExtractError) as cm:
                self._run("https://example.com/page", routes)
            self.assertIn("HTML 响应超过大小上限", str(cm.exception))

    def test_icon_fetch_limit_enforced(self):
        huge = b"\x00\x00\x01\x00" + b"x" * 200
        routes = {"https://example.com/logo.ico": FakeHTTPResponse(huge, "https://example.com/logo.ico", "image/x-icon")}
        with mock.patch.object(fofatoto, "_MAX_ICON_BYTES", 100):
            with self.assertRaises(fofatoto.IconExtractError) as cm:
                self._run("https://example.com/logo.ico", routes)
            self.assertIn("超过大小上限", str(cm.exception))

    def test_dead_link_falls_back_to_favicon_ico(self):
        calls = []
        routes = {
            "https://example.com": FakeHTTPResponse(
                b'<html><link rel="icon" href="/dead.png"></html>',
                "https://example.com/", "text/html",
            ),
            "https://example.com/dead.png": urllib.error.HTTPError(
                "https://example.com/dead.png", 404, "Not Found", None, None
            ),
            "https://example.com/favicon.ico": FakeHTTPResponse(
                self.ICO, "https://example.com/favicon.ico", "image/x-icon"
            ),
        }
        info = self._run("https://example.com", routes, calls=calls)
        self.assertIn("https://example.com/dead.png", calls)
        self.assertTrue(info["icon_url"].endswith("/favicon.ico"))
        self.assertEqual(info["icon_hash"], fofatoto.favicon_hash(self.ICO))

    def test_corrupted_data_uri_link_does_not_mint_garbage_hash(self):
        # 严格 base64 校验：损坏的 data URI 候选按失败走回退，而不是解出垃圾字节当成功。
        # 载荷取 "@@" + 合法 base64 + "@@"：未开 validate 的旧实现会剥掉 @ 后解出
        # junk 字节冒充成功（icon_url 为 "(data: URI)"），严格校验则报错走回退——
        # 端到端据此检测 validate=True 是否被回退。
        junk_b64 = base64.b64encode(b"junk-data").decode("ascii")
        routes = {
            "https://example.com": FakeHTTPResponse(
                b'<html><link rel="icon" href="data:image/png;base64,@@'
                + junk_b64.encode("ascii")
                + b'@@"></html>',
                "https://example.com/", "text/html",
            ),
            "https://example.com/favicon.ico": FakeHTTPResponse(
                self.ICO, "https://example.com/favicon.ico", "image/x-icon"
            ),
        }
        info = self._run("https://example.com", routes)
        self.assertTrue(info["icon_url"].endswith("/favicon.ico"))
        self.assertEqual(info["icon_hash"], fofatoto.favicon_hash(self.ICO))

    def test_html_parse_error_surfaced_in_final_error(self):
        class BoomParser(fofatoto._IconLinkParser):
            def feed(self, data):
                raise ValueError("boom")

        routes = {
            "https://example.com": FakeHTTPResponse(b"<html>x</html>", "https://example.com/", "text/html"),
            "https://example.com/favicon.ico": urllib.error.HTTPError(
                "https://example.com/favicon.ico", 404, "Not Found", None, None
            ),
        }
        with mock.patch.object(fofatoto, "_IconLinkParser", BoomParser):
            with self.assertRaises(fofatoto.IconExtractError) as cm:
                self._run("https://example.com", routes)
        msg = str(cm.exception)
        self.assertIn("HTML 解析失败", msg)
        self.assertIn("boom", msg)

    def test_empty_icon_response_rejected(self):
        # /favicon.ico 返回 200 空体时按失败处理，不产出空字节哈希
        routes = {
            "https://example.com": FakeHTTPResponse(b"<html>no icon</html>", "https://example.com/", "text/html"),
            "https://example.com/favicon.ico": FakeHTTPResponse(b"", "https://example.com/favicon.ico", "image/x-icon"),
        }
        with self.assertRaises(fofatoto.IconExtractError) as cm:
            self._run("https://example.com", routes)
        self.assertIn("页面未找到可用图标", str(cm.exception))
        self.assertIn("图标响应为空", str(cm.exception))

    def test_timeout_error_classified(self):
        routes = {"https://slow.example": socket.timeout("timed out")}
        with self.assertRaises(fofatoto.IconExtractError) as cm:
            self._run("slow.example", routes)
        self.assertIn("连接超时", str(cm.exception))

    def test_http_status_error_classified(self):
        routes = {
            "https://example.com": urllib.error.HTTPError(
                "https://example.com", 503, "Service Unavailable", None, None
            )
        }
        with self.assertRaises(fofatoto.IconExtractError) as cm:
            self._run("example.com", routes)
        self.assertIn("HTTP 503", str(cm.exception))


class IconCacheTest(unittest.TestCase):
    """resolve_icon_cached 不缓存原始 icon_bytes（PR #2 复核意见）"""

    def test_cache_strips_bytes_and_reuses_entry(self):
        png = b"\x89PNG\r\n\x1a\n" + b"payload"
        calls = []

        def fake_urlopen(req, timeout=None, context=None):
            calls.append(getattr(req, "full_url", req))
            return FakeHTTPResponse(png, "https://example.com/f.png", "image/png")

        fofatoto._ICON_CACHE.clear()
        try:
            with mock.patch.object(urllib.request, "urlopen", fake_urlopen):
                info = fofatoto.resolve_icon_cached("https://example.com/f.png")
                again = fofatoto.resolve_icon_cached("https://example.com/f.png")
        finally:
            fofatoto._ICON_CACHE.clear()
        self.assertNotIn("icon_bytes", info)
        self.assertNotIn("icon_data_uri", info)  # 预览字段无人消费，已移除
        self.assertEqual(info["icon_hash"], fofatoto.favicon_hash(png))
        self.assertEqual(again["icon_hash"], info["icon_hash"])
        self.assertEqual(len(calls), 1)

    def test_cache_evicts_oldest_at_max(self):
        png = b"\x89PNG\r\n\x1a\n" + b"payload"

        def fake_urlopen(req, timeout=None, context=None):
            return FakeHTTPResponse(png, "https://x.test/f.png", "image/png")

        fofatoto._ICON_CACHE.clear()
        try:
            with mock.patch.object(urllib.request, "urlopen", fake_urlopen), mock.patch.object(
                fofatoto, "_ICON_CACHE_MAX", 2
            ):
                for target in ("https://a.test", "https://b.test", "https://c.test"):
                    fofatoto.resolve_icon_cached(target)
                self.assertEqual(list(fofatoto._ICON_CACHE.keys()), ["https://b.test", "https://c.test"])
        finally:
            fofatoto._ICON_CACHE.clear()

    def test_failed_resolution_not_cached(self):
        # 瞬时失败不进缓存：下一条请求应重试而不是永久命中错误
        png = b"\x89PNG\r\n\x1a\n" + b"payload"
        state = {"fail": True}

        def fake_urlopen(req, timeout=None, context=None):
            if state["fail"]:
                raise urllib.error.URLError("transient outage")
            return FakeHTTPResponse(png, "https://y.test/f.png", "image/png")

        fofatoto._ICON_CACHE.clear()
        try:
            with mock.patch.object(urllib.request, "urlopen", fake_urlopen):
                with self.assertRaises(fofatoto.IconExtractError):
                    fofatoto.resolve_icon_cached("y.test")
                state["fail"] = False
                info = fofatoto.resolve_icon_cached("y.test")
                self.assertEqual(info["icon_hash"], fofatoto.favicon_hash(png))
                self.assertEqual(list(fofatoto._ICON_CACHE.keys()), ["y.test"])
        finally:
            fofatoto._ICON_CACHE.clear()


class ApiIconEndpointTest(unittest.TestCase):
    """_handle_icon 端点契约（__new__ + mock 响应通道，不起真实服务）"""

    @staticmethod
    def _handler(body):
        handler = fofatoto.FofaWebHandler.__new__(fofatoto.FofaWebHandler)
        sent = {}
        handler._read_body = mock.Mock(return_value=body)
        handler._send_json = mock.Mock(
            side_effect=lambda data, status=200: sent.update(json=data, status=status)
        )
        handler._send_error = mock.Mock(
            side_effect=lambda error, status=200, data=None: sent.update(error=error, status=status)
        )
        return handler, sent

    def test_missing_target_rejected(self):
        handler, sent = self._handler({})
        handler._handle_icon()
        handler._send_json.assert_not_called()
        self.assertEqual(sent["error"], "Target is required")

    def test_success_payload_contract(self):
        # 前端只读 data.icon_hash，字段缺失会被填成 icon_hash="undefined"，端点必须保证存在
        handler, sent = self._handler({"target": "https://example.com"})
        info = {
            "icon_hash": "-123",
            "icon_md5": "ab",
            "icon_url": "https://example.com/f.png",
            "icon_size": 5,
            "source": "url",
        }
        with mock.patch.object(fofatoto, "resolve_icon_cached", return_value=info):
            handler._handle_icon()
        handler._send_error.assert_not_called()
        self.assertTrue(sent["json"]["success"])
        for key in ("icon_hash", "icon_md5", "icon_url", "icon_size", "source"):
            self.assertIn(key, sent["json"]["data"])
        self.assertEqual(sent["json"]["data"]["icon_hash"], "-123")
        # 预览字段已随缓存瘦身移除，不得回潜
        self.assertNotIn("icon_data_uri", sent["json"]["data"])

    def test_extract_error_maps_to_error_response(self):
        handler, sent = self._handler({"target": "does-not-exist.example"})
        with mock.patch.object(
            fofatoto, "resolve_icon_cached", side_effect=fofatoto.IconExtractError("页面未找到可用图标")
        ):
            handler._handle_icon()
        handler._send_json.assert_not_called()
        self.assertIn("页面未找到可用图标", str(sent["error"]))

    def test_unexpected_exception_still_answers(self):
        handler, sent = self._handler({"target": "https://example.com"})
        with mock.patch.object(fofatoto, "resolve_icon_cached", side_effect=RuntimeError("boom")):
            handler._handle_icon()
        handler._send_json.assert_not_called()
        self.assertIn("boom", str(sent["error"]))

    def test_local_file_path_never_resolved_as_file(self):
        # 端点级不变量：Web 端 allow_file 硬编码 False，本地路径不得被读取后返回
        with tempfile.NamedTemporaryFile(suffix=".ico", delete=False) as fh:
            fh.write(b"\x00\x00\x01\x00local-secret")
            path = fh.name
        try:
            handler, sent = self._handler({"target": path})

            def fake_urlopen(req, timeout=None, context=None):
                raise urllib.error.URLError("network disabled")

            with mock.patch.object(urllib.request, "urlopen", fake_urlopen):
                handler._handle_icon()
            handler._send_json.assert_not_called()
            self.assertIsInstance(sent["error"], fofatoto.IconExtractError)
        finally:
            os.unlink(path)


class MainIconModeTest(unittest.TestCase):
    """--icon 与 -w/-b 互斥、以及 --icon 不落入 Web 模式（main 3237-3243 的守卫）"""

    def test_icon_conflicts_with_web_and_batch(self):
        # 缺密钥或缺批量文件也会 sys.exit(1)；必须看到互斥文案，两条臂才算守住。
        self.addCleanup(fofatoto._reset_update_check_state)
        for extra in (["-w"], ["-b", "targets.txt"]):
            with self.subTest(extra=extra):
                stderr = io.StringIO()
                argv = ["fofatoto.py", "--no-update-check", "--icon", "example.com", *extra]
                with (
                    mock.patch.object(sys, "argv", argv),
                    mock.patch.object(sys, "stderr", stderr),
                    mock.patch.object(fofatoto, "announce_update"),
                ):
                    with self.assertRaises(SystemExit) as cm:
                        fofatoto.main()
                self.assertEqual(cm.exception.code, 1)
                self.assertIn("不能同时使用", stderr.getvalue())

    def test_icon_mode_without_query_runs_icon_not_web(self):
        # 回归敏感行：web_mode 条件若丢掉 `and not args.icon`，--icon 会静默拉起 Web UI
        with (
            mock.patch.object(sys, "argv", ["fofatoto.py", "--icon", "example.com"]),
            mock.patch.object(fofatoto, "ConfigManager") as cm_cls,
            mock.patch.object(fofatoto, "print_account_status"),
            mock.patch.object(fofatoto, "handle_icon_mode") as him,
            mock.patch.object(fofatoto, "FofaWebServer") as server,
            mock.patch.object(fofatoto, "announce_update"),
        ):
            cm_cls.return_value.ensure_exists.return_value = True
            cm_cls.return_value.is_valid.return_value = True
            fofatoto.main()
        him.assert_called_once()
        server.assert_not_called()


class _ReleaseResponse:
    def __init__(self, body: bytes):
        self._body = body
        self._pos = 0
        self.status = 200

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            n = len(self._body) - self._pos
        chunk = self._body[self._pos : self._pos + n]
        self._pos += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class UpdateCheckTest(unittest.TestCase):
    """GitHub Releases 版本检查：比较、缓存、失败静默、Web 载荷。不发真实请求。"""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.cache_path = Path(self._tmpdir.name) / "update.json"
        self._cache_patch = mock.patch.object(
            fofatoto, "_update_cache_file", return_value=self.cache_path
        )
        self._cache_patch.start()
        fofatoto._reset_update_check_state()
        self.addCleanup(self._cache_patch.stop)
        self.addCleanup(self._tmpdir.cleanup)
        self.addCleanup(self._wait_and_reset)

    def _wait_and_reset(self):
        for _ in range(200):
            with fofatoto._update_lock:
                inflight = fofatoto._update_inflight
            if not inflight:
                break
            time.sleep(0.01)
        fofatoto._reset_update_check_state()

    def test_parse_and_compare_versions(self):
        self.assertEqual(fofatoto.parse_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(fofatoto.parse_version("1.2"), (1, 2))
        self.assertIsNone(fofatoto.parse_version("1.2.3-beta"))
        self.assertIsNone(fofatoto.parse_version("v1.2.3-rc1"))
        self.assertIsNone(fofatoto.parse_version(""))
        self.assertTrue(fofatoto.is_newer_version("1.10.0", "1.9.0"))
        self.assertTrue(fofatoto.is_newer_version("v1.8.0", "1.7.0"))
        self.assertFalse(fofatoto.is_newer_version("1.7", "1.7.0"))
        self.assertFalse(fofatoto.is_newer_version("1.6.9", "1.7.0"))
        self.assertFalse(fofatoto.is_newer_version("nope", "1.7.0"))

    def test_fetch_parses_release(self):
        body = json.dumps(
            {
                "tag_name": "v9.1.0",
                "html_url": "https://github.com/keyblues/fofatoto/releases/tag/v9.1.0",
                "draft": False,
                "prerelease": False,
            }
        ).encode()
        seen = {}

        def fake(req, timeout=None):
            seen["url"] = req.full_url
            seen["timeout"] = timeout
            seen["ua"] = req.get_header("User-agent")
            return _ReleaseResponse(body)

        with mock.patch.object(urllib.request, "urlopen", fake):
            found = fofatoto.fetch_latest_release(2.5)
        self.assertEqual(
            found,
            ("9.1.0", "https://github.com/keyblues/fofatoto/releases/tag/v9.1.0"),
        )
        self.assertIn("/repos/keyblues/fofatoto/releases/latest", seen["url"])
        self.assertEqual(seen["timeout"], 2.5)
        self.assertIn(f"fofatoto/{fofatoto.APP_VERSION}", seen["ua"])

    def test_fetch_rejects_prerelease_draft_and_bad_payloads(self):
        def respond(payload):
            def fake(req, timeout=None):
                return _ReleaseResponse(json.dumps(payload).encode())

            with mock.patch.object(urllib.request, "urlopen", fake):
                return fofatoto.fetch_latest_release()

        self.assertIsNone(respond({"tag_name": "v9.0.0", "prerelease": True}))
        self.assertIsNone(respond({"tag_name": "v9.0.0", "draft": True}))
        self.assertIsNone(respond({"tag_name": "nightly"}))
        self.assertIsNone(respond([]))

    def test_fetch_swallows_network_errors_and_oversized_body(self):
        def boom(req, timeout=None):
            raise urllib.error.URLError("offline")

        with mock.patch.object(urllib.request, "urlopen", boom):
            self.assertIsNone(fofatoto.fetch_latest_release())

        huge = b"{" + b"x" * (fofatoto.UPDATE_RESPONSE_LIMIT + 1)

        def oversized(req, timeout=None):
            return _ReleaseResponse(huge)

        with mock.patch.object(urllib.request, "urlopen", oversized):
            self.assertIsNone(fofatoto.fetch_latest_release())

    def test_untrusted_release_url_is_replaced(self):
        body = json.dumps(
            {
                "tag_name": "v9.1.0",
                "html_url": "https://evil.example/phish",
            }
        ).encode()

        def fake(req, timeout=None):
            return _ReleaseResponse(body)

        with mock.patch.object(urllib.request, "urlopen", fake):
            found = fofatoto.fetch_latest_release()
        self.assertEqual(
            found[1], "https://github.com/keyblues/fofatoto/releases/tag/v9.1.0"
        )

    def test_announce_prints_newer_version_and_uses_cache(self):
        url = "https://github.com/keyblues/fofatoto/releases/tag/v9.2.0"
        calls = {"n": 0}

        def fake(timeout=None):
            calls["n"] += 1
            return ("9.2.0", url)

        buf = io.StringIO()
        with mock.patch.object(fofatoto, "fetch_latest_release", fake):
            with mock.patch("sys.stdout", buf):
                fofatoto.announce_update(blocking=True)
                fofatoto.announce_update(blocking=True)
        text = buf.getvalue()
        self.assertIn("发现新版本 v9.2.0", text)
        self.assertIn(f"当前 v{fofatoto.APP_VERSION}", text)
        self.assertIn(url, text)
        self.assertEqual(calls["n"], 1)
        cached = json.loads(self.cache_path.read_text(encoding="utf-8"))
        self.assertEqual(cached["latest"], "9.2.0")
        self.assertTrue(cached["ok"])

    def test_current_version_is_silent(self):
        def fake(timeout=None):
            return (
                fofatoto.APP_VERSION,
                f"https://github.com/keyblues/fofatoto/releases/tag/v{fofatoto.APP_VERSION}",
            )

        buf = io.StringIO()
        with mock.patch.object(fofatoto, "fetch_latest_release", fake):
            with mock.patch("sys.stdout", buf):
                fofatoto.announce_update(blocking=True)
        self.assertNotIn("发现新版本", buf.getvalue())
        snap = fofatoto.snapshot_update()
        self.assertFalse(snap["update_available"])
        self.assertFalse(snap["pending"])

    def test_failure_is_cached_until_fail_ttl(self):
        clock = {"t": 1_700_000_000.0}
        calls = {"n": 0}

        def now():
            return clock["t"]

        def fake(timeout=None):
            calls["n"] += 1
            return None

        with (
            mock.patch.object(fofatoto.time, "time", now),
            mock.patch.object(fofatoto, "fetch_latest_release", fake),
        ):
            fofatoto.announce_update(blocking=True)
            fofatoto.announce_update(blocking=True)
            self.assertEqual(calls["n"], 1)
            clock["t"] += fofatoto.UPDATE_FAIL_TTL + 1
            fofatoto.announce_update(blocking=True)
            self.assertEqual(calls["n"], 2)

    def test_disk_cache_rewrites_untrusted_url(self):
        self.cache_path.write_text(
            json.dumps(
                {
                    "checked_at": time.time(),
                    "ok": True,
                    "latest": "9.9.0",
                    "url": "https://evil.example/phish",
                }
            ),
            encoding="utf-8",
        )
        with mock.patch.object(fofatoto, "fetch_latest_release") as fetch:
            snap = fofatoto.snapshot_update()
        fetch.assert_not_called()
        self.assertTrue(snap["update_available"])
        self.assertEqual(snap["latest"], "9.9.0")
        self.assertEqual(
            snap["url"], "https://github.com/keyblues/fofatoto/releases/tag/v9.9.0"
        )
        self.assertFalse(snap["pending"])

    def test_disabled_by_env_and_flag(self):
        with mock.patch.object(fofatoto, "fetch_latest_release") as fetch:
            with mock.patch.dict(os.environ, {"FOFATOTO_NO_UPDATE_CHECK": "1"}):
                fofatoto.announce_update(blocking=True)
                snap = fofatoto.snapshot_update()
            fetch.assert_not_called()
        self.assertFalse(snap["update_available"])
        self.assertFalse(snap["pending"])

        fofatoto.suppress_update_check()
        with mock.patch.object(fofatoto, "fetch_latest_release") as fetch:
            fofatoto.announce_update(blocking=True)
            fetch.assert_not_called()
        self.assertTrue(fofatoto.update_check_disabled())
        args = fofatoto.build_parser().parse_args(["--no-update-check"])
        self.assertTrue(args.no_update_check)

    def test_snapshot_pending_then_ready(self):
        started = threading.Event()
        release = threading.Event()
        url = "https://github.com/keyblues/fofatoto/releases/tag/v9.0.0"

        def fake(timeout=None):
            started.set()
            self.assertTrue(release.wait(2))
            return ("9.0.0", url)

        with mock.patch.object(fofatoto, "fetch_latest_release", fake):
            first = fofatoto.snapshot_update()
            self.assertTrue(first["pending"])
            self.assertFalse(first["update_available"])
            self.assertTrue(started.wait(1))
            release.set()
            snap = first
            deadline = time.time() + 2
            while time.time() < deadline:
                snap = fofatoto.snapshot_update()
                if not snap["pending"]:
                    break
                time.sleep(0.01)
        self.assertFalse(snap["pending"])
        self.assertTrue(snap["update_available"])
        self.assertEqual(snap["latest"], "9.0.0")
        self.assertEqual(snap["url"], url)

    def test_update_endpoint_and_route(self):
        handler = fofatoto.FofaWebHandler.__new__(fofatoto.FofaWebHandler)
        sent = {}
        handler._send_json = lambda data, status=200: sent.update(json=data, status=status)
        payload = {
            "current": fofatoto.APP_VERSION,
            "latest": "9.0.0",
            "update_available": True,
            "url": "https://github.com/keyblues/fofatoto/releases/tag/v9.0.0",
            "pending": False,
        }
        with mock.patch.object(fofatoto, "snapshot_update", return_value=payload):
            handler._handle_update()
        self.assertTrue(sent["json"]["success"])
        self.assertEqual(sent["json"]["data"]["latest"], "9.0.0")

        handler.path = "/api/update"
        handler._handle_update = mock.Mock()
        handler.do_GET()
        handler._handle_update.assert_called_once()

    def test_web_template_has_update_badge(self):
        html = fofatoto.render_web_html()
        self.assertIn('id="updateBadge"', html)
        self.assertIn('fetch("/api/update")', html)
        self.assertIn(f"{fofatoto.GITHUB_URL}/releases/", html)
        self.assertNotIn("__GITHUB_URL__", html)

    def test_no_update_check_flag_suppresses_before_web(self):
        with (
            mock.patch.object(sys, "argv", ["fofatoto.py", "--no-update-check"]),
            mock.patch.object(fofatoto, "ConfigManager") as cm_cls,
            mock.patch.object(fofatoto, "FofaWebServer") as server,
            mock.patch.object(fofatoto, "announce_update") as announce,
        ):
            cm_cls.return_value.ensure_exists.return_value = True
            cm_cls.return_value.is_valid.return_value = False
            fofatoto.main()
        self.assertTrue(fofatoto.update_check_disabled())
        server.return_value.start.assert_called_once()
        announce.assert_not_called()


def _plain_log(text: str) -> str:
    return re.sub(r"\033\[[0-9;]*m", "", text)


class WebAccessLogTest(unittest.TestCase):
    """Web UI 启动后的 CLI 访问日志：轮询与浏览器探测静默，操作与错误保留。"""

    def setUp(self):
        fofatoto._web_home_seen.clear()

    def _handler(self, method, path, peer="127.0.0.1"):
        handler = fofatoto.FofaWebHandler.__new__(fofatoto.FofaWebHandler)
        handler.command = method
        handler.path = path
        handler.client_address = (peer, 12345)
        return handler

    def _logged(self, handler, code=200, error=None):
        buf = io.StringIO()
        with mock.patch.object(sys, "stderr", buf):
            if error is None:
                handler.log_request(code)
            else:
                handler.log_error(*error)
        return _plain_log(buf.getvalue())

    def _at(self, method, target, code, peer="", clock="14:48:02"):
        return _plain_log(fofatoto._format_web_access(method, target, code, peer, clock))

    def test_access_line_aligns_method_path_and_status(self):
        search = self._at("GET", "/api/search", 200)
        home = self._at("POST", "/", 201)
        download = self._at("GET", "/api/export/download?format=csv", 200)
        self.assertEqual(
            search,
            "[web] 14:48:02  GET   /api/search               200\n",
        )
        self.assertEqual(search.index("200"), home.index("201"))
        self.assertIn("GET   /api/search", search)
        self.assertIn("POST  /", home)
        self.assertTrue(download.endswith("  200\n"))
        self.assertIn("/api/export/download?format=csv", download)
        self.assertGreater(download.index("200"), search.index("200"))

    def test_quiet_progress_polls_and_browser_probes(self):
        cases = [
            ("GET", "/api/progress?task_id=abc", 200),
            ("GET", "/favicon.ico", 404),
            ("GET", "/robots.txt", 404),
            ("GET", "/apple-touch-icon.png", 404),
            ("GET", "/json/version", 404),
            ("GET", "/json", 404),
            ("GET", "/json/list", 404),
            ("GET", "/devtools/page/1", 404),
            ("GET", "/.well-known/appspecific/com.chrome.devtools.json", 404),
        ]
        for method, path, code in cases:
            with self.subTest(path=path, code=code):
                self.assertEqual(self._logged(self._handler(method, path), code), "")

    def test_account_and_update_checks_are_logged_with_peer(self):
        info = self._logged(self._handler("GET", "/api/info"), 200)
        update = self._logged(self._handler("GET", "/api/update"), 200)
        self.assertEqual(info, self._at("GET", "/api/info", 200, "127.0.0.1", clock=info[6:14]))
        self.assertEqual(
            update, self._at("GET", "/api/update", 200, "127.0.0.1", clock=update[6:14])
        )

    def test_devtools_probe_error_still_logged(self):
        line = self._logged(self._handler("GET", "/json/version"), 500)
        self.assertIn("/json/version", line)
        self.assertIn("127.0.0.1", line)
        self.assertTrue(line.endswith("500  127.0.0.1\n"))

    def test_repeated_homepage_loads_collapse(self):
        handler = self._handler("GET", "/")
        times = iter([0.0, 1.0, 31.0])
        with mock.patch.object(fofatoto.time, "monotonic", side_effect=lambda: next(times)):
            first = self._logged(handler, 200)
            second = self._logged(handler, 200)
            third = self._logged(handler, 200)
        self.assertEqual(first, self._at("GET", "/", 200, "127.0.0.1", clock=first[6:14]))
        self.assertEqual(second, "")
        self.assertIn("GET   /", third)
        self.assertTrue(third.endswith("200  127.0.0.1\n"))

    def test_progress_error_still_logged(self):
        line = self._logged(
            self._handler("GET", "/api/progress?task_id=abc"), 500
        )
        self.assertEqual(
            line, self._at("GET", "/api/progress", 500, "127.0.0.1", clock=line[6:14])
        )
        self.assertNotIn("task_id", line)

    def test_user_actions_include_client_ip(self):
        page = self._logged(self._handler("GET", "/"), 200)
        search = self._logged(self._handler("POST", "/api/search"), 200)
        download = self._logged(
            self._handler(
                "GET", "/api/export/download?task_id=abc&format=csv"
            ),
            200,
        )
        self.assertEqual(page, self._at("GET", "/", 200, "127.0.0.1", clock=page[6:14]))
        self.assertEqual(
            search, self._at("POST", "/api/search", 200, "127.0.0.1", clock=search[6:14])
        )
        self.assertEqual(
            download,
            self._at(
                "GET",
                "/api/export/download?format=csv",
                200,
                "127.0.0.1",
                clock=download[6:14],
            ),
        )
        self.assertNotIn("task_id", download)

    def test_ipv6_loopback_is_kept(self):
        line = self._logged(self._handler("POST", "/api/icon", peer="::1"), 200)
        self.assertEqual(line, self._at("POST", "/api/icon", 200, "::1", clock=line[6:14]))
        self.assertTrue(line.endswith("  200  ::1\n"))

    def test_control_chars_do_not_break_the_line(self):
        line = self._logged(self._handler("GET", "/foo\nbar"), 404)
        self.assertEqual(line.count("\n"), 1)
        self.assertNotIn("\nbar", line)
        self.assertIn("GET   /foo", line)
        self.assertTrue(line.endswith("404  127.0.0.1\n"))

    def test_send_error_boilerplate_is_not_duplicated(self):
        handler = self._handler("GET", "/nope")
        self.assertEqual(
            self._logged(handler, error=("code %d, message %s", 400, "Bad Request")),
            "",
        )
        line = self._logged(handler, 400)
        self.assertEqual(line, self._at("GET", "/nope", 400, "127.0.0.1", clock=line[6:14]))

    def test_unexpected_log_error_is_kept(self):
        line = self._logged(
            self._handler("GET", "/"),
            error=("Request timed out: %r", TimeoutError("slow")),
        )
        self.assertIn("[web] 127.0.0.1 Request timed out:", line)


if __name__ == "__main__":
    unittest.main()
