# DeepSeek Monitor

追踪 DeepSeek 全平台变化的监控系统。自动检测网页端部署、Feature Flags 变化、API 端点增减、法律文档更新、GitHub 开源动态和官方状态页面事件。

## 功能

- **前端部署追踪** — 检测 commit-id、JS/CSS 文件 hash 变化
- **Feature Flags 监控** — 提取 8+ 个远程功能开关，对比历史变化
- **API 端点追踪** — 监控 36+ 个 `/api/v0/*` 端点的增减，支持点击查看详细说明
- **CDN 资源追踪** — 监控 JS/CSS 上传时间和 ETag
- **法律文档检测** — Terms of Use / Privacy Policy 更新预警
- **GitHub 监控** — 追踪 deepseek-ai 组织的新仓库、代码推送、Release 发布
- **Status Page 监控** — 监控 status.deepseek.com 的服务状态和故障事件
- **Web Dashboard** — 暗色主题可视化面板，支持一键检查和报告导出

## 快速开始

### 1. 下载并安装

```bash
git clone https://github.com/felikschu/deepseek-monitor.git
cd deepseek-monitor

# 一键安装（安装依赖 + 创建桌面快捷方式）
bash scripts/setup.sh
```

### 2. 启动

**macOS**: 双击桌面的 `DeepSeek Monitor.command`（安装脚本自动创建）

**手动启动**:

```bash
cd deepseek-monitor
python3 web/server.py
```

打开 http://localhost:8765 查看 Dashboard。

### 3. 设置定时检查

```bash
crontab -e
# 每3小时自动检查一次（包含前端、GitHub、Status Page）
0 */3 * * * cd /path/to/deepseek-monitor && python3 web/server.py --no-open >> logs/cron.log 2>&1 &
```

## 已发现的真实事件

以下是通过本系统追踪到的 DeepSeek 网页端变化，所有结论均基于技术证据（HTTP 响应头、JS 代码分析、status.deepseek.com 官方数据）：

### 2026年3月27日 — 法律文档更新

- **证据**: CDN HTTP `Last-Modified` 响应头
- Terms of Use 和 Privacy Policy 同时更新至 `2026-03-27 03:50:07 GMT`（北京时间 11:50:07）
- 两份文档修改时间精确到秒一致，说明是统一操作
- **意义**: 法律文档更新通常预示重大产品变更

### 2026年3月29日 — 模型静默升级 + 13小时宕机

- **证据**: status.deepseek.com 官方状态页面、用户报告（掘金、知乎、搜狐、新浪等）
- 网页/APP 服务从 29日 21:35 开始异常，持续到 30日 10:33 修复（近 13 小时）
- 事件代号: `v5mmslnf9249`
- **用户观察到的变化**（宕机前）:
  - 模型自报身份从"纯文字AI助手"变为明确的"DeepSeek-V3模型"
  - 知识截止日期从 2025年初 更新到 2026年1月（能回答2025美国大选结果）
  - SVG 生成和代码生成能力显著提升
- **宕机后回退**: 修复后知识截止日期恢复为 2025年5月，自我介绍不再提及版本号
- 这暗示灰度部署了新模型但出了问题，随后被回退

### 2026年3月30日 — 第二轮宕机（7+ 小时）

- **证据**: status.deepseek.com 官方状态页面 — 约 433 分钟完全中断
- 事件代号: `rjs0ljjlqhsw`
- 3月29日故障修复后不久再次崩溃
- DeepSeek 网页端史上最长单日中断记录

### 2026年3月31日 — 第三轮故障

- **证据**: status.deepseek.com 官方状态页面 — API 33分钟部分中断 + 网页 30分钟完全中断
- 三天连续故障的最后一天

### 2026年4月1日 — 前端代码提交

- **证据**: 生产 JS 内嵌元数据 `commit_datetime:"2026/04/01 21:01:36"`
- commit-id: `1fcf6559`
- 前端包版本: `@deepseek/chat` v1.5.8
- API 版本: v1.7.1
- 此为宕机修复后的代码提交

### 2026年4月3日 — CDN 新部署

- **证据**: CDN HTTP `Last-Modified` 响应头、status.deepseek.com 官方状态页面
- 所有 CDN 静态文件统一更新至 `2026-04-03 08:20:13 GMT`（北京时间 16:20:13）
- 三个文件（main.js 1.1MB、main.css 221KB、vendors.js 679KB）的修改时间精确到秒一致
- status.deepseek.com 记录了 103 秒轻微中断

