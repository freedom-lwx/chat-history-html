# 对话手记 · dialogue-html

将有价值的深入讨论沉淀为可离线阅读的 HTML。**模型自主决定何时生成；同一主题持续增量更新；每次实质变化保留历史版本。** 不会机械地每轮生成一篇，也不是所有会话的自动监听器。

## GitHub 仓库与阅读入口

仓库：<https://github.com/freedom-lwx/chat-history-html>

下载或克隆后，双击根目录 `index.html` 阅读统一主页；HTML、历史快照和配套源码包均可离线使用。上传 GitHub 仓库不等于开通网页托管，本次不自动启用 GitHub Pages。

```bash
git clone https://github.com/freedom-lwx/chat-history-html.git
cd chat-history-html
```

下文的绝对路径描述原维护机器的配置。换机后需要调整全局提示词中的归档路径，并把 `memory/context.example.md` 复制为 `memory/context.md`。用户级 Pi 配置、真实工作记忆、缓存和凭据不随仓库上传。

## 开始使用

1. **在当前 Pi 会话执行 `/reload`，或在任意工作目录启动新会话。无需进入本工程目录。**
2. 归档规则已配置到用户级系统追加提示词 **`C:\Users\Admin\.pi\agent\APPEND_SYSTEM.md`**，采用追加而非替换 Pi 默认系统提示词的方式。
3. 正常讨论即可。信息量足够、有复用价值且相对已有文档有实质增量时，模型会自行归档。不足时继续讨论，不强制生成。
4. 所有归档统一保存在 **`D:\workspace\dialogue-html`**。双击该目录的 **`index.html`** 查看、搜索主题及历史版本，无需服务、网络或安装前端依赖。

这是 **Pi 当前用户级的系统提示词配置**，不是操作系统所有软件/所有用户共用的设置。使用不同 `PI_CODING_AGENT_DIR` 或 SDK 自定义 agentDir 的实例，需要在其对应配置中另行设置。现有会话在重新加载前不会自动注入新文件。

其他客户端需要把上述全局提示词加入其自身的系统/用户指令，并提供对归档工程的文件读写和 Python 运行权限。单纯网页聊天不能自动落盘；本项目也不会读取其他客户端的会话历史。

> Pi 的项目 APPEND_SYSTEM.md 会优先于用户级同名文件，而非自动合并。为保留跨目录偏好，已在 `C:\Users\Admin\.pi\agent\AGENTS.md` 添加简短的全局归档约定：当完整规则未加载时读取上述全局文件。禁用上下文发现、使用自定义资源加载器或具体项目/用户明确禁止归档时，这一行为仍可能不生效。原工程级 `.pi/APPEND_SYSTEM.md` 已移除，避免遮蔽全局版本。

## 控制归档行为

- “先继续讨论，信息足够后你自己决定是否生成 HTML。”——默认行为。
- “更新之前的离线架构主题，补充这次的新结论。”——增量修改已有主题。
- **`/save-html`** 或 `/save-html 主题名称或补充要求`——显式保存当前讨论。
- “本轮不归档 / 不要保存这些内容。”——本轮内容不写入主题、历史或工作记忆。
- “暂停自动归档，直到我说恢复。”——暂停；模型应将这一偏好写入工作记忆。

提示词约定会引导模型，但不是强制执行钩子或后台任务。它不能保证每个模型每轮都完全遵循，也无法归档模型看不到的历史信息。重要内容可以用 `/save-html` 显式触发。

## 工程结构

```text
AGENTS.md                  助手工作约定
memory/context.md          本地跨会话偏好与线索（Git 忽略，不公开）
memory/context.example.md  无个人内容的工作记忆模板
topics/<slug>.json         可编辑的主题源文件
templates/topic.json       新主题结构示例，不会出现在归档目录
assets/style.css           公共样式，生成时内联
scripts/archive.py         创建、校验、发布和重建工具
index.html                 离线目录页（生成）
manifest.json              供模型查找主题的索引（生成）
pages/<slug>.html          每个主题固定地址的最新页面（生成）
history/<slug>/v0001/      每次发布的历史快照（首次发布后创建）
  source.json              当时的完整内容源
  revision.json            版本号、UTC 时间、修订说明和 SHA-256
  index.html               当时的自包含 HTML
tests/test_archive.py      测试（独立临时目录，不污染真实归档）
```

用户级配置（位于工程之外）：

