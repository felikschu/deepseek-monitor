"""
模型配置监控模块

监控 DeepSeek 的模型配置变化：
1. 通过浏览器访问网页
2. 提取运行时的 Feature Flag 数据
3. 检测配置变化
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, List, Any
from pathlib import Path

from playwright.async_api import async_playwright, Browser
from loguru import logger

from utils.diff_utils import deep_diff


class ConfigMonitor:
    """模型配置监控器"""

    def __init__(self, config: Dict, storage):
        """初始化配置监控器

        Args:
            config: 配置字典
            storage: 存储管理器实例
        """
        self.config = config
        self.storage = storage
        self.targets = config.get("targets", {})
        self.browser_config = config.get("browser", {})

        self.browser = None
        self.context = None
        self.page = None

        self.results = {
            "timestamp": None,
            "changes": [],
            "config": {}
        }

    async def check(self) -> Dict[str, Any]:
        """执行配置检查

        Returns:
            检查结果字典
        """
        logger.info("开始模型配置检查...")
        self.results["timestamp"] = datetime.now().isoformat()

        try:
            # 启动浏览器
            await self._launch_browser()

            # 访问主页
            await self._navigate_to_main_page()

            # 提取模型配置
            model_config = await self._extract_model_config()
            self.results["config"] = model_config

            # 检测配置变化
            await self._check_config_changes(model_config)

            # 检测 API 端点
            await self._detect_api_endpoints()

        except Exception as e:
            logger.error(f"配置检查失败: {e}", exc_info=True)
            self.results["error"] = str(e)

        finally:
            await self._cleanup_browser()

        return self.results

    async def _launch_browser(self):
        """启动浏览器"""
        logger.info("启动浏览器...")

        playwright = await async_playwright().start()

        browser_type = self.browser_config.get("type", "chromium")
        browser_launcher = getattr(playwright, browser_type)

        self.browser = await browser_launcher.launch(
            headless=self.browser_config.get("headless", True),
            args=['--no-sandbox', '--disable-setuid-sandbox'] if browser_type == "chromium" else []
        )

        # 创建上下文
        self.context = await self.browser.new_context(
            user_agent=self.browser_config.get("user_agent"),
            viewport={"width": 1920, "height": 1080}
        )

        # 创建页面
        self.page = await self.context.new_page()

        # 设置超时
        self.page.set_default_timeout(self.browser_config.get("page_timeout", 30000))

        logger.info(f"浏览器已启动: {browser_type}")

    async def _navigate_to_main_page(self):
        """导航到主页"""
        base_url = self.targets.get("base_url")
        logger.info(f"访问主页: {base_url}")

        await self.page.goto(base_url, wait_until="networkidle")

        # 等待页面加载
        await asyncio.sleep(2)

        logger.info("页面加载完成")

    async def _extract_model_config(self) -> Dict:
        """提取模型配置

        通过执行 JavaScript 获取运行时的配置数据
        """
        logger.info("提取模型配置...")

        # 尝试从 window 对象中提取配置
        extract_js = """
        () => {
            const config = {};

            // 尝试获取 model_configs
            if (typeof window !== 'undefined') {
                // 方法1: 从全局变量获取
                if (window.__NEXT_DATA__?.props?.pageProps) {
                    config.next_data = window.__NEXT_DATA__.props.pageProps;
                }

                // 方法2: 尝试获取 Feature Flag
                if (window.__FEATURE_FLAGS__) {
                    config.feature_flags = window.__FEATURE_FLAGS__;
                }

                // 方法3: 尝试从 localStorage 获取
                try {
                    const modelConfigs = localStorage.getItem('model_configs');
                    if (modelConfigs) {
                        config.localStorage_model_configs = JSON.parse(modelConfigs);
                    }
                } catch (e) {}

                // 方法4: 扫描所有可能包含配置的变量
                for (let key in window) {
                    if (key.toLowerCase().includes('config') ||
                        key.toLowerCase().includes('model') ||
                        key.toLowerCase().includes('feature')) {

                        try {
                            const value = window[key];
                            if (value && typeof value === 'object') {
                                config[key] = value;
                            }
                        } catch (e) {}
                    }
                }
            }

            return config;
        }
        """

        try:
            config = await self.page.evaluate(extract_js)
            logger.info(f"提取到配置: {list(config.keys())}")

            # 尝试通过网络请求获取配置
            api_config = await self._fetch_config_via_api()
            if api_config:
                config["api_config"] = api_config

            return config

        except Exception as e:
            logger.error(f"提取配置失败: {e}", exc_info=True)
            return {}

    async def _fetch_config_via_api(self) -> Dict:
        """通过 API 获取配置

        监听网络请求，尝试获取配置相关的 API 响应
        """
        logger.info("监听网络请求获取配置...")

        api_responses = {}

        def log_response(response):
            """记录 API 响应"""
            request = response.request
            url = response.url

            # 只记录配置相关的请求
            if any(keyword in url.lower() for keyword in ["config", "model", "feature", "flag"]):
                try:
                    # 尝试获取响应体
                    # 注意：这需要 API 返回 JSON
                    # 由于 Playwright 限制，这里只能记录 URL 和状态
                    api_responses[url] = {
                        "status": response.status,
                        "headers": dict(response.headers)
                    }
                    logger.debug(f"捕获到配置请求: {url}")
                except Exception as e:
                    logger.debug(f"无法获取响应内容: {e}")

        # 添加响应监听器
        self.page.on("response", log_response)

        # 刷新页面触发网络请求
        await self.page.reload(wait_until="networkidle")

        # 等待一段时间让请求完成
        await asyncio.sleep(3)

        # 移除监听器
        self.page.remove_listener("response", log_response)

        if api_responses:
            logger.info(f"捕获到 {len(api_responses)} 个配置相关的网络请求")

        return api_responses

    async def _check_config_changes(self, current_config: Dict):
        """检查配置变化

        Args:
            current_config: 当前配置
        """
        logger.info("检查配置变化...")

        # 获取历史配置
        last_config = await self.storage.get_last_model_config()

        if last_config:
            # 计算差异
            diff = deep_diff(last_config["config"], current_config)

            if diff:
                change = {
                    "type": "config_change",
                    "diff": diff,
                    "detected_at": datetime.now().isoformat()
                }
                self.results["changes"].append(change)
                logger.warning(f"检测到配置变化: {len(diff)} 处差异")

                # 记录主要变化
                for d in diff[:10]:  # 只显示前10个
                    logger.info(f"  [{d['path']}] {d['type']}")
            else:
                logger.info("配置未变化")
        else:
            logger.info("首次保存配置")

        # 保存当前配置
        await self.storage.save_model_config(current_config)

    async def _detect_api_endpoints(self):
        """检测 API 端点变化"""
        logger.info("检测 API 端点...")

        # 监听网络请求，收集所有 API 端点
        api_endpoints = set()

        def collect_api_endpoints(request):
            """收集 API 端点"""
            url = request.url
            if "/api/" in url:
                # 提取端点路径
                from urllib.parse import urlparse
                parsed = urlparse(url)
                endpoint = parsed.path
                api_endpoints.add(endpoint)

        # 添加请求监听器
        self.page.on("request", collect_api_endpoints)

        # 执行一些操作来触发 API 请求
        # 例如：点击一些按钮，触发功能
        try:
            # 刷新页面
            await self.page.reload(wait_until="networkidle")
            await asyncio.sleep(2)

            # 尝试触发一些交互
            # 这里可以根据实际情况添加更多交互
        except Exception as e:
            logger.debug(f"触发 API 请求时出错: {e}")

        # 移除监听器
        self.page.remove_listener("request", collect_api_endpoints)

        if api_endpoints:
            logger.info(f"发现 {len(api_endpoints)} 个 API 端点")
            self.results["api_endpoints"] = list(api_endpoints)

            # 检查端点变化
            last_endpoints = await self.storage.get_last_api_endpoints()

            if last_endpoints:
                last_set = set(last_endpoints["endpoints"])
                new_endpoints = api_endpoints - last_set
                removed_endpoints = last_set - api_endpoints

                if new_endpoints or removed_endpoints:
                    change = {
                        "type": "api_endpoints_change",
                        "new_endpoints": list(new_endpoints),
                        "removed_endpoints": list(removed_endpoints),
                        "detected_at": datetime.now().isoformat()
                    }
                    self.results["changes"].append(change)

                    if new_endpoints:
                        logger.info(f"新增 API 端点: {new_endpoints}")
                    if removed_endpoints:
                        logger.info(f"移除 API 端点: {removed_endpoints}")

            # 保存当前端点
            await self.storage.save_api_endpoints(list(api_endpoints))

    async def _cleanup_browser(self):
        """清理浏览器资源"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        logger.debug("浏览器资源已清理")

    async def cleanup(self):
        """清理资源（已被 _cleanup_browser 替代）"""
        pass
