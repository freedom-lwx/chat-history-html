# dialogue-html 工程约定

本工程用于把有价值的深入讨论增量沉淀为 HTML，不是聊天记录自动全量导出器。

- 行为规则：读 `C:/Users/Admin/.pi/agent/APPEND_SYSTEM.md`（用户级系统追加提示词），每轮自主判断是否值得归档。同主题优先更新，尊重不保存/暂停指令。规则适用于各个工作目录，归档统一保存在 `D:/workspace/dialogue-html`。
- 新会话：先读 `memory/context.md` 与 `manifest.json`，按需读相关主题。
- 内容源文件：`topics/<slug>.json`。格式示例：`templates/topic.json`。slug 和章节 id 使用小写英文、数字与连字符，首字符必须是英文字母。
- 新建：`python scripts/archive.py new <slug> --title "主题标题"`，然后编辑源文件。
- 校验：`python scripts/archive.py check`。
- 发布：`python scripts/archive.py publish <slug> --note "简述实质变化"`。
- 重建目录/最新页：`python scripts/archive.py rebuild`。它使用已发布快照，不会发布尚未归档的源文件修改。
- 测试：`python -m unittest discover -s tests -v`。
- `index.html`、`manifest.json`、`pages/` 是派生输出，不手工编辑。`history/` 是已发布的自包含快照，正常工作流只新增，不覆盖。
- 历史快照中同时保存 source.json、revision.json 和 index.html。内容不变的重复发布不新增版本。修订说明不是正文，单独修改说明不产生版本。
- `assets/style.css` 是共享样式；发布/重建时内联到最新页面。旧快照保持原样。
- 支持正文标签：p、h3、h4、ul、ol、li、strong、em、b、i、blockquote、pre、code、table、thead、tbody、tfoot、tr、th、td、a、br、hr、details、summary、kbd、mark、del、sup、sub、caption。仅 a 支持 href/title（href 限 http(s) 或本页锚点），th/td 支持 colspan/rowspan（1–20）。不支持任意 class/style/id、脚本、图片或 iframe。
- 只使用 Python 标准库，不安装依赖，不启动公网服务。用户已要求将归档提示词配置为全局；日常归档不应自行继续修改全局配置。以下相对路径与命令示例均以本工程为基准；从其他目录操作时，使用 `D:/workspace/dialogue-html` 下的绝对文件路径和 `python "D:/workspace/dialogue-html/scripts/archive.py"`（脚本会自行定位工程），不必切换当前工作目录。
- 不记录不可见的历史，不伪造参考资料。凭据、原始私密信息和用户禁止保存的内容不得进入源文件、快照或 memory。
- 本工具面向单进程本地维护；发布/重建有排他锁，不要并发修改同一个源文件。不要自动清除其他进程持有的锁。
