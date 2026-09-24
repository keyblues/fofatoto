# Changelog

本文件使用发布记录（Releases）风格维护版本变更。

## Unreleased

### 新增
- Web UI 字段 chip 支持拖入查询输入框：松手即插入 `字段=""` 并自动聚焦、光标落在引号内直接输入值；输入框已有内容时以 `||` 追加（已有尾部 `&&`/`||` 运算符则直接续接），拖动悬停时输入框高亮虚线框提示可放置（复用 chip 现有拖拽排序手势，不影响排序）。
- **Icon 同款查询**：输入网站地址自动抓取 favicon 并计算 `icon_hash`，一键查询使用相同图标的网站（同框架/同产品默认页面，如 OA、中间件控制台）。`icon_hash` 按 Shodan/FOFA 通用约定计算（base64 编码后 MurmurHash3 x86_32 有符号 32 位）；为保持零依赖，内置纯 Python MurmurHash3 实现（已与 mmh3 包输出逐例对照验证）。
- CLI 新增 `-i/--icon TARGET`：目标支持网站地址（缺省 scheme 自动补全）、本地 icon 文件、已知 `icon_hash` 整数三种形态；位置参数变为附加过滤条件并自动 AND（如 `--icon https://example.com "port=443"`）；提取结果与生成的查询语句打印后走现有单查询/导出链路（limit/fields/去重/深度导出全兼容）。与 `-b/--batch`、`-w/--web` 互斥。
- Web UI 即时预览设置旁新增「Icon 提取」按钮：点击弹窗输入网站地址，自动提取 icon_hash 并填入查询输入框，回车即查；提取报错在弹窗内展示、可直接修改重试（Enter 提交 / Esc 关闭）。新增 `POST /api/icon` 接口：仅接受网址或 hash 整数、不接受本地文件路径，结果带内存缓存避免重复抓取。
- favicon 提取管线：解析页面 `<link rel=...icon...>`（优先级 shortcut icon > icon > apple-touch-icon，支持 data: URI 内嵌图标），回退 `/favicon.ico`；目标直接指向图片时按图片处理；跳过证书校验、10 秒超时、HTML 2MB / 图标 5MB 上限，错误按域名解析失败/超时/HTTP 状态/无图标分类提示。

### 修复
- 修复「不看」排除统计提示落入页面底部不消失的问题：排除全部结果时统计条随表格一起消失，提示文字兜底落到页面底部的消息区，取消排除后不再清除。现「已排除 x 项，显示 x/x」计数只显示在「不看」按钮旁的统计条内（原正常位置），不再落到底部消息区；全部排除时保留统计条，使计数仍有显示位置（PR #2 复核意见）。
- 修复即时预览与深度导出切换时搜索卡片高度跳动 2px 的问题：选项行内 select / 数字输入框 / mini 按钮默认渲染高度不一致（21/23/25px），现统一固定为 25px 并为选项行加最小高度，三种模式间切换布局稳定。
- Icon 提取边界修复（PR #2 复核意见）：2–5MB 的直接图片 URL 改按图标 5MB 上限抓取不再误拒（HTML 仍单独限 2MB）；`/api/icon` 的内存缓存不再保留原始 `icon_bytes`，只缓存接口所需字段。

### 文档
- README 新增「Icon 同款查询」章节（CLI 示例、三种目标形态、提取流程与 hash 约定说明），特性列表、Web UI 交互说明与命令行参数表同步更新。
- AGENTS.md 组件行号表更新，新增 icon 提取模块说明。

### 其他
- 补充 icon 提取与 MurmurHash 单元测试（PR #2 复核意见）：确定性哈希向量（对照 mmh3 输出）与 mock 网络的提取管线用例（link 优先级、data URI、直接图片、scheme 回退、大小与错误分类、缓存剥离原始字节、Web 端禁本地文件）。

## v1.6.0 - 2026-09-19

