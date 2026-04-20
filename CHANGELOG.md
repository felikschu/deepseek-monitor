# DeepSeek 网页端变更记录

> 本文档记录通过技术手段追踪到的 DeepSeek 网页端变化。所有条目均标注了证据来源。

---

## 2026年4月

### 4月20日 — 新增“DeepSeek 网页动向”语义摘要板块

**类型**: 监控系统升级

**详情**:
- 新增 `utils/deepseek_bundle_semantics.py`，把 `coder / vision / agent / api / pricing` 从关键词命中提升为结构化语义
- 前端 `Bundle 深挖` 现在会展示隐藏能力、路由模式、API 家族，不再只显示 API 数量和依赖数量
- Dashboard 新增 “DeepSeek 网页动向” 板块，分开展示：
  - 官网/文档公开表达了什么
  - chat bundle 里已经埋了什么隐藏能力
- 官方页面监控的 diff 粒度升级，新增：
  - `route_patterns`
  - `api_families`
  - `hidden_capabilities`
  - `coder_signals`
  - `vision_signals`
  - `agent_signals`
- 修复 bundle 语义分析因“新字段上线但内容为空”导致的伪变化，避免 vendor/runtime 噪音干扰高信号摘要
- 新增测试覆盖网页摘要逻辑和 DeepSeek bundle 语义抽取
- 实测当前 DeepSeek chat 公开前端仍为：
  - `main.e0f8beaa34.js`
  - `commit-id: 4b9671fa`
  - `commit_datetime: 2026/04/16 13:01:46`

### 4月19日 — 侦察方法升级为“页面 + 同源脚本”双层探针

**类型**: 监控系统升级

**详情**:
- 新增 `OfficialMonitor` / `CompetitorMonitor` 的同源脚本探针，不再只看 HTML
- 新增竞品商业化信号抽取：价格、套餐、Token Plan、MiniMax Agent、龙虾套餐、Code Interpreter 等
- 新增可疑链接发现与商业动作摘要：`promotion` / `token-plan` / `mcp` / `agent` / `research/<id>`
- 新增智谱 `GLM-5V-Turbo` 研究页、MiniMax `Referral Program` 与 `MCP News` 监控面
- 修复脚本探针优先级，优先抓 `app/main/page`，避免 `runtime/vendor` 抢占探测名额
- 竞品变化时间支持优先回填页面发布时间信号，不再只依赖 HTTP `Last-Modified`
- 竞品侦察增加单页超时保护，避免单个慢页面卡住整轮报告
- 新增 `scripts/recon_competitors.py`，可直接生成智谱 / MiniMax 侦察报告
- 修复 `model_configs_change` 历史误报在高信号摘要里继续展示的问题
- 前后端统一：CLI 模式和 Dashboard 的 `/api/check` 都会跑竞品侦察
- 新增自动化测试，覆盖提取器和高信号过滤逻辑

### 4月7日 — 三模型模式代码全面上线（当日三版热更）

**类型**: 重大代码部署

**证据来源**: 生产 JS 内嵌元数据、HTML `<meta name="commit-id">`、JS 源码分析、CDN HEAD 请求

**详情**:
- 4月7日当天 DeepSeek 连续进行了 **三次前端热部署**：

| 时间 | commit-id | JS 文件 | 状态 | 说明 |
|------|-----------|---------|------|------|
| 12:58 | `6f08af6b` | `main.a7e3d12518.js` | 已下线 | 中间版本，存在约 4 小时 |
| 17:13 | `086dedc0` | `main.b8c3389fe2.js` | 已下线 | 中间版本，存在约 1 小时 |
| **18:00** | **`e11cf433`** | **`main.c578e6e518.js`** | **当前线上版本** | 新增多模型切换判断条件 |

- **关键发现**：`default` / `expert` / `vision` 三种模型模式的完整 UI 逻辑已**全部编译进生产包**
  - `expert` 对应 R1/思考模式（不支持文件上传）
  - `vision` 对应多模态/视觉模式（支持图片上传）
  - `default` 对应 V3.2 非思考模式
