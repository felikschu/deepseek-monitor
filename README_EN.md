# DeepSeek Monitor

> **🚨 Why This Exists**: DeepSeek V4 is taking forever to release, and let's be honest—we're all getting a bit impatient (myself included)! This system was born out of pure "update anxiety"—if we can't have the new model yet, we might as well stalk DeepSeek's every move and see what they're secretly cooking up! 🔍

A monitoring system that tracks changes across the entire DeepSeek platform. Automatically detects web frontend deployments, Feature Flags changes, API endpoint additions/removals, legal document updates, GitHub open source activities, and official status page incidents.

> **中文**: 追踪 DeepSeek 全平台变化的监控系统。自动检测网页端部署、Feature Flags 变化、API 端点增减、法律文档更新、GitHub 开源动态和官方状态页面事件。
>
> 📄 [中文 README](README.md)

## Features

- **Frontend Deployment Tracking** — Detects commit-id and JS/CSS file hash changes
- **Feature Flags Monitoring** — Extracts 8+ remote feature switches and compares historical changes
- **API Endpoint Tracking** — Monitors 36+ `/api/v0/*` endpoints with click-to-view descriptions
- **CDN Resource Tracking** — Monitors JS/CSS upload times and ETags
- **Legal Document Detection** — Alerts on Terms of Use / Privacy Policy updates
- **GitHub Monitoring** — Tracks new repositories, code pushes, and Release publications from deepseek-ai organization
- **Status Page Monitoring** — Monitors service status and incidents from status.deepseek.com
- **Web Dashboard** — Dark-themed visualization panel with one-click checks and report export

## Quick Start

### 1. Download and Install

```bash
git clone https://github.com/felikschu/deepseek-monitor.git
cd deepseek-monitor

# One-click install (installs dependencies + creates desktop shortcut)
bash scripts/setup.sh
```

### 2. Launch

**macOS**: Double-click `DeepSeek Monitor.command` on your desktop (auto-created by install script)

**Manual Launch**:

```bash
cd deepseek-monitor
python3 web/server.py
```

Open http://localhost:8765 to view the Dashboard.

### 3. Schedule Automatic Checks

```bash
crontab -e
# Check every 3 hours (includes frontend, GitHub, and Status Page)
0 */3 * * * cd /path/to/deepseek-monitor && python3 web/server.py --no-open >> logs/cron.log 2>&1 &
```

## Real Events Discovered

The following DeepSeek changes were tracked by this system, all based on technical evidence (HTTP response headers, JS code analysis, and official status.deepseek.com data):

### March 27, 2026 — Legal Document Update

- **Evidence**: CDN HTTP `Last-Modified` response header
- Terms of Use and Privacy Policy simultaneously updated to `2026-03-27 03:50:07 GMT` (Beijing time 11:50:07)
- Both documents modified at the exact same second, indicating a unified operation
- **Significance**: Legal document updates often precede major product changes

### March 29, 2026 — Silent Model Upgrade + 13-Hour Outage

- **Evidence**: status.deepseek.com official status page, user reports (Juejin, Zhihu, Sohu, Sina, etc.)
- Web/App services abnormal from 21:35 on the 29th to 10:33 on the 30th (nearly 13 hours)
- Incident ID: `v5mmslnf9249`
- **User-observed changes** (before outage):
  - Model self-identification changed from "pure text AI assistant" to explicit "DeepSeek-V3 Model"
  - Knowledge cutoff updated from early 2025 to January 2026 (could answer questions about 2025 US election results)
  - SVG generation and code generation capabilities significantly improved
- **Post-outage rollback**: After fix, knowledge cutoff reverted to May 2025, self-introduction no longer mentioned version number
- This suggests a new model was deployed via gray release but had issues and was rolled back

### March 30, 2026 — Second Outage (7+ Hours)

- **Evidence**: status.deepseek.com official status page — approximately 433 minutes of complete outage
- Incident ID: `rjs0ljjlqhsw`
- Collapsed again shortly after March 29 fix
- Longest single-day outage in DeepSeek web history

### March 31, 2026 — Third Incident

- **Evidence**: status.deepseek.com official status page — API 33-minute partial outage + Web 30-minute complete outage
- Last day of three consecutive days of failures

### April 1, 2026 — Frontend Code Commit

- **Evidence**: Production JS embedded metadata `commit_datetime:"2026/04/01 21:01:36"`
- commit-id: `1fcf6559`
- Frontend package version: `@deepseek/chat` v1.5.8
- API version: v1.7.1
- This was the post-outage fix commit