### 修复
- Web 批量模式进度面板被立刻藏掉：`syncModeContent` 只在深度导出模式下显示导出面板，批量查询共用该面板，启动后 `updateLayout` 把面板 `display` 设为 `none`。进度、错误、取消和下载入口都看不见，按钮只停在「批量查询中...」。现批量模式同样保留面板。
- FOFA API 请求 URL 参数统一编码：`qbase64`/`fields`/`key` 在拼接 URL 前经 `urllib.parse.quote` 编码。base64 字母表含 `+`，未编码时存在被服务端按表单规则解码为空格、查询语句遭破坏的隐患（防御性修复，与 FOFA 官方 SDK 惯例一致）。
- 「取消导出」响应迟缓：取消原先只在进度事件之间生效，任务可能停留在限流休眠（最长 60 秒）或重试退避（最长 30 秒）中迟迟不退出；现在休眠改为分片执行并持续检查取消标志，取消可在约 0.25 秒内中断当前休眠（等待中的 HTTP 请求仍受 45 秒超时约束），批量模式目标间的 2 秒间隔休眠同样改为可中断。
- 自定义字段去重：`dedup_results` 对不在 `FofaResult` 上的字段改为读取 `_extra`。此前 `getattr` 取不到这些字段、一律当成空字符串，只按该字段去重时所有行会被并成一条。
- 占位符密钥：`config.example.json` 里的 `your_fofa_api_key_here` 不在 `is_valid()` 的占位符集合中，复制示例后会被当成已配置并直接请求 FOFA。现与 `your-fofa-key-here`、`your-api-key` 一样视为未配置；示例文件改回与 `DEFAULT_CONFIG` 相同的占位符。
- Web UI 历史下拉的 `title` 属性改用 `escAttr`。`escHtml` 不转义引号，普通 FOFA 查询（含 `"`）会截断提示；特定查询还能逃出属性。
- 顶栏账户信息（剩余查询、过期时间、VIP 等级、中转站今日剩余）写入 `innerHTML` 前经 `escHtml`，避免接口返回值打断页面。
- Web 导出临时目录 `fofa_web_exports` 尽量收成仅当前用户可进入（`0700`），导出文件 `0600`。Windows 上 `chmod` 只影响只读位，同用户读取不受影响。
- Web API 请求体上限 8MiB。`Content-Length` 为负或超过上限时拒绝，不再按声明长度整包读入。
- CI：Linux arm64 改在 `ubuntu-24.04-arm` 上编译（此前与 amd64 共用 `ubuntu-latest`，名为 arm64 的产物实际是 amd64），并在编译前断言机器架构。macOS 只发布 Apple Silicon（M 系列）产物 `fofatoto_mac_arm64`，不再发布 Intel 包。手动触发不再执行 `git tag <分支名>`；Release 只在 `v*` tag 推送时创建。
- 导出任务 TTL 改为从完成时刻（`finished_at`）起算而非创建时刻：运行超过 30 分钟的深度导出此前一完成就可能被 60 秒后台清理删除下载文件，与提示语「完成后约 30 分钟自动清理」不符；现在长任务完成后仍有完整的 30 分钟下载窗口，终态迁移统一经 `_finish_export_task` 保证状态与完成时间同步写入。
- 服务端导出并发守卫的「检查+注册」合并为同一临界区，消除两个并发请求同时通过检查、绕过单任务限制的竞态窗口（`_has_running_export_task` 改为调用方持锁语义）；导出/批量任务线程中获取 client 移入异常保护——配置热重载期间 `get_client()` 抛错时任务会被正确置为 error，不再留下永久卡住并发守卫的 running 幽灵任务；任务线程 `start()` 本身失败（如线程资源耗尽）同样会就地置为终态并向客户端返回错误（`_start_export_thread` 统一收口），堵住幽灵任务的最后一条产生路径。
- 导出任务过期临时文件泄漏：TTL 清理原先只在新建任务时触发，无人发新任务时已完成任务的临时文件（`fofa_web_exports/`）一直滞留；现在 Web UI 启动后台清理线程，每 60 秒自动清理过期任务及临时文件，服务器停止时终止线程。
- Web UI `buildRowsHtml` 属性注入：前端 `escHtml` 仅转义 `& < >`，在 `title="..."` / `href="..."` / `class="..."` 属性上下文中未转义引号，FOFA 返回值含 `"` 时可逃逸属性；新增 `escAttr` 函数补转义 `&quot;` `&#39;`，`buildRowsHtml` 属性值统一使用（文本内容仍用 `escHtml`；主渲染路径 `updateRowNode` 使用 `setAttribute` 不受影响）。
- 导出任务过期后点击下载提示不友好：原先后端统一返回 `Export not ready`（404），且前端 `window.open` 直接把 JSON 错误当页面打开；现在后端区分「任务不存在或已过期」与「尚未完成」两种情况，前端下载改为 `fetch` + Blob，失败时在页面内弹出具体原因（如任务已被 30 分钟 TTL 清理，需重新导出）。

