import copy
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from html.parser import HTMLParser

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("archive", PROJECT / "scripts" / "archive.py")
archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)


class LinkCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "a" and "href" in attrs:
            self.links.append(attrs["href"])


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in ("assets", "templates"):
            shutil.copytree(PROJECT / name, self.root / name)
        (self.root / "topics").mkdir()
        self.data = {
            "slug": "test-topic", "title": "深入讨论：架构选择", "summary": "权衡离线体验与实现成本。",
            "tags": ["架构", "HTML"], "status": "进行中",
            "sections": [{"id": "background", "title": "背景", "html": "<p>保留背景与约束。</p>"},
                         {"id": "analysis", "title": "分析", "html": "<p>使用<strong>静态页面</strong>。</p><pre><code>a &lt; b &amp;&amp; c &gt; d</code></pre>"}],
            "openQuestions": ["后续需要验证移动端可读性。"],
            "references": [{"label": "参考资料示例", "url": "https://example.com/docs?a=1&b=2"}],
        }
        self.save()

    def tearDown(self):
        self.temp.cleanup()

    def save(self):
        (self.root / "topics" / "test-topic.json").write_text(archive.json_text(self.data), encoding="utf-8")

    def publish(self, note="首次沉淀"):
        return archive.publish(self.root, "test-topic", note)

    def test_empty_index(self):
        self.assertEqual(archive.rebuild(self.root), [])
        self.assertIn("好讨论，值得留下来", (self.root / "index.html").read_text(encoding="utf-8"))
        self.assertFalse((self.root / "pages" / "test-topic.html").exists())

    def test_first_publish_and_check(self):
        self.assertEqual(self.publish(), (True, 1))
        manifest = archive.read_json(self.root / "manifest.json")
        self.assertEqual(manifest["topics"][0]["version"], 1)
        self.assertEqual(archive.check(self.root), 1)
        page = (self.root / "pages" / "test-topic.html").read_text(encoding="utf-8")
        self.assertIn('id="background"', page)
        self.assertIn("a &lt; b &amp;&amp; c &gt; d", page)
        self.assertNotIn("<script>", page)
        self.assertIn("Content-Security-Policy", page)

    def test_repeat_is_idempotent_even_with_new_note(self):
        self.publish()
        self.assertEqual(self.publish("只修改说明不增加版本"), (False, 1))
        self.assertEqual(len(archive.revisions(self.root, "test-topic")), 1)

    def test_changed_section_keeps_old_snapshot_and_other_sections(self):
        self.publish()
        snapshot = self.root / "history" / "test-topic" / "v0001"
        before = {p.name: p.read_bytes() for p in snapshot.iterdir()}
        self.data["sections"][1]["html"] = "<p>新增离线部署的权衡。</p>"
        self.save()
        self.assertEqual(self.publish("补充部署权衡"), (True, 2))
        self.assertEqual(before, {p.name: p.read_bytes() for p in snapshot.iterdir()})
        latest = (self.root / "pages" / "test-topic.html").read_text(encoding="utf-8")
        self.assertIn("保留背景与约束", latest)
        self.assertIn("新增离线部署的权衡", latest)
        self.assertIn("v0001/index.html", latest)
        self.assertIn("v0002/index.html", latest)

    def test_rebuild_does_not_publish_drafts(self):
        self.publish()
        self.data["title"] = "尚未发布的标题"
        self.save()
        (self.root / "index.html").unlink()
        (self.root / "pages" / "test-topic.html").unlink()
        archive.rebuild(self.root)
        self.assertNotIn("尚未发布的标题", (self.root / "index.html").read_text(encoding="utf-8"))
        self.assertEqual(len(archive.revisions(self.root, "test-topic")), 1)

    def test_interrupted_output_is_recoverable(self):
        with patch.object(archive, "rebuild_unlocked", side_effect=OSError("simulated interruption")):
            with self.assertRaisesRegex(archive.ArchiveError, "快照已保存"):
                self.publish()
        self.assertFalse((self.root / ".archive.lock").exists())
        archive.rebuild(self.root)
        self.assertTrue((self.root / "index.html").is_file())
        self.assertEqual(self.publish(), (False, 1))

    def test_lock_rejects_concurrent_operation(self):
        lock = self.root / ".archive.lock"
        lock.write_text("another process")
        with self.assertRaisesRegex(archive.ArchiveError, "正在进行"):
            self.publish()
        self.assertEqual(lock.read_text(), "another process")

    def test_unsafe_fragments_are_rejected(self):
        samples = ["<script>alert(1)</script>", '<p onclick="x()">text</p>', '<img src="https://example.com/a.png">',
                   '<a href="javascript:alert(1)">x</a>', '<a href="java&#x73;cript:alert(1)">x</a>',
                   '<a href="file:///C:/secret">x</a>', '<a href="https://u:p@example.com">x</a>',
                   '<p style="background:url(https://example.com)">x</p>', '<iframe></iframe>',
                   '<svg><script>x</script></svg>', '<a href="https://example.com" href="javascript:x">x</a>',
                   '<table><tr><td colspan="0">x</td></tr></table>', '<!DOCTYPE html><p>x</p>']
        for sample in samples:
            with self.subTest(sample=sample), self.assertRaises(archive.ArchiveError):
                archive.safe_html(sample)

    def test_safe_fragment_tags_and_entities(self):
        sample = '<details><summary>展开</summary><p><a href="https://example.com/?a=1&amp;b=2">来源</a><br/>x &lt; y</p></details>'
        result = archive.safe_html(sample)
        self.assertIn('rel="noreferrer noopener"', result)
        self.assertIn("x &lt; y", result)
        self.assertIn("a=1&amp;b=2", result)
        self.assertEqual(archive.safe_html('<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>'), '<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>')

    def test_unbalanced_html_rejected(self):
        for value in ("<p>missing", "<p><strong>x</p></strong>", "</p>"):
            with self.subTest(value=value), self.assertRaises(archive.ArchiveError):
                archive.safe_html(value)

    def test_path_traversal_and_bad_slugs_rejected(self):
        for value in ("../outside", "C:/outside", "/tmp/outside", "UPPER", "a_b", "a--b", "", "a" * 81):
            with self.subTest(value=value), self.assertRaises(archive.ArchiveError):
                archive.publish(self.root, value, "note")

    def test_invalid_schema_rejected_without_history(self):
        self.data["sections"][1]["id"] = "background"
        self.save()
        with self.assertRaises(archive.ArchiveError):
            self.publish()
        self.assertFalse((self.root / "history").exists())
        self.assertFalse((self.root / ".archive.lock").exists())
        self.data["sections"][1]["id"] = "references"
        with self.assertRaises(archive.ArchiveError):
            archive.validate(self.data)

    def test_metadata_is_escaped(self):
        self.data["title"] = '<img src=x onerror="alert(1)">'
        self.data["summary"] = '</p><script>alert(1)</script>'
        self.save()
        self.publish('<script>alert("note")</script>')
        for path in (self.root / "pages" / "test-topic.html", self.root / "index.html"):
            result = path.read_text(encoding="utf-8")
            self.assertNotIn('<img src=x', result)
            self.assertNotIn('<script>alert(', result)
            self.assertIn('&lt;img', result)

    def test_local_links_resolve(self):
        self.publish()
        self.data["summary"] = "新增第二版摘要。"
        self.save()
        self.publish("更新摘要")
        for path in self.root.rglob("*.html"):
            collector = LinkCollector()
            collector.feed(path.read_text(encoding="utf-8"))
            for href in collector.links:
                with self.subTest(path=path, href=href):
                    if href.startswith("#"):
                        self.assertIn(href[1:], collector.ids)
                    elif not href.startswith("http"):
                        self.assertTrue((path.parent / href).resolve().is_file())

    def test_history_tampering_detected(self):
        self.publish()
        source = self.root / "history" / "test-topic" / "v0001" / "source.json"
        tampered = copy.deepcopy(self.data)
        tampered["summary"] = "被篡改的历史内容"
        source.write_text(archive.json_text(tampered), encoding="utf-8")
        with self.assertRaisesRegex(archive.ArchiveError, "校验失败"):
            archive.check(self.root)

    def test_new_does_not_overwrite_existing(self):
        path = archive.new_topic(self.root, "another-topic", "另一主题")
        self.assertTrue(path.exists())
        self.assertFalse((self.root / "history").exists())
        with self.assertRaises(archive.ArchiveError):
            archive.new_topic(self.root, "another-topic", "覆盖标题")

    def test_json_key_order_does_not_change_hash(self):
        self.assertEqual(archive.digest(self.data), archive.digest(dict(reversed(list(self.data.items())))))

    def test_broken_reference_and_schema_errors(self):
        for mutation in ({"references": [{"label": "x", "url": "data:text/html,hello"}]},
                         {"status": []}, {"sections": []}, {"tags": "not a list"}, {"slug": "wrong-slug"}):
            with self.subTest(mutation=mutation), self.assertRaises(archive.ArchiveError):
                archive.validate({**self.data, **mutation}, "test-topic")


if __name__ == "__main__":
    unittest.main()
