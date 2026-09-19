#!/usr/bin/env python3
"""fofatoto 单元测试 — 仅标准库 unittest，覆盖纯函数与关键路径。

运行: python -m unittest test_fofatoto -v
（在本文件所在目录执行；不发起任何真实网络请求，FOFA API 通过
monkeypatch urlopen 模拟。）
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
import unittest
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

    def test_web_categories_validation_passes(self):
        fofatoto._validate_web_field_categories()  # 不应抛异常

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

    def test_https_default_port_omitted(self):
        r = make_result(host="a.com", port="443")
        self.assertEqual(fofatoto.build_url(r), "https://a.com")

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

    def test_none_check_degrades_to_sleep(self):
        fofatoto._sleep_interruptible(0.05)


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

    def test_to_dict_no_underscore_keys(self):
        r = make_result(ip="1.2.3.4")
        self.assertNotIn("_extra", r.to_dict())


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

    def test_string_row_result(self):
        _, stats = self._search(
            "ip", {"error": False, "size": 1, "results": [["1.1.1.1", "extra"]]}
        )
        self.assertEqual(stats.results[0].ip, "1.1.1.1")


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


if __name__ == "__main__":
    unittest.main()