### 新增
- Web 批量模式新增「每目标上限」：每个目标最多导出 N 条（0 为不限制）。1–10000 走单次查询，与命令行 `-l` 一致，避免深度游标对每个目标先探测再等待限流；0 或超过 10000 仍走深度导出。
- 服务端导出任务并发限制：`/api/export` 与 `/api/batch` 在已有未取消任务运行时拒绝新任务（与前端单任务限制一致），防止多标签页或脚本并发多个任务、各自独立限流地消耗 FOFA 配额。

### 优化
- 大批量导出序列化性能：`FofaResult.to_dict()` 改用浅拷贝替代 `dataclasses.asdict()` 递归深拷贝（字段均为 str/dict，行为不变），10 万行级导出的字典转换明显提速。
- 即时预览表头排序改为数值感知：两侧值均为纯数字时按数值比较（如 port 列 `9` 正确排在 `80` 之前），否则退回字符串比较（IP 等混合值行为不变）。

### 其他
- 字段清单收敛为单一来源：新增由 `FofaResult` 派生的 `ALL_FIELD_NAMES`/`KNOWN_FIELDS`（本地自定义字段 `url` 单独由 `CUSTOM_FIELDS` 声明），`search()` 的内联字段集合与 `Exporter.BASE_FIELDS` 改由其统一供给；Web UI 字段分组迁移为 `WEB_FIELD_CATEGORIES` 常量并经新占位符 `__FIELD_CATEGORIES_JSON__` 注入，模块加载时自动校验分组与字段全集一致——新增 FOFA 字段只需改 dataclass 与分组两处（同一文件）。
- 死代码清理：`dedup_results` 的 elif 不可达分支（host/ip/port/domain/protocol 均为 dataclass 属性，`hasattr` 恒真）简化为统一 `getattr` 路径；`ExportTask.results` 未使用字段移除；`main()` 中与 argparse 重复的手动 `-h`/`--help` 检查移除。
- `run_batch_search` 循环不变量（`parse_limit_value`/`_merge_dedup_fields`）提到循环外，避免每次迭代重复解析。
- `FofaWebServer` 内部类 `ThreadingServer` 替换为标准库 `http.server.ThreadingHTTPServer`（Python 3.7+；`allow_reuse_address`/`daemon_threads` 均为其类默认值，无需构造后重复设置）；移除随之无用的 `import socketserver`。
- 修正 `dedup_results` 内联注释（`_extra` 自定义字段参与去重分组，见上方修复条目）。
- 新增单元测试套件 `test_fofatoto.py`（纯标准库 `unittest`，77 个用例，不发真实网络请求）：覆盖字段清单单一来源校验、`_api_fields`/`build_url`/`dedup_results`/`parse_limit_value` 等纯函数、`search()` URL 编码与结果解析（mock urlopen）、`Exporter` 三格式导出、导出任务守卫/终态迁移/TTL 清理（含 `finished_at` 锚点与线程启动失败收口）、Web 批量每目标上限路径选择、版本三处一致性等。
- CI 新增 `check` job 并置于所有构建之前：语法检查（`py_compile`）+ 单元测试 + 版本一致性校验（`APP_VERSION` = `pyproject.toml` = `uv.lock`）；tag 推送时额外校验 tag 与 `APP_VERSION` 匹配，防止发错版本号。

