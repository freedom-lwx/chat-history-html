#!/usr/bin/env python3
"""Local, dependency-free conversation HTML archive. Python 3.10+."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from html import escape, unescape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SLUG = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
STATUSES = {"进行中", "已沉淀", "待验证"}
RESERVED_IDS = {"open-questions", "references", "revision-history"}
TAGS = set("p h3 h4 ul ol li strong em b i blockquote pre code table thead tbody tfoot tr th td a br hr details summary kbd mark del sup sub caption".split())
VOID = {"br", "hr"}
SEARCH_SCRIPT = """const q=document.querySelector('#search'),s=document.querySelector('#status');
const cards=[...document.querySelectorAll('[data-search]')];
function filter(){let n=0;const term=q.value.trim().toLocaleLowerCase();
for(const card of cards){const show=card.dataset.search.includes(term)&&(!s.value||card.dataset.status===s.value);card.hidden=!show;if(show)n++;}
document.querySelector('#result-count').textContent=`显示 ${n} 个主题`;
document.querySelector('#no-results').hidden=n!==0||cards.length===0;}
q.addEventListener('input',filter);s.addEventListener('change',filter);filter();"""


class ArchiveError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ArchiveError(message)


def valid_slug(value):
    require(isinstance(value, str) and bool(SLUG.fullmatch(value)) and len(value) <= 80,
            "slug/id 必须是 1–80 字符的小写英文、数字和连字符，且以字母开头")
    return value


def text(value, name):
    require(isinstance(value, str) and bool(value.strip()), f"{name} 必须是非空字符串")
    return value


def valid_url(value, fragment=False):
    text(value, "链接")
    require(not re.search(r"[\s\x00-\x20\x7f\\]", value), "链接不能包含空白、控制字符或反斜杠")
    if fragment and value.startswith("#"):
        valid_slug(value[1:])
        return value
    try:
        parsed = urlsplit(value)
        require(parsed.scheme in {"http", "https"} and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None, "链接仅允许无凭据的 http(s) URL")
        _ = parsed.port
    except ValueError as exc:
        raise ArchiveError(f"无效链接：{value}") from exc
    return value


class SafeFragment(HTMLParser):
    """Allowlisted HTML fragments, reconstructed instead of passed through."""
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.stack = []
        self.output = []

    def handle_starttag(self, tag, attrs):
        require(tag in TAGS, f"不允许 HTML 标签 <{tag}>")
        allowed = {"href", "title"} if tag == "a" else {"colspan", "rowspan"} if tag in {"th", "td"} else set()
        seen = set()
        rendered = []
        for name, value in attrs:
            require(name in allowed and name not in seen and value is not None,
                    f"<{tag}> 的属性 {name} 不受支持或重复")
            seen.add(name)
            if name == "href":
                valid_url(value, fragment=True)
            if name in {"colspan", "rowspan"}:
                require(value.isascii() and value.isdigit() and 1 <= int(value) <= 20, "表格合并范围必须为 1–20")
            rendered.append(f' {name}="{escape(value, quote=True)}"')
        if tag == "a":
            rendered.append(' rel="noreferrer noopener"')
        self.output.append(f"<{tag}{''.join(rendered)}>")
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        require(tag in VOID, f"只有 br/hr 可使用自闭合写法：{tag}")
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        require(bool(self.stack) and self.stack[-1] == tag, f"HTML 标签未正确配对：{tag}")
        self.stack.pop()
        self.output.append(f"</{tag}>")

    def handle_data(self, data):
        self.output.append(escape(data, quote=False))

    def handle_entityref(self, name):
        self.handle_data(unescape(f"&{name};"))

    def handle_charref(self, name):
        self.handle_data(unescape(f"&#{name};"))

    def handle_decl(self, decl):
        raise ArchiveError("章节中不能包含文档声明")

    def handle_pi(self, data):
        raise ArchiveError("章节中不能包含处理指令")

    def unknown_decl(self, data):
        raise ArchiveError("章节中包含不支持的声明")


def safe_html(value):
    parser = SafeFragment()
    parser.feed(text(value, "section.html"))
    parser.close()
    require(not parser.stack, "HTML 存在未闭合标签")
    return "".join(parser.output)


def exact_keys(obj, expected, name):
    require(isinstance(obj, dict) and set(obj) == set(expected.split()), f"{name} 字段应为：{expected}")


def validate(data, expected_slug=None):
    exact_keys(data, "slug title summary tags status sections openQuestions references", "主题")
    valid_slug(data["slug"])
    require(expected_slug is None or data["slug"] == expected_slug, "文件名与 slug 不一致")
    text(data["title"], "title")
    text(data["summary"], "summary")
    require(isinstance(data["status"], str) and data["status"] in STATUSES, "status 应为 进行中 / 已沉淀 / 待验证")
    for key in ("tags", "openQuestions"):
        require(isinstance(data[key], list), f"{key} 必须是数组")
        for item in data[key]:
            text(item, key)
    require(isinstance(data["sections"], list) and data["sections"], "至少需要一个章节")
    ids = set(RESERVED_IDS)
    for section in data["sections"]:
        exact_keys(section, "id title html", "章节")
        sid = valid_slug(section["id"])
        require(sid not in ids, f"重复或保留的章节 id：{sid}")
        ids.add(sid)
        text(section["title"], "章节标题")
        safe_html(section["html"])
    require(isinstance(data["references"], list), "references 必须是数组")
    for ref in data["references"]:
        exact_keys(ref, "label url", "来源")
        text(ref["label"], "来源名称")
        valid_url(ref["url"])
    return data


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ArchiveError(f"无法读取 JSON：{path}：{exc}") from exc


def json_text(data):
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def digest(data):
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".archive-stage-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def locked(root):
    lock = root / ".archive.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ArchiveError("另一个归档操作正在进行；若是异常退出残留，请先确认没有运行进程再手动移除 .archive.lock") from exc
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def display_time(value):
    return escape(value.replace("T", " ").replace("Z", " UTC"))


def revision_name(version):
    return f"v{version:04d}"


def revisions(root, slug):
    folder = root / "history" / slug
    result = []
    if not folder.exists():
        return result
    candidates = sorted((p for p in folder.iterdir() if re.fullmatch(r"v\d{4,}", p.name)), key=lambda p: int(p.name[1:]))
    for path in candidates:
        meta = read_json(path / "revision.json")
        exact_keys(meta, "version publishedAt note sha256", "修订记录")
        require(type(meta["version"]) is int and meta["version"] == len(result) + 1
                and path.name == revision_name(meta["version"]), f"历史版本不连续：{path}")
        for field in ("publishedAt", "note", "sha256"):
            text(meta[field], field)
        require(bool(re.fullmatch(r"[0-9a-f]{64}", meta["sha256"])), "历史校验码不正确")
        try:
            datetime.fromisoformat(meta["publishedAt"].replace("Z", "+00:00"))
        except ValueError as exc:
            raise ArchiveError("历史时间格式不正确") from exc
        require((path / "index.html").is_file() and (path / "source.json").is_file(), f"历史快照不完整：{path}")
        result.append(meta)
    return result


def snapshot_source(root, slug, meta):
    path = root / "history" / slug / revision_name(meta["version"]) / "source.json"
    data = validate(read_json(path), slug)
    require(digest(data) == meta["sha256"], f"历史源文件校验失败：{path}")
    return data


def document(root, title, body, home, script=""):
    import base64
    script_policy = "'none'"
    if script:
        hashed = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii")
        script_policy = f"'sha256-{hashed}'"
    policy = f"default-src 'none'; style-src 'unsafe-inline'; script-src {script_policy}; base-uri 'none'; form-action 'none'; object-src 'none'"
    css = (root / "assets" / "style.css").read_text(encoding="utf-8")
    return f'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{escape(policy, quote=True)}">
<meta name="referrer" content="no-referrer">
<title>{escape(title)} · 对话手记</title>
<style>{css}</style>
</head>
<body><div class="shell">
<header class="topbar"><a class="brand" href="{home}">对话手记 <span class="muted">/ Dialogue notes</span></a><span class="muted">本地保存 · 持续生长</span></header>
<main>{body}</main>
<footer class="footer">由讨论沉淀，而非逐字记录。保留依据、边界与尚未解决的问题。所有页面可离线阅读；浏览器打印可另存为 PDF。</footer>
</div>{('<script>' + script + '</script>') if script else ''}</body>
</html>
'''


def render_topic(root, data, meta, history, archived=False):
    slug = data["slug"]
    prefix = "../../../" if archived else "../"
    links = [(s["id"], s["title"]) for s in data["sections"]]
    sections = [f'<section id="{s["id"]}"><h2>{escape(s["title"])}</h2>{safe_html(s["html"])}</section>' for s in data["sections"]]
    if data["openQuestions"]:
        links.append(("open-questions", "待验证与后续问题"))
        sections.append('<section id="open-questions"><h2>待验证与后续问题</h2><ul>' + ''.join(f'<li>{escape(q)}</li>' for q in data["openQuestions"]) + '</ul></section>')
    if data["references"]:
        links.append(("references", "参考来源"))
        refs = ''.join(f'<li><a href="{escape(r["url"], quote=True)}" rel="noreferrer noopener">{escape(r["label"])}</a></li>' for r in data["references"])
        sections.append(f'<section id="references"><h2>参考来源</h2><ul>{refs}</ul></section>')
    if not archived:
        links.append(("revision-history", "修订记录"))
        rows = ''.join(f'<li><a href="../history/{slug}/{revision_name(r["version"])}/index.html">v{r["version"]}</a> · {display_time(r["publishedAt"])} — {escape(r["note"])}</li>' for r in reversed(history))
        sections.append(f'<section id="revision-history" class="history"><h2>修订记录</h2><ol reversed>{rows}</ol></section>')
    toc = ''.join(f'<a href="#{sid}">{escape(label)}</a>' for sid, label in links)
    tags = ''.join(f'<span class="tag">{escape(tag)}</span>' for tag in data["tags"])
    banner = (f'这是不可变的历史快照 v{meta["version"]}。<a href="{prefix}pages/{slug}.html">查看最新版本</a>'
              if archived else f'本次更新：{escape(meta["note"])}')
    body = f'''<div class="hero"><div class="eyebrow">Discussion / {escape(data['status'])}</div>
<h1>{escape(data['title'])}</h1><p>{escape(data['summary'])}</p><div class="tags">{tags}<span class="tag status">v{meta['version']}</span></div>
<p class="meta">更新于 {display_time(meta['publishedAt'])}</p></div>
<div class="revision">{banner}</div><div class="layout"><nav class="toc" aria-label="章节目录"><span class="eyebrow">Contents</span>{toc}</nav><article>{''.join(sections)}</article></div>'''
    return document(root, data["title"], body, prefix + "index.html")


def render_index(root, topics):
    cards = []
    for item in topics:
        search = escape(' '.join([item["title"], item["summary"], *item["tags"]]).lower(), quote=True)
        tags = ''.join(f'<span class="tag">{escape(t)}</span>' for t in item["tags"])
        cards.append(f'''<article class="card" data-search="{search}" data-status="{escape(item['status'])}">
<div class="tags"><span class="tag status">{escape(item['status'])}</span>{tags}</div>
<h2><a href="pages/{item['slug']}.html">{escape(item['title'])}</a></h2><p>{escape(item['summary'])}</p>
<div class="meta">v{item['version']} · {display_time(item['updatedAt'])}</div></article>''')
    total = sum(item["version"] for item in topics)
    empty = '''<div class="empty"><div class="eyebrow">A place for useful conversations</div><h2>好讨论，值得留下来。</h2><p>这里还没有归档主题。信息足够时，模型会自主整理；<br>同一主题持续更新，每次实质变化保留一个版本。</p><p>在任意目录的 Pi 会话中开始讨论，或输入 <code>/save-html</code> 显式保存。</p></div>''' if not topics else ''
    body = f'''<div class="hero"><div class="eyebrow">Personal knowledge / Incremental archive</div><h1>让讨论留下脉络。</h1><p>把值得反复阅读的分析、判断与行动，整理成持续更新的手记。<br>不追求每轮记录，只保留真正推进理解的内容。</p></div>
<div class="stats"><div class="stat"><strong>{len(topics):02d}</strong><span>归档主题</span></div><div class="stat"><strong>{total:02d}</strong><span>历史版本</span></div><div class="stat"><strong>离线</strong><span>无需服务与账号</span></div></div>
<div class="toolbar"><label for="search" class="sr-only">搜索标题、摘要和标签</label><input id="search" type="search" placeholder="搜索标题、摘要或标签…"><label for="status" class="sr-only">筛选主题状态</label><select id="status"><option value="">全部状态</option><option>进行中</option><option>已沉淀</option><option>待验证</option></select></div>
<p class="meta" id="result-count" role="status">共 {len(topics)} 个主题</p><noscript><p class="meta">JavaScript 已禁用：可阅读全部主题，搜索与筛选不可用。</p></noscript>
<div class="grid">{''.join(cards)}</div>{empty}<div class="empty" id="no-results" hidden>没有匹配的主题，试试其他关键词。</div>'''
    return document(root, "归档目录", body, "index.html", SEARCH_SCRIPT)


def rebuild_unlocked(root):
    topics = []
    outputs = []
    history_root = root / "history"
    for folder in sorted(history_root.iterdir()) if history_root.exists() else []:
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        slug = valid_slug(folder.name)
        records = revisions(root, slug)
        if not records:
            continue
        latest = records[-1]
        data = snapshot_source(root, slug, latest)
        outputs.append((root / "pages" / f"{slug}.html", render_topic(root, data, latest, records)))
        topics.append({**{k: data[k] for k in ("slug", "title", "summary", "tags", "status")},
                       "version": latest["version"], "createdAt": records[0]["publishedAt"],
                       "updatedAt": latest["publishedAt"], "sha256": latest["sha256"], "history": records})
    topics.sort(key=lambda topic: (topic["updatedAt"], topic["slug"]), reverse=True)
    outputs.extend([(root / "manifest.json", json_text({"schemaVersion": 1, "topics": topics})),
                    (root / "index.html", render_index(root, topics))])
    for path, content in outputs:
        atomic_write(path, content)
    return topics


def rebuild(root=ROOT):
    with locked(root):
        return rebuild_unlocked(root)


def publish(root, slug, note):
    valid_slug(slug)
    text(note, "修订说明")
    with locked(root):
        data = validate(read_json(root / "topics" / f"{slug}.json"), slug)
        records = revisions(root, slug)
        content_hash = digest(data)
        if records:
            snapshot_source(root, slug, records[-1])
        if records and records[-1]["sha256"] == content_hash:
            rebuild_unlocked(root)
            return False, records[-1]["version"]
        meta = {"version": len(records) + 1, "publishedAt": stamp(), "note": note, "sha256": content_hash}
        # Render before committing anything; validation/CSS errors leave history untouched.
        page = render_topic(root, data, meta, records + [meta], archived=True)
        folder = root / "history" / slug
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / revision_name(meta["version"])
        require(not target.exists(), f"拒绝覆盖快照：{target}")
        stage = Path(tempfile.mkdtemp(prefix=".archive-stage-", dir=folder))
        try:
            atomic_write(stage / "source.json", json_text(data))
            atomic_write(stage / "revision.json", json_text(meta))
            atomic_write(stage / "index.html", page)
            os.rename(stage, target)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
        # The immutable snapshot is the commit point. Rebuild can recover interrupted outputs.
        try:
            rebuild_unlocked(root)
        except (OSError, ValueError) as exc:
            raise ArchiveError(f"v{meta['version']} 快照已保存，但目录/最新页未完成；请运行 rebuild 恢复。原因：{exc}") from exc
        return True, meta["version"]


def new_topic(root, slug, title):
    valid_slug(slug)
    text(title, "标题")
    data = read_json(root / "templates" / "topic.json")
    data.update(slug=slug, title=title)
    validate(data)
    with locked(root):
        require(not revisions(root, slug), "该 slug 已有历史记录，请恢复/编辑源文件而不是新建")
        path = root / "topics" / f"{slug}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(json_text(data))
        except FileExistsError as exc:
            raise ArchiveError(f"主题已存在：{path}") from exc
    return path


def check(root):
    count = 0
    for path in sorted((root / "topics").glob("*.json")):
        validate(read_json(path), path.stem)
        count += 1
    history_root = root / "history"
    for folder in history_root.iterdir() if history_root.exists() else []:
        if folder.is_dir() and not folder.name.startswith("."):
            valid_slug(folder.name)
            for meta in revisions(root, folder.name):
                snapshot_source(root, folder.name, meta)
    return count


def main():
    # Keep Chinese CLI output readable when Windows redirects stdout to an agent.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="增量维护本地对话 HTML：无依赖、离线、可追溯")
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("new", help="创建未发布的主题源文件")
    new.add_argument("slug")
    new.add_argument("--title", required=True)
    pub = commands.add_parser("publish", help="发布内容变化并保留不可变快照")
    pub.add_argument("slug")
    pub.add_argument("--note", required=True)
    commands.add_parser("check", help="校验源文件、安全 HTML 和历史源文件校验码")
    commands.add_parser("rebuild", help="从已发布快照重建最新页与目录，不发布草稿")
    args = parser.parse_args()
    try:
        if args.command == "new":
            print(f"已创建草稿，请编辑后发布：{new_topic(ROOT, args.slug, args.title)}")
        elif args.command == "publish":
            changed, version = publish(ROOT, args.slug, args.note)
            print(f"{'已发布' if changed else '内容无变化，未新增版本'} v{version}：{ROOT / 'pages' / (args.slug + '.html')}")
        elif args.command == "check":
            print(f"校验通过：{check(ROOT)} 个主题源文件；历史源文件完整。")
        else:
            print(f"目录已重建：{len(rebuild(ROOT))} 个主题；{ROOT / 'index.html'}")
    except (OSError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