### 已删除的测试版本

- `main.6184d0a79e.js` 在 CDN 上返回 404（`x-amz-error-code: NoSuchKey`）
- 此版本包含**三模式切换 UI** 代码（快速模式/专家模式/多模态模式），当前生产版为两开关模式（DeepThink + Search）
- 上线时间未知，已被删除

### 宕机后新增的功能

通过对比当前 JS 代码（commit `1fcf6559`）识别到以下新增 feature flags：

| Flag | 默认值 | 说明 |
|------|--------|------|
| `sse_auto_resume_timeout` | 2000ms | SSE 流式响应断线自动重连（新功能） |
| `session_prefetch` | true | 会话预加载加速（新功能） |
| `pow_prefetch` | false | PoW 反滥用预取（新功能） |
| `chat_hcaptcha` | false | 海外人机验证码（新功能） |
| `allow_file_with_search` | false | 搜索时允许上传文件（新功能） |
| `launch_clean_session_interval_seconds` | 21600 | 6小时自动清理会话 |

### 故障统计

| 日期 | 中断时长 | 类型 | 严重度 |
|------|---------|------|--------|
| 3/5 | 40分钟 | 完全中断 | 一般 |
| 3/10 | 33分钟 | 部分中断 | 一般 |
| 3/18 | - | 性能异常 | 一般 |
| 3/29 | ~13小时 | 重大故障 | 严重 |
| 3/30 | 7.2小时 | 重大故障 | 严重 |
| 3/31 | ~1小时 | 部分+完全 | 一般 |
| 4/3 | 2分钟 | 轻微异常 | 轻微 |

3月网页端整体可用性: ~98.61%（来自 status.deepseek.com）

## 追踪原理

系统通过以下信号检测变化：

1. **commit-id** — HTML 中 `<meta name="commit-id">` 的值，每次部署都会变
2. **JS 文件 hash** — CDN 文件名中的 hash（如 `main.cd620c850b.js`），hash 变 = 内容变
3. **Feature Flags** — JS 代码中 `getFeature("xxx", default)` 调用，由 `/api/v0/client/settings` 远程控制
4. **CDN Last-Modified** — 华为云 CDN 的上传时间，所有文件同时更新 = 一次统一部署
5. **法律文档** — 更新通常是重大变更的前兆（3月27日更新 → 3月29日宕机的先例）
6. **GitHub 活动** — 监控 deepseek-ai 组织的仓库创建、代码推送、Release 发布
7. **Status Page** — 爬取 status.deepseek.com 获取官方服务状态和故障事件

## 项目结构

```
deepseek-monitor/
├── web/
│   ├── server.py           # Dashboard Web 服务器（端口 8765）
│   └── static/index.html   # Dashboard 前端页面
├── core/
│   ├── frontend_monitor.py  # 前端资源监控器（核心模块）
│   ├── github_monitor.py    # GitHub 监控器
│   ├── status_monitor.py    # Status Page 监控器
│   ├── config_monitor.py    # 配置监控器（需 Playwright）
│   ├── behavior_monitor.py  # 行为监控器（需 Playwright）
│   ├── storage.py           # SQLite 存储管理
│   ├── alerter.py           # 告警模块
│   └── reporter.py          # 报告生成
├── utils/
│   ├── config.py            # 配置加载
│   ├── diff_utils.py        # 差异比较工具
│   └── hash_utils.py        # Hash 工具
├── scripts/
│   ├── monitor.py           # 命令行入口
│   └── start_dashboard.sh   # Dashboard 启动脚本
├── config.yaml              # 配置文件
├── CHANGELOG.md             # 详细变更记录
├── ARCHITECTURE.md          # 系统架构设计
└── requirements.txt         # Python 依赖
```

## 依赖

- Python 3.8+
- aiohttp
- loguru
- pyyaml
- beautifulsoup4

完整检查（含浏览器行为测试）额外需要：
- playwright（`pip install playwright && playwright install chromium`）

## 许可证

MIT License

## 免责声明

本系统仅用于学习和研究目的。请遵守 DeepSeek 的使用条款，设置合理的检查间隔（建议 3 小时以上），避免频繁请求。