### 文档
- AGENTS.md：移除已在 v1.4.0 删除的 `gan-harness/` 段落；补充测试运行说明与 CI check job 描述；刷新组件行号表。CI 段落改为 Linux 分架构 runner、macOS 仅 M 系列。
- README 下载表去掉 macOS Intel，只保留 `fofatoto_mac_arm64`。

## v1.5.0 - 2026-08-13

### 新增
- 设置弹窗新增「显示历史记录」开关（默认开启，持久化到 localStorage）：关闭后查询历史下拉框不再弹出，但历史记录照常写入，重新开启后仍可用。
- 顶部 API 账户信息自动刷新：每 3 分钟静默刷新一次余额/过期等数据，页面隐藏时暂停、恢复可见时若已过间隔立即补刷；刷新出错（含 429 频率限制）静默忽略、不覆盖上次成功显示，避免打扰。
- Web UI 新增 `--host` 监听地址参数：默认 `127.0.0.1` 仅本机可访问；设为 `0.0.0.0` 时监听所有网卡并打印局域网访问地址；非回环监听时提示 Web UI 无鉴权、局域网内任何人可访问并使用 FOFA 配额的风险；显式指定监听地址后不再自动打开浏览器（启动横幅已打印访问地址，可手动打开）。

### 修复
- 修复查询字段包含 `url` 时 API 返回 `HTTP Error 400` 的问题：`url` 为工具自定义字段（由 `host`/`ip`/`port`/`protocol` 本地拼接），FOFA API 并不提供；现改为请求前剥离 `url`（`_api_fields`）并确保拼接所需字段存在，导出与去重仍按本地拼接逻辑输出。
- 修复无图形环境自动打开浏览器报错刷屏：SSH 会话（检测 `SSH_CONNECTION`/`SSH_CLIENT`）与 Linux 无 DISPLAY 环境跳过自动打开并提示手动访问；WSL 环境改由 `explorer.exe` 调起 Windows 默认浏览器。此前裸 `webbrowser.open()` 在 WSL 会触发 `gio: Operation not supported`，在 SSH + X11 转发的服务器上会触发 X11 转发弹窗与 `xdg-open: no method available` 报错。
- 修复虚拟滚动滚动条长度随滚动位置忽大忽小（向下滚到底部附近尤其明显）：撑高行 `<td>` 残留 CSS padding/border、撑高行/数据行角色切换时残留 `height`/`colSpan` 等内联样式，导致 `scrollHeight` 随窗口波动、浏览器钳制 `scrollTop`。
- 修复虚拟滚动滚动时数据行内容闪动：原每帧 `innerHTML` 整体重建/按位置重映射导致所有可见行 `textContent` 被改写；改为按行号绑定的节点所有权映射，保持不变的行零 DOM 写入。
- 修复虚拟滚动滚动时行背景在浅蓝/白间闪烁：斑马纹改用按绝对行号 `vs-stripe` 类（脱离 DOM 位置），并清撑高行残留的条纹类；滚动期间抑制 hover 第三色。
- 修复虚拟滚动向下滚动时数据行上下抖动（第50行跳到51行又变回）：行高为分数值（`line-height:1.5` + `font-size:11.5px`）导致 `scrollHeight` 随窗口 ±2px 波动；固定 `td`/`th` `line-height:18px` 使行高为整数 33px，`scrollHeight` 恒定。
- 修复虚拟滚动滚动时个别行高度变得特别大：撑高行复用时残留 `_idx` 行号标记，被误判为「内容未变」直接复用、带着撑高行的巨大 `style.height` 渲染；撑高行重塑时清除 `_idx`。
- 修复虚拟滚动向下滚动时数据从顶部进入（行顺序颠倒）：节点插入锚点改为 `bottomSpacer` 之前，DOM 顺序与行号升序一致。
- 修复虚拟滚动首次滑动数据全部消失：撑高行未锚定首尾，`need` 调整的增删破坏其位置；改为先识别撑高行、增删均绕开它们（删 `bottomSpacer.previousSibling`、增 `insertBefore(new, bottomSpacer)`）。
- 修复「不看」/「选取查询」排除或排序后表格显示陈旧错误数据：`stabilizeColumnWidths` 提前返回导致 `vsLastWindow` 未失效、所有权映射复用了错位的旧行；`renderResults` 设 `currentView` 后立即 `vsLastWindow=null` 强制全量重建。
- 修复「不看」与「选取查询」无法选取字段值为空的单元格：`pickTableClick` 的 `if(!value)return` 守卫拦截了空值，移除后空值可正常排除（匹配空字段行）或加入查询（生成 `field=""`）。
- 修复切换模式 tab（即时预览/深度导出/批量模式）后输入框被自动聚焦导致展开并弹出历史下拉框：`switchMode` 移除末尾的 `.focus()`；输入框 `autofocus` 属性保证首屏仍自动聚焦。
- 修复查询输入框展开后显示滚动条：`:focus` 状态的 `overflow-y:auto` 在超长查询触顶时显示滚动条，移除后回退 `overflow:hidden` 不再出现滚动条。

