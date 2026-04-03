# DeepSeek Monitor

追踪 DeepSeek 网页端变化的监控系统。自动检测前端部署、Feature Flags 变化、API 端点增减和法律文档更新。

## 功能

- **前端部署追踪** — 检测 commit-id、JS/CSS 文件 hash 变化
- **Feature Flags 监控** — 提取 8+ 个远程功能开关，对比历史变化
- **API 端点追踪** — 监控 36+ 个 `/api/v0/*` 端点的增减
- **CDN 资源追踪** — 监控 JS/CSS 上传时间和 ETag
- **法律文档检测** — Terms of Use / Privacy Policy 更新预警
- **Web Dashboard** — 暗色主题可视化面板，支持一键检查和报告导出

## 快速开始

### 1. 安装依赖

```bash
pip install aiohttp loguru pyyaml beautifulsoup4
```

### 2. 启动 Dashboard

**macOS**: 双击桌面的 `DeepSeek Monitor.command`

**或手动运行**:

```bash
cd deepseek_monitor

# 启动 Dashboard（推荐）
python3 web/server.py

# 或命令行检查
python3 scripts/monitor.py --mode frontend
```

打开 http://localhost:8765 查看 Dashboard。

### 3. 设置定时检查

```bash
# crontab -e
# 每3小时自动检查一次
0 */3 * * * cd /path/to/deepseek_monitor && python3 scripts/monitor.py --mode frontend >> logs/cron.log 2>&1
```

## Dashboard 说明

Dashboard 包含 6 个模块，每个模块右上角有 `?` 按钮可以查看详细说明：

| 模块 | 说明 |
|------|------|
| 事件时间线 | 按天显示变化数量的折线图 |
| Feature Flags | 远程功能开关列表及变化状态 |
| CDN 资源 | JS/CSS 文件的上传时间和大小 |
| 变更记录 | 所有检测到的变化，可按类型过滤 |
| API 端点 | 前端调用的所有后端接口 |
| 法律文档 | 使用条款和隐私政策的更新记录 |

所有时间均显示为北京时间（UTC+8）。

## 追踪原理

系统通过以下信号检测 DeepSeek 网页端变化：

1. **commit-id** — HTML 中 `<meta name="commit-id">` 的值，每次部署都会变
2. **JS 文件 hash** — CDN 文件名中的 hash（如 `main.cd620c850b.js`），hash 变 = 内容变
3. **Feature Flags** — JS 代码中 `getFeature("xxx", default)` 调用，由服务端远程控制
4. **CDN Last-Modified** — 文件上传时间，所有文件同时更新 = 一次统一部署
5. **法律文档** — 更新通常是重大变更的前兆

## 项目结构

```
deepseek_monitor/
├── web/
│   ├── server.py          # Dashboard Web 服务器
│   └── static/index.html  # Dashboard 前端页面
├── core/
│   ├── frontend_monitor.py # 前端资源监控器
│   ├── config_monitor.py   # 配置监控器（需 Playwright）
│   ├── behavior_monitor.py # 行为监控器（需 Playwright）
│   ├── storage.py          # SQLite 存储管理
│   ├── alerter.py          # 告警模块
│   └── reporter.py         # 报告生成
├── utils/
│   ├── config.py           # 配置加载
│   ├── diff_utils.py       # 差异比较工具
│   └── hash_utils.py       # Hash 工具
├── scripts/
│   ├── monitor.py          # 命令行入口
│   └── start_dashboard.sh  # Dashboard 启动脚本
├── config.yaml             # 配置文件
├── CHANGELOG.md            # 变更记录（已发现的 DeepSeek 变化）
└── requirements.txt        # Python 依赖
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