- 模型切换器是否渲染取决于服务端 `/api/v0/client/settings` 返回的 `model_configs` 数量，说明前端已就绪，服务端正在**灰度放量**
- CDN `Last-Modified`（最终版）: `Tue, 07 Apr 2026 09:26:01 GMT`
- 注意：monitor 在 09:27-09:33 之间因多次触发检查产生过重复记录，已通过在 `save_cdn_resource` 和 `save_resource_hash` 中加入去重逻辑修复

---

### 4月3日 — CDN 新部署 + 短暂异常

**类型**: 部署 + 故障

**证据来源**: HTTP 响应头 `Last-Modified`、status.deepseek.com uptimeData

**详情**:
- 所有 CDN 静态文件统一更新至 `2026-04-03 08:20:13 GMT`（精确到秒，说明是一次统一部署操作）：
  - `main.cd620c850b.js` (1,104,338 bytes)
  - `main.02cdcfca28.css` (220,799 bytes)
  - `default-vendors.fb66be1c50.js` (679,010 bytes)
- status.deepseek.com 记录了 103 秒轻微中断（`outages: {m: 103}`），事件代号 `t7vhwd8z5ts0`

**CDN ETag**:
- main.js: `"d55237054923c405b8eebdf1abdffb88"`
- main.css: `"d55237054923c405b8eebdf1abdffb88"`
- vendors.js: `"a584220e6799cd0f518a73fd942b3c3d"`

---

### 4月1日 — 前端代码提交

**类型**: 代码变更

**证据来源**: 生产 JS 内嵌元数据

**详情**:
- **commit-id**: `1fcf6559`
- **commit-datetime**: `2026/04/01 21:01:36`（UTC+8）
- **前端包版本**: `@deepseek/chat` v1.5.8
- **API 版本**: v1.7.1
- 此版本为当前线上运行版本（截至 2026-04-03）

---

## 2026年3月

### 3月31日 — 第三轮故障

**类型**: 故障

**证据来源**: status.deepseek.com uptimeData

**详情**:
- API 服务：`outages: {p: 1974}` ≈ 33 分钟部分中断
- 网页服务：`outages: {m: 1820}` ≈ 30 分钟完全中断
- 事件代号: `lqrmk53rs6d3`
- 三天连续故障中的最后一天

---

### 3月30日 — 第二轮宕机（7+ 小时）

**类型**: 重大故障

**证据来源**: status.deepseek.com uptimeData、多家媒体报道

**详情**:
- 网页端：`outages: {m: 26023}` ≈ **433 分钟（7.2 小时）完全中断**
- 事件代号: `rjs0ljjlqhsw`
- DeepSeek 网页端史上最长单日中断
- 前一日（3/29）故障修复后不久再次崩溃

---

### 3月29日 — 模型静默升级 + 史上最长宕机（开始）

**类型**: 模型升级 + 重大故障

**证据来源**: status.deepseek.com uptimeData、用户报告（掘金、知乎、搜狐、新浪）、当前 JS 代码分析

**详情**:

#### 模型静默升级（宕机前）
用户在宕机前观察到的变化：
- **身份标识变化**: 模型自报从"一款纯文字AI助手"变为明确的"DeepSeek-V3模型"
- **知识截止日期更新**: 从 2025年初更新到约 2026年1月（能回答2025美国大选结果）
- **SVG 生成能力提升**: 鹈鹕骑自行车测试任务效果明显改善
- **代码生成能力提升**: 一次性前端页面生成质量大幅提高

#### 宕机事件
- 21:35 首次检测到异常
- 网页端：`outages: {m: 5580}` ≈ 93 分钟标记时间（用户实际体验中断从 29日 21:35 到 30日 10:33，近 13 小时）
- 事件代号: `v5mmslnf9249`

#### 宕机后功能回退
搜狐等媒体报道：
> "故障修复后，部分功能出现'回退'现象。知识截止日期恢复为2025年5月，自我介绍中也不再提及版本号。"

这暗示灰度部署的新模型在出问题后被回退。

---

### 3月27日 — 法律文档更新

**类型**: 法律/合规

**证据来源**: CDN HTTP 响应头 `Last-Modified`

**详情**:
- **Terms of Use**: `Last-Modified: Thu, 27 Mar 2026 03:50:07 GMT`
- **Privacy Policy**: `Last-Modified: Thu, 27 Mar 2026 03:50:07 GMT`
- 两份文档的修改时间完全一致到秒，说明是统一更新
- 法律文档更新通常预示重大产品变更（3/29 的宕机+升级印证了这一点）