### 优化
- Web UI 访问日志显示来源 IP，便于定位请求来源。
- Web UI 查询输入框改为 textarea：超长查询语句聚焦时自动向下展开并换行，高度自适应（上限接近视口高度）；失焦时收起为单行。
- 输入框聚焦时浮起脱离文档流（`position:absolute` + 阴影），展开后不撑开 `.card` 容器、不下推字段行，整体 UI 布局稳定。
- 失焦时 `white-space:nowrap` 强制单行显示，彻底消除多行内容第二行文字顶部在输入框内残留显示的问题（任意浏览器缩放下均不出现）。
- 历史记录下拉框跟随 textarea 展开高度动态调整 `top`，不再遮挡输入框。
- `Enter` 提交搜索且不插入换行符；`Shift+Enter` 可手动换行。

### 文档
- 重写 README：结构重排并全面核对当前实现，补充 Web UI 功能说明（虚拟滚动、字段选取器、查询历史、设置项、账户自动刷新）、`--host`/`-c` 参数、中转站适配、配置热更新与从源码运行说明（含 Python 直接运行与 `uv run` 两种方式）。

### 其他
- 版本号同步：`APP_VERSION`、`pyproject.toml`、`uv.lock` 统一为 `1.5.0`。

## v1.4.0 - 2026-07-22

### 新增
- 第三方中转站账户信息自动识别：内置 `RELAY_INFO_APIS` 域名映射表（已支持 `fafaapi.info`），当 `config.json` 的 `url` 匹配已知中转站域名时，自动改用对应的账户查询接口（如 `/fofaapi/v1/validate-key`）替代标准 FOFA `/api/v1/info/my`，并将响应归一化为统一字段格式；域名后缀匹配兼容末尾多输入 `/` 的情况。
- Web UI 与 CLI 账户信息适配中转站：显示「中转站」标识、有效/无效状态、剩余查询、今日剩余、过期时间、首次使用时间；标准 FOFA 仍显示 VIP 等级与服务器状态。
- CLI 新增 `-c`/`--check` 快速检测命令：仅显示 Banner 与账户状态后退出，不执行查询。
- 即时预览改为真·虚拟滚动：DOM 恒定只渲染视口附近约 40 行（上下各 10 行缓冲），滚动条代表全量数据，可直接拖到任意位置；1 万条数据下滚动、排序、过滤均流畅。
- 即时预览新增「适应窗口宽度」开关（设置弹窗，默认开启）：开启时表格总宽贴合窗口、永不出现横向滚动条；关闭时列宽按内容自然宽度、内容过宽时显示横向滚动条。两种模式滚动时列宽均稳定不抖动。
- 字段 chip 支持拖拽排序：拖动字段标签可调整顺序，顺序直接影响 FOFA 返回列及导出文件的列顺序。