```text
C:/Users/Admin/.pi/agent/APPEND_SYSTEM.md     系统追加提示词：跨目录的归档判断与流程
C:/Users/Admin/.pi/agent/AGENTS.md            全局偏好及项目覆盖时的规则入口
C:/Users/Admin/.pi/agent/prompts/save-html.md 全局 /save-html 命令
```

迁移或备份到其他机器时，需要同时处理这些配置及其中的绝对路径，不能仅复制工程目录。

## 发布工具

以下相对命令在 `D:/workspace/dialogue-html` 下执行。从其他工作目录调用时，把 `scripts/archive.py` 改为 `"D:/workspace/dialogue-html/scripts/archive.py"`；无需切换当前目录，脚本会自行定位归档根目录。

需要 **Python 3.10+**，仅标准库。本机已检测到 Python 3.13，无须安装依赖。

```powershell
# 1. 创建草稿；不会自动发布模板占位内容
python scripts/archive.py new offline-architecture --title "离线架构讨论"

# 2. 由模型编辑 topics/offline-architecture.json，替换模板内容

# 3. 校验全部源文件、HTML 片段及历史源文件
python scripts/archive.py check

# 4. 发布，生成最新页、历史快照和目录
python scripts/archive.py publish offline-architecture --note "首次整理方案权衡与待验证项"

# 5. 后续只编辑相关章节，再发布同一 slug
python scripts/archive.py publish offline-architecture --note "补充同步方案，修正成本判断"

# 目录或最新页面损坏时，从已发布快照恢复（不会发布未完成的草稿）
python scripts/archive.py rebuild

# 运行测试
python -m unittest discover -s tests -v
```

源文件只包含 `slug`、`title`、`summary`、`tags`、`status`、`sections`、`openQuestions`、`references` 八个字段。status 取 `进行中`、`已沉淀`、`待验证`。章节结构为 `{ "id": "stable-id", "title": "章节标题", "html": "<p>正文</p>" }`。参考来源结构为 `{ "label": "来源名称", "url": "https://…" }`。

允许表格、代码块、列表、引用和折叠详情；具体标签白名单见 `AGENTS.md`。不用 Markdown 解析器，模型直接维护 HTML 片段。标题、摘要、待验证问题和来源名称是纯文本，会自动转义。页面禁止任意脚本、事件处理器及远程资源；目录搜索脚本由固定哈希 CSP 放行。

### 增量与恢复约定

- **逻辑增量**：模型只修改源文件中受影响的章节；工具重新渲染完整 HTML，保证每版都能独立阅读。
- 内容源的规范化 JSON 哈希未变化时，不生成新版本。重复发布、仅更改 `--note`、JSON 字段顺序或外部缩进不会增加版本；HTML 字符串内部的变化会视为内容变化。
- 历史快照只新增，不覆盖。重建或更改样式不会改变旧快照。需要回到旧内容时，将旧 `source.json` 的内容恢复到对应主题源文件，再发布一个新版本，保留回退轨迹。
- 快照目录的原子重命名是发布提交点。每个派生文件也采用原子替换，但多个派生文件不是一个事务；若进程在提交后中断，运行 `rebuild` 恢复一致性。工具不会凭空恢复尚未成功保存的内容。
- `.archive.lock` 防止并发发布/重建。异常退出可能留下锁，确认没有归档进程运行后才可手动删除。此工具面向本地单写入者，不面向多用户并发服务。
- `check` 检查源内容、HTML 白名单、版本连续性与历史源文件哈希，不是完整的浏览器渲染验证器。
- 当前工程从空目录开始，没有虚构样例讨论，也未扫描或导入磁盘上既有的 HTML。

## 隐私与备份

归档操作默认只在本地保存，无遥测、无自动上传。本公开仓库保存用户明确授权推送的工程、主题和历史快照；后续归档不会自动同步 GitHub，上传前仍需审阅内容。真实的 `memory/context.md`、凭据与用户级 Pi 配置不纳入公开仓库。归档前剔除密钥和不必要的个人信息。**历史版本会保留旧内容：只删除最新源文件中的敏感文字，不会删除旧快照。** 如需彻底移除，需明确审查源文件、历史、派生页、备份及任何外部版本库；本工具未提供自动清理命令。

“不可变快照”指工具不会覆盖它，文件本身并非操作系统只读或防篡改存储。SHA-256 用于发现意外修改，不是签名。可自行将整个工程纳入 Git 或定期备份，但不要未经审查公开含有对话内容的仓库。