---

### 3月18日 — 网页/APP 性能异常

**类型**: 故障

**证据来源**: status.deepseek.com uptimeData

**详情**:
- 事件代号: `4hhgg6f06mfj`
- 已解决

---

### 3月10日 — 网页/APP 不可用

**类型**: 故障

**证据来源**: status.deepseek.com uptimeData

**详情**:
- `outages: {p: 2014}` ≈ 33 分钟部分中断
- 事件代号: `ky5fwrzf9mfp`

---

### 3月5日 — 网页不可用

**类型**: 故障

**证据来源**: status.deepseek.com uptimeData

**详情**:
- `outages: {m: 2421}` ≈ 40 分钟完全中断
- 事件代号: `yq7pjh6s282v`

---

## 已删除的测试版本

### main.6184d0a79e.js（时间未知）

**类型**: 测试部署（已删除）

**证据来源**: CDN 404 响应（`x-amz-error-code: NoSuchKey`）

**详情**:
- 此文件在 CDN 上返回 404，已被删除
- 文件名 hash 格式 `6184d0a79e` 与生产版 `cd620c850b` 不同
- 根据之前的分析，此版本包含**三模式切换 UI** 的代码：
  - 快速模式 / Instant Mode
  - 专家模式 / Expert Mode（DeepThink）
  - 多模态模式 / Vision Mode
- ~~当前生产版仅使用两开关模式（DeepThink + Search），无三模式切换~~
- **更新（2026-04-07）**: `main.a7e3d12518.js` 已将三模式切换的完整代码全面编译进生产包，服务端通过 `model_configs` 配置进行灰度放量

---

## 当前版本技术快照

### commit 元数据

| 字段 | 值 |
|------|------|
| commit-id | `e11cf433` |
| commit-datetime | `2026/04/07 18:00:18` |
| commit 简报 | 优化上传按钮提示文案逻辑，新增多模型可切换状态的判断条件 |
| 前端包 | `@deepseek/chat` v1.5.8 |
| API 版本 | v1.7.1 |

### Feature Flags（远程配置）

通过 `/api/v0/client/settings` API 分发，前端通过 `nB.getFeature()` 读取：

| Flag 名称 | 默认值 | 说明 |
|-----------|--------|------|
| `chat_hcaptcha` | `false` | 海外用户 hCaptcha 验证码 |
| `allow_file_with_search` | `false` | 联网搜索时允许上传文件 |
| `pow_prefetch` | `false` | PoW 反滥用挑战预取 |
| `session_prefetch` | `true` | 会话预取加速 |
| `sse_auto_resume_timeout` | `2000` (ms) | SSE 断线自动重连超时 |
| `normal_history_and_file_token_limit` | `undefined` | 普通模式历史+文件 token 限制 |
| `r1_history_and_file_token_limit` | `undefined` | R1 模式历史+文件 token 限制 |
| `hif_max_retry_interval_secs` | `600` | 最大重试间隔（秒） |
| `launch_clean_session_interval_seconds` | `21600` | 自动清理会话间隔（6小时） |
| `volcengine_enabled` | 服务端控制 | 火山引擎相关功能 |

### 其他内嵌标志

| 标志 | 值 | 说明 |
|------|------|------|
| `ab_test` | `false` (硬编码) | A/B 测试框架存在但当前关闭 |

### API 端点清单