### 修复
- 修复字段「+」按钮被 `renderChips` 整体清空导致增删字段后「+」永久消失、无法再添加字段的 bug。
- 修复字段面板选中字段后因重绘导致点击目标脱离 DOM、被误判为「点击外部」而关闭面板的问题（改用 mousedown 记录按下位置）。
- 修复「不看」排除后导出 TXT 仍包含被排除行的问题（TXT 分支原先绕过过滤器，现 CSV/JSON/TXT 均应用排除过滤）；导出完成提示改为真实导出条数。
- 修复深滚动位置下用「不看」大幅过滤后表格空白的问题（渲染前将 scrollTop 钳制到合法范围）。
- 修复首次查询时表格底部留白未填满的问题（先确定容器最终高度再渲染虚拟窗口）。
- 修复多选字段后出现横向滚动条的问题（th 表头补充 `overflow:hidden` 裁剪溢出文字）。
- 修复关闭列宽开关后滚动时列宽抖动、横向滚动条时隐时现的问题（改用自然像素列宽 + fixed 布局）。
- 查询框与字段搜索框禁用浏览器原生自动补全（`autocomplete="off"`），避免浏览器历史下拉遮挡页面自带的查询历史。

### 优化
- 即时预览大数据量渲染性能：以虚拟滚动替代全量 DOM 渲染，配合列宽锁定（每次查询测量一次），消除滚动卡顿与列宽抖动。
- 列宽按内容自然宽度测量后归一化，宽内容字段按比例收窄，始终自适应窗口。

### 其他
- 移除无用的 AI 工具残留文件（`.monkeycode/`、`gan-harness/`、`CLAUDE.md`）。
- 版本号同步：`APP_VERSION`、`pyproject.toml`、`uv.lock` 统一为 `1.4.0`。


## v1.3.0 - 2026-07-09

### 新增
- Web UI 即时预览模式新增「全部数据」开关（`instantFull`），可切换搜索全部数据（不止一年），与深度导出的「全部数据」语义一致。原先即时预览硬编码 `full:false`（仅近一年数据），现在通过复选框把该值传给 `/api/search` 的 `full` 参数，后端无需改动。
- Web UI 即时预览新增字段值选取器：结果区操作栏「不看」和「选取查询」两个按钮，点击进入选取模式后鼠标点击任意单元格即可选取该字段值。
  - 「不看」：多条件排除筛选，选取的值从当前结果中排除（本地过滤），排除项以红底 chip 显示在数量下拉框右侧，可单独移除。
  - 「选取查询」：选取的值以 `字段="值"` 形式智能追加到查询框，配合「选取查询后自动搜索」开关可自动执行搜索。
- Web UI 配置热更新：`ConfigManager` 新增 `get_client()` 方法按需重新读取 `config.json` 并按 `(url, key)` 签名缓存 `FofaClient`，`FofaWebHandler` 通过 `_current_client()` 统一获取，用户修改配置后无需重启服务即可生效。
- Web UI 设置弹窗：「全部数据」和「选取查询后自动搜索」两个开关收纳到即时预览选项行的「设置」弹窗中，点击展开、点击外部自动关闭。

### 优化
- 美化即时预览数量下拉菜单：`appearance:none` 去掉原生箭头，改用自定义 SVG 箭头（hover/focus 变蓝），字号和配色与 `mini-btn` 统一。
- 即时预览统计栏状态消息改为显示在「不看/选取查询」按钮旁的 `previewStatus` 位置，不再写入底部 `messageArea`，避免破坏页面布局产生滚动条。`showMessage`/`clearMessage` 现在会调用 `updateLayout()` 重算表格高度；`fitResultsHeight` 计算时扣除 `messageArea` 高度。