### April 3, 2026 — CDN New Deployment

- **Evidence**: CDN HTTP `Last-Modified` response header, status.deepseek.com official status page
- All CDN static files uniformly updated to `2026-04-03 08:20:13 GMT` (Beijing time 16:20:13)
- Three files (main.js 1.1MB, main.css 221KB, vendors.js 679KB) modified at exact same second
- status.deepseek.com recorded 103 seconds of minor interruption

### Deleted Test Version

- `main.6184d0a79e.js` returns 404 on CDN (`x-amz-error-code: NoSuchKey`)
- This version contained **three-mode switching UI** code (Fast Mode / Expert Mode / Vision Mode), current production uses two-switch mode (DeepThink + Search)
- Launch time unknown, has been deleted

### New Features After Outage

By comparing current JS code (commit `1fcf6559`), the following new feature flags were identified:

| Flag | Default | Description |
|------|---------|-------------|
| `sse_auto_resume_timeout` | 2000ms | SSE streaming response auto-resume timeout (NEW) |
| `session_prefetch` | true | Session prefetch acceleration (NEW) |
| `pow_prefetch` | false | PoW anti-abuse prefetch (NEW) |
| `chat_hcaptcha` | false | Overseas hCaptcha verification (NEW) |
| `allow_file_with_search` | false | Allow file upload during search (NEW) |
| `launch_clean_session_interval_seconds` | 21600 | Auto-clean sessions every 6 hours |

### Outage Statistics

| Date | Duration | Type | Severity |
|------|----------|------|----------|
| 3/5 | 40 min | Complete outage | Moderate |
| 3/10 | 33 min | Partial outage | Moderate |
| 3/18 | - | Performance degraded | Moderate |
| 3/29 | ~13 hours | Major incident | Critical |
| 3/30 | 7.2 hours | Major incident | Critical |
| 3/31 | ~1 hour | Partial + Complete | Moderate |
| 4/3 | 2 min | Minor anomaly | Low |

March web availability: ~98.61% (from status.deepseek.com)

## Tracking Principles

The system detects changes through the following signals:

1. **commit-id** — Value in HTML `<meta name="commit-id">`, changes with every deployment
2. **JS file hash** — Hash in CDN filenames (e.g., `main.cd620c850b.js`), hash change = content change
3. **Feature Flags** — `getFeature("xxx", default)` calls in JS code, remotely controlled by `/api/v0/client/settings`
4. **CDN Last-Modified** — Huawei Cloud CDN upload time, all files updated simultaneously = unified deployment
5. **Legal Documents** — Updates usually precede major changes (March 27 update → March 29 outage precedent)
6. **GitHub Activity** — Monitors deepseek-ai organization for repository creation, code pushes, and Release publications
7. **Status Page** — Crawls status.deepseek.com for official service status and incident events

## Project Structure

```
deepseek-monitor/
├── web/
│   ├── server.py           # Dashboard web server (port 8765)
│   └── static/index.html   # Dashboard frontend
├── core/
│   ├── frontend_monitor.py  # Frontend resource monitor (core module)
│   ├── github_monitor.py    # GitHub monitor
│   ├── status_monitor.py    # Status Page monitor
│   ├── config_monitor.py    # Config monitor (requires Playwright)
│   ├── behavior_monitor.py  # Behavior monitor (requires Playwright)
│   ├── storage.py           # SQLite storage management
│   ├── alerter.py           # Alert module
│   └── reporter.py          # Report generation
├── utils/
│   ├── config.py            # Config loading
│   ├── diff_utils.py        # Diff comparison tools
│   └── hash_utils.py        # Hash utilities
├── scripts/
│   ├── monitor.py           # CLI entry point
│   └── start_dashboard.sh   # Dashboard startup script
├── config.yaml              # Configuration file
├── CHANGELOG.md             # Detailed change log
├── ARCHITECTURE.md          # System architecture design
└── requirements.txt         # Python dependencies
```

## Dependencies

- Python 3.8+
- aiohttp
- loguru
- pyyaml
- beautifulsoup4

For full checks (including browser behavior testing), additionally requires:
- playwright (`pip install playwright && playwright install chromium`)

## License

MIT License

## Disclaimer

This system is for educational and research purposes only. Please comply with DeepSeek's Terms of Use, set reasonable check intervals (recommended 3+ hours), and avoid frequent requests.