| 端点 | 说明 |
|------|------|
| `/api/v0/chat/completion` | 聊天补全（核心） |
| `/api/v0/chat/regenerate` | 重新生成 |
| `/api/v0/chat/continue` | 继续对话 |
| `/api/v0/chat/stop_stream` | 停止流式输出 |
| `/api/v0/chat/resume_stream` | 恢复流式输出 |
| `/api/v0/chat/edit_message` | 编辑消息 |
| `/api/v0/chat/history_messages` | 历史消息 |
| `/api/v0/chat/message_feedback` | 消息反馈 |
| `/api/v0/chat/create_pow_challenge` | 创建 PoW 挑战 |
| `/api/v0/chat_session/create` | 创建会话 |
| `/api/v0/chat_session/delete` | 删除会话 |
| `/api/v0/chat_session/delete_all` | 删除全部会话 |
| `/api/v0/chat_session/fetch_page` | 分页获取会话 |
| `/api/v0/chat_session/update_pinned` | 置顶会话 |
| `/api/v0/chat_session/update_title` | 更新会话标题 |
| `/api/v0/client/settings` | 客户端远程配置（Feature Flags） |
| `/api/v0/client/span` | 客户端埋点上报 |
| `/api/v0/client/wechat_js_sdk_signature` | 微信 JS SDK 签名 |
| `/api/v0/file/upload_file` | 文件上传 |
| `/api/v0/file/fetch_files` | 获取文件列表 |
| `/api/v0/file/preview` | 文件预览 |
| `/api/v0/users` | 用户信息 |
| `/api/v0/users/settings` | 用户设置 |
| `/api/v0/users/update_settings` | 更新用户设置 |
| `/api/v0/users/create_email_verification_code` | 邮箱验证码 |
| `/api/v0/users/create_sms_verification_code` | 短信验证码 |
| `/api/v0/users/create_guest_challenge` | 访客挑战 |
| `/api/v0/users/logout_all_sessions` | 登出所有设备 |
| `/api/v0/users/set_birthday` | 设置生日 |
| `/api/v0/share/create` | 创建分享 |
| `/api/v0/share/delete` | 删除分享 |
| `/api/v0/share/list` | 分享列表 |
| `/api/v0/share/content` | 分享内容 |
| `/api/v0/share/fork` | 复刻分享 |
| `/api/v0/download_export_history` | 下载导出历史 |
| `/api/v0/export_all` | 全部导出 |

### 补全请求参数

| 参数 | 说明 |
|------|------|
| `chat_session_id` | 会话 ID |
| `parent_message_id` | 父消息 ID |
| `prompt` | 用户输入 |
| `ref_file_ids` | 关联文件 ID |
| `thinking_enabled` | 是否开启深度思考 |
| `search_enabled` | 是否开启联网搜索 |
| `preempt` | 抢占模式 |

### 环境配置

| 环境 | 域名 | 状态 |
|------|------|------|
| 生产 | `chat.deepseek.com` | 正常 |
| 测试 | `chat-test.*.deepseek.com` | 内部 |
| 预发 | `chat-dev.deepseek.com` | 403 (WAF 保护) |

### CDN 信息

- **提供商**: 华为云 CDN（S3 兼容后端，`x-amz-*` 响应头）
- **基础 URL**: `https://fe-static.deepseek.com/chat/static/`
- **SPA 架构**: HTML 极简，所有内容由 JS bundle 渲染

---

## 故障统计（2026年3月）

| 日期 | 中断分钟 | 类型 | 事件代号 |
|------|---------|------|---------|
| 3/5 | 40 | 完全中断 | `yq7pjh6s282v` |
| 3/10 | 33 | 部分中断 | `ky5fwrzf9mfp` |
| 3/18 | - | 性能异常 | `4hhgg6f06mfj` |
| 3/29 | 93+ (实际~13h) | 重大故障 | `v5mmslnf9249` |
| 3/30 | 433 | 重大故障 | `rjs0ljjlqhsw` |
| 3/31 | 63 | 部分+完全 | `lqrmk53rs6d3` |
| 4/3 | 2 | 轻微异常 | `t7vhwd8z5ts0` |

**3月网页端整体可用性**: ~98.61%（来自 status.deepseek.com）

---

## 追踪方法总结

| 信号 | 获取方式 | 检测能力 |
|------|---------|---------|
| `commit-id` | 抓取 HTML `<meta name="commit-id">` | 前端代码更新 |
| JS 文件名 hash | 抓取 HTML 中的 `<script src>` | 部署新版 |
| CDN `Last-Modified` | HEAD 请求 CDN 资源 | 静默热更新 |
| `/api/v0/client/settings` | 需登录 token，轮询 feature flags | 服务端功能开关变化 |
| 法律文档 `Last-Modified` | HEAD 请求 CDN 法律文档 | 预示重大变更 |
| status page uptimeData | 爬取 status.deepseek.com JSON | 宕机时间和严重程度 |
| JS 内容分析 | 下载并正则匹配 | API 端点、feature flags、版本号变化 |