### 修复
- 修复深度导出/批量任务运行中切换到即时预览会隐藏导出面板、丢失进度与下载入口的问题：`switchMode` 在有运行中的导出任务（`exportPollTimer` 存在）且切换到不同模式时拦截并提示，避免用户误以为任务丢失。
- 修复即时预览点击表头排序后统计栏「独立IP」归零的问题：`sortBy` 排序后通过 `renderCurrentView` 重新统计独立 IP 数传给 `renderResults`。
- 修复清空所有字段后即时预览/导出/批量发送空 `fields` 导致 FOFA 请求异常的问题：`_handle_search`、`_handle_export`、`_handle_batch` 统一用 `body.get("fields") or DEFAULT_FIELDS` 兜底空字段。
- 修复后端未校验 `size`/`fill_percent`/`max_size` 范围的问题：`size` 强制 `max(1, min(size, 10000))` 并捕获类型异常；`fill_percent` 限定 `(0, 1]`，越界或非法时回退 0.8；`max_size` 负值回退 0；`full` 统一 `bool()` 规范化。

### 其他
- 版本号更新：`v1.2.1` -> `v1.3.0`。
- 完成语法检查验证（`python -m py_compile fofatoto.py`）。

## v1.2.1 - 2026-06-23

### 修复
- 修复 Nuitka onefile 模式下配置文件被写入 PID 子目录（如 `8968\config.json`）、进程退出即丢失的问题。根因：`_get_config_dir` 误用 Nuitka 内部环境变量 `NUITKA_ONEFILE_PARENT`（其值为进程 PID，并非路径），`Path(<PID>).resolve()` 被解析为当前工作目录下的 PID 子目录。现改用 bootstrap 注入的 `NUITKA_ONEFILE_DIRECTORY`（原始可执行文件所在目录）定位配置目录。
- 修复 Web UI 导出任务和临时文件从不清理导致的内存与磁盘泄漏：新增 30 分钟 TTL 自动清理机制（`_cleanup_export_tasks`），过期任务及其临时文件会被自动删除。
- 修复 `FofaWebHandler.log_message` 实现错误：原本输出 `args[0]` 而非 `format % args`，导致日志内容错误。
- 修复 `build_url` 中 HTTPS 端口推断仅识别 443 的问题：现在同时覆盖 8443、4443 等常见 HTTPS 端口。
- 修复 `dedup_results` 中空键元组跳过去重的问题：空键也纳入 `seen` 集合，避免多条全空记录未被去重。
- 修复 `export_json` 字段过滤顺序导致 JSON schema 不一致的问题：指定字段时保留所有字段（空值输出为空字符串），未指定字段时才过滤空值。
- 修复 `_handle_search` 未校验 `size` 下界的问题：负值或 0 会传入 FOFA API，现在强制 `max(1, min(size, 10000))`。
- 修复 `_find_available_port` 全部端口被占用时返回已占用端口的问题：现在抛出明确的 `OSError`。
- 修复 `before_time` 解析失败时回退为原始字符串可能导致循环的问题：所有解析失败统一设为 `None`。

### 优化
- 提取 `_merge_dedup_fields` 公共函数，消除 `handle_single_mode` 和 `run_batch_search` 中的重复代码。
- `FofaResult._extra` 默认值改用 `field(default_factory=dict)`，删除冗余的 `__post_init__`。
- 删除 `search()` 重试循环中不可达的 `for-else` 死代码及 `last_error` 无用赋值。
- 非交互环境下进度条降频输出（每 10 批或达目标时才打印），避免日志膨胀。
- `webbrowser.open` 添加异常处理，无桌面环境时不崩溃。

### 其他
- 版本号更新：`v1.2.0` -> `v1.2.1`。
- 完成语法检查与实际查询、深度导出、Web UI 接口回归验证。

## v1.2.0 - 2026-05-11

### 新增
- 新增零依赖本地 Web UI，提供即时预览、深度导出、批量注入和本地查询历史。
- Web UI 默认监听 `127.0.0.1:17380`，端口被占用时自动后延；支持 `-w`/`--web` 显式启动和 `--port` 指定端口。
- 无参数运行或双击二进制文件时自动进入 Web UI，便于 Windows 用户直接使用。
- 即时预览支持字段选择、10 到 10000 的数量预设、列排序、URL 跳转、结果保留和当前预览 CSV/JSON/TXT 导出。
- 深度导出以后台任务执行，按 `before` 时间游标分批拉取数据，并在页面内展示进度、目标、配额、耗时和下载入口。
- 批量注入支持占位符批量替换目标，并复用深度导出流程合并结果。
- 本地查询历史基于浏览器 localStorage，支持搜索框内联建议、过滤、点击插入、删除和键盘选择。

