# DeepSeek 网页侦察方法论

这套 monitor 不应该只盯一个 `main.js`。

真正可靠的网页侦察应该同时覆盖 3 个层次：

1. 传输层信号
2. 结构层信号
3. 源码层信号
4. 语义层信号

## 1. 传输层信号

先看 HTTP 自己提供了什么：

- `final_url`：是否发生跳转
- `status_code`：页面是否下线、改鉴权、改路由
- `Last-Modified`：上游声称的更新时间
- `ETag`：内容签名
- `Content-Type`：HTML / XML / JSON / 文本
- `Cache-Control`：缓存策略是否变化

这些信号的意义：

- `Last-Modified` 更接近“官方更新时间”
- `observed_at` 是“本地发现时间”
- 这两者必须分开显示，不能混用

## 2. 结构层信号

抓页面源码后，不要只抽一个字段。至少提取：

- `title`
- 关键 `meta`
- 脚本资源列表
- 样式资源列表
- 站内链接图谱
- 多语言入口
- `sitemap.xml`

这些信号的意义：

- 资源列表变化：通常意味着重新部署
- 站内链接变化：通常意味着新增/下线页面或入口调整
- `sitemap` 变化：能发现 monitor 原来根本没监控到的新页面
- 从首页 / 新闻页 / 研究页抽到的“可疑链接”本身就是监控对象，尤其是：
  - `pricing`
  - `token-plan`
  - `promotion`
  - `coding`
  - `mcp`
  - `agent`
  - `research/<id>`

## 3. 源码层信号

很多最关键的情报根本不在可见页面里，而是在：

- 同站点 JS bundle
- Next.js / React Flight 内嵌数据块
- 平台页的前端配置 JSON
- 菜单/运营位文案
- 前端静态资源版本号

重点要抓：

- 新模型型号
- 价格表 / 定价明细
- 套餐文案 / 限时免费 / Token 赠送活动
- `agentId` / `CODER` / `CHAT` 这种路由和产品形态信号
- 平台前端版本号，例如 `prod-en-minimax-0.1.39`

经验规则：

- `HTML` 里没有，不代表没有
- 同站点 `app.*.js` / `page-*.js` 往往比首页正文更重要
- 开放平台页通常是“信息密度最高”的地方

## 4. 语义层信号

只知道“页面变了”没有价值。需要进一步比较：

- 可见正文是否变化
- 新增/删除了哪些段落
- 新增的链接是否指向 `news` / `pricing` / `download` / `status`
- 文档页是否新增了新的 release note

输出时必须给出：

- `summary`
- `evidence`
- `impact_guess`
- `source_time`
- `observed_at`

对于 DeepSeek，这一层还应该专门抽：

- `route_patterns`：判断 `coder / agent / session` 是否已经进入真实路由
- `api_families`：判断前端已经暴露了哪些能力家族
- `hidden_capabilities`：把源码线索归纳成接近产品语言的结论
- `coder_signals / vision_signals / agent_signals`：保留原始证据，便于人工复核

## 5. DeepSeek 站点的实际应用

围绕 DeepSeek，优先级最高的页面不是只有 `chat.deepseek.com`。

应该至少监控：

- `https://www.deepseek.com/`
- `https://www.deepseek.com/en/`
- `https://api-docs.deepseek.com/`
- `https://api-docs.deepseek.com/quick_start/pricing`
- `https://api-docs.deepseek.com/quick_start/rate_limit`
- `https://api-docs.deepseek.com/sitemap.xml`
- 法律文档两页
- `https://status.deepseek.com/`
- `https://github.com/deepseek-ai`
- `chat.deepseek.com` 的主 bundle
- `www.deepseek.com` / `api-docs.deepseek.com` 的同站点脚本资源

同样的方法要复制到竞品：

- 智谱官网
- 智谱开放平台 `open.bigmodel.cn`
- MiniMax 官网
- MiniMax 新闻页及其内嵌 Next 数据块

## 6. 监控输出规则

每条变化要回答 5 个问题：

1. 什么变了
2. 证据是什么
3. 这个时间是官方时间还是本地发现时间
4. 可能影响什么
5. 置信度有多高

如果系统答不出第 2 条和第 3 条，这条变化就还不够可用。

## 7. 竞品网页的实战规则

针对智谱和 MiniMax，这里有一套更实用的抓法：

1. 先抓首页
2. 抽同源 JS bundle
3. 抽页面里所有 `href`
4. 只保留“可疑链接”
5. 再针对这些链接补抓二跳页面

其中“可疑链接”关键词优先级最高的是：

- `pricing`
- `token-plan`
- `promotion`
- `referral`
- `coding`
- `plan`
- `package`
- `research`
- `news`
- `model`
- `mcp`
- `agent`

这套方法的意义：

- 智谱的新模型页经常会先以 `research/<id>` 的形式挂出来
- MiniMax 的商业化动作往往先出现在 `docs/pricing` / `token-plan` / `promotion` 这些路径
- 首页正文不一定说全，但导航、JSON、React Flight 和链接图谱通常已经暴露了入口

## 8. 项目内的通用落地

为了避免每次临时手写扒站代码，项目里现在有一个通用脚本：

```bash
python3 scripts/recon_surfaces.py --profile official
python3 scripts/recon_surfaces.py --profile competitor --vendor minimax
python3 scripts/recon_surfaces.py --url https://www.deepseek.com/en/ --extractor deepseek
python3 scripts/recon_surfaces.py --url https://open.bigmodel.cn/ --extractor zhipu --expand-discovered 4
```

它的设计目标是：

- 保持灵活：支持任意 `URL`、任意 extractor、任意脚本探针深度
- 保持一般性：默认从 host 推断站点类型，不必每次写特判
- 保持可复用：同一套方法同时服务 DeepSeek 官方页、竞品页、临时 ad hoc 侦察
- 保持可扩展：以后新增厂商时，只要补一个 extractor 和站点规则映射即可

现在项目里还多了一层源码语义抽取，重点覆盖 DeepSeek 的：

- `coder`：是否进入 Agent 路由、是否存在 OAuth 回跳
- `vision`：是否通过 `enabled / switchable / file_feature.vision` 接入模型选择
- `agent`：是否存在 `/a/:agentId` 与 `/a/:agentId/s/:sessionId` 这类会话结构
- `api`：`/api/v0/*` 暴露出的能力家族
- `pricing`：公开文案是否强调 API / agent / coding 等商业化方向