### 优化
- Web UI 顶栏展示版本信息、GitHub 仓库链接和账号状态，服务器状态使用“正常/异常”文字。
- Web UI 的即时预览、深度导出和批量注入按模式隔离展示，切换模式时保留已有查询结果和导出任务状态。
- Web UI 响应式布局适配不同屏幕高度，查询历史下拉与结果表格会按窗口剩余空间自适应。
- 默认字段统一为 `host,ip,port,protocol,domain,title,server,country,city`，CLI 与 Web UI 复用同一份配置。
- 深度抓取尾批按剩余目标动态请求，并为大目标保留 1000 条尾批下限，兼顾配额消耗与 FOFA 分批拉取稳定性。
- 深度抓取增加自适应请求间隔，遇到 `[-501]`、超时等临时失败时自动放慢分批请求频率和请求内重试节奏，成功后逐步回落。
- 优化 CLI 输出，修正 Banner 对齐、Windows/非交互环境颜色转义、账号状态颜色一致性，以及进度/重试消息的换行表现。

### 修复
- 修复深度抓取时 `-l`/`--limit` 未作为有效目标显示与计算的问题，进度条改按有效目标推进。
- 修复深度抓取请求失败后无法保留已获取结果的问题；重试后仍失败时会生成部分导出文件。

### 文档
- 更新 README，补充 Web UI 使用方式、默认端口、深度导出流程和默认字段说明。
- 文档统一使用 `before` 时间游标分批拉取描述，避免与传统分页概念混淆。

### 其他
- 版本号更新：`v1.1.3` -> `v1.2.0`。
- 完成语法检查验证。

## v1.1.3 - 2026-04-23

### 修复
- 修复 `domain` 字段可能被推断结果覆盖的问题（仅在空值时补全）。
- 修复全量抓取进度条颜色阈值判断错误（50% 分界恢复正常）。
- 修复去重在空/无效字段场景下可能误删结果的问题。

### 优化
- 新增统一的 `-l/--limit` 参数解析与校验，仅支持正整数或 `max`。
- 新增 `--fill` 取值范围校验，限制为 `(0, 1]`。
- 优化单格式导出逻辑，自动修正输出文件后缀，避免后缀与内容不一致。

### 其他
- 版本号更新：`v1.1.2` -> `v1.1.3`。
- 完成语法检查与关键边界回归验证。

## v1.1.2 - 2026-04-16

### 修复
- 合并并恢复审计修复分支中的关键改动，补齐此前遗漏的真实修复。
- 修复 IPv6 处理、`build_url` 生成、导出与去重相关问题。
- 修复进度条颜色判断、配额统计与配置目录创建等稳定性问题。

### 文档
- 更新 README，补充批量查询与 `-l` 参数行为说明。

## v1.1.1 - 2026-03-27

### 修复
- 修复导出时 `url` 字段为空的问题。
- `url` 查询场景自动补全 `host,ip,port,protocol` 字段，提升结果完整性。
- 修复 `build_url` 回退逻辑，优先使用可用 `host` 值构建 URL。
- 支持 `--dedup url` 去重，保证 URL 维度去重可用。

### 其他
- 版本号更新：`v1.1.0` -> `v1.1.1`。

## v1.1.0 - 2026-03-26

### 新增
- 新增批量查询能力（从文件逐行读取查询目标）。
- 新增占位符批量查询模式，支持将模板查询按目标列表展开执行。

### 修复
- 修复 FOFA API 地址与 CI 版本号硬编码相关问题。

### 其他
- 版本号更新为 `v1.1.0`，同步仓库链接与 Release 说明。

## 历史记录

### 未发布变更
- 文档：修复 `README.md` 重复内容问题（提交：`ad1c4e1`）。
