"""
行为特征监控模块

监控 DeepSeek 的行为特征变化：
1. 执行标准测试用例
2. 分析响应特征
3. 检测行为变化
"""

import asyncio
import re
from datetime import datetime
from typing import Dict, List, Any
from statistics import mean, median

from playwright.async_api import async_playwright
from loguru import logger

from utils.diff_utils import analyze_response_changes


class BehaviorMonitor:
    """行为特征监控器"""

    def __init__(self, config: Dict, storage):
        """初始化行为监控器

        Args:
            config: 配置字典
            storage: 存储管理器实例
        """
        self.config = config
        self.storage = storage
        self.targets = config.get("targets", {})
        self.behavior_config = config.get("behavior", {})
        self.browser_config = config.get("browser", {})

        self.browser = None
        self.context = None
        self.page = None

        self.results = {
            "timestamp": None,
            "changes": [],
            "test_results": []
        }
        self.input_selector = None

    async def check(self) -> Dict[str, Any]:
        """执行行为检查

        Returns:
            检查结果字典
        """
        logger.info("开始行为特征检查...")
        self.results["timestamp"] = datetime.now().isoformat()

        try:
            # 启动浏览器
            await self._launch_browser()

            # 访问主页
            await self._navigate_to_main_page()

            if await self._detect_auth_gate():
                note = "当前网页未登录态直接进入登录页，行为测试需要有效登录态。"
                logger.warning(note)
                self.results["auth_required"] = True
                self.results["note"] = note
                return self.results

            # 执行测试用例
            test_cases = self.behavior_config.get("test_cases", [])
            logger.info(f"执行 {len(test_cases)} 个测试用例...")

            for i, test_case in enumerate(test_cases, 1):
                logger.info(f"[{i}/{len(test_cases)}] 执行测试: {test_case['prompt'][:30]}...")

                try:
                    result = await self._execute_test_case(test_case)
                    self.results["test_results"].append(result)

                    # 保存测试结果
                    await self.storage.save_test_result(test_case, result)

                except Exception as e:
                    logger.error(f"测试用例执行失败: {e}")
                    self.results["test_results"].append({
                        "prompt": test_case["prompt"],
                        "error": str(e)
                    })

                # 测试之间的间隔
                if i < len(test_cases):
                    await asyncio.sleep(2)

            # 分析行为变化
            await self._analyze_behavior_changes()

        except Exception as e:
            logger.error(f"行为检查失败: {e}", exc_info=True)
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
            headless=self.browser_config.get("headless", True)
        )

        self.context = await self.browser.new_context(
            user_agent=self.browser_config.get("user_agent")
        )

        self.page = await self.context.new_page()
        self.page.set_default_timeout(self.browser_config.get("page_timeout", 30000))

        logger.info("浏览器已启动")

    async def _navigate_to_main_page(self):
        """导航到主页"""
        base_url = self.targets.get("base_url")
        logger.info(f"访问主页: {base_url}")

        await self.page.goto(base_url, wait_until="networkidle")
        await asyncio.sleep(2)

        logger.info("页面加载完成")

    async def _detect_auth_gate(self) -> bool:
        """检测当前页面是否处于登录门槛。"""
        body_text = await self.page.locator("body").inner_text()
        markers = [
            "Send code",
            "Log in",
            "Scan with Wechat to login",
        ]
        return all(marker in body_text for marker in markers)

    async def _execute_test_case(self, test_case: Dict) -> Dict:
        """执行单个测试用例

        Args:
            test_case: 测试用例配置

        Returns:
            测试结果字典
        """
        prompt = test_case["prompt"]

        # 查找输入框
        await self._wait_for_input_ready()

        # 记录开始时间
        start_time = datetime.now()

        # 输入问题
        await self._type_prompt(prompt)

        # 发送（模拟 Enter 键或点击发送按钮）
        await self._send_message()

        # 等待响应
        await self._wait_for_response()

        # 记录结束时间
        end_time = datetime.now()

        # 提取响应内容
        response_text = await self._extract_response()

        # 分析响应特征
        metrics = self._analyze_response(response_text, start_time, end_time)

        return {
            "prompt": prompt,
            "category": test_case.get("category", "未分类"),
            "response": response_text,
            "metrics": metrics,
            "timestamp": datetime.now().isoformat()
        }

    async def _wait_for_input_ready(self):
        """等待输入框就绪"""
        try:
            selectors = [
                "textarea:visible",
                "[contenteditable='true']:visible",
                "[role='textbox']:visible",
                ".chat-input:visible",
            ]
            for selector in selectors:
                locator = self.page.locator(selector).first
                if await locator.count():
                    try:
                        await locator.wait_for(state="visible", timeout=3000)
                        self.input_selector = selector
                        await asyncio.sleep(1)
                        return
                    except Exception:
                        continue

            locator = self.page.locator(
                "textarea, [contenteditable='true'], [role='textbox'], .chat-input"
            ).first
            await locator.wait_for(state="visible", timeout=10000)
            self.input_selector = "textarea, [contenteditable='true'], [role='textbox'], .chat-input"
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"等待输入框失败: {e}")
            raise

    async def _type_prompt(self, prompt: str):
        """向当前输入控件输入 prompt。"""
        selector = self.input_selector or "textarea, [contenteditable='true'], [role='textbox'], .chat-input"
        locator = self.page.locator(selector).first
        await locator.click()

        tag_name = await locator.evaluate("el => (el.tagName || '').toLowerCase()")
        is_contenteditable = await locator.evaluate(
            "el => el.getAttribute('contenteditable') === 'true'"
        )

        if tag_name in ("textarea", "input"):
            await locator.fill(prompt)
            return

        if is_contenteditable:
            await self.page.keyboard.type(prompt, delay=50)
            return

        await self.page.type(selector, prompt, delay=50)

    async def _send_message(self):
        """发送消息"""
        try:
            # 尝试方法1: 按 Enter 键
            await self.page.keyboard.press("Enter")
        except Exception as e:
            logger.debug(f"按 Enter 键失败: {e}")

            # 尝试方法2: 点击发送按钮
            try:
                send_button = self.page.locator("button:has-text('发送'), button:has-text('Send'), .send-button")
                await send_button.click()
            except Exception as e2:
                logger.error(f"点击发送按钮失败: {e2}")
                raise

    async def _wait_for_response(self):
        """等待响应完成"""
        try:
            # 等待响应出现（通常会有加载指示器）
            # 这里需要根据实际的 UI 结构调整

            # 方法1: 等待加载动画消失
            try:
                await self.page.wait_for_selector(".loading, .spinner, [class*='loading']", state="detached", timeout=30000)
            except:
                pass

            # 方法2: 等待响应内容出现
            await self.page.wait_for_selector(".message-content, .chat-response, [class*='message']", timeout=30000)

            # 额外等待确保响应完全加载
            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"等待响应失败: {e}")
            raise

    async def _extract_response(self) -> str:
        """提取响应文本

        Returns:
            响应文本内容
        """
        try:
            # 尝试找到最后的消息气泡
            # 这里的选择器需要根据实际页面结构调整

            # 方法1: 通过类名查找
            messages = await self.page.query_selector_all(".message-content, .chat-response, [class*='message']")

            if messages:
                # 获取最后一个消息
                last_message = messages[-1]
                text = await last_message.inner_text()
                return text.strip()

            # 方法2: 通过文本选择器
            text = await self.page.inner_text("body")
            # 这里可以添加更复杂的解析逻辑

            return "无法提取响应"

        except Exception as e:
            logger.error(f"提取响应失败: {e}")
            return "提取失败"

    def _analyze_response(self, response: str, start_time: datetime, end_time: datetime) -> Dict:
        """分析响应特征

        Args:
            response: 响应文本
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            指标字典
        """
        # 计算响应时间
        response_time = (end_time - start_time).total_seconds()

        # 检测代码块
        has_code = bool(re.search(r'```[\s\S]*?```', response))

        # 检测搜索结果
        has_search = bool(re.search(r'搜索|search|参考|来源', response, re.I))

        # 提取模型签名（如果有）
        model_signature = self._extract_model_signature(response)

        return {
            "response_time": response_time,
            "response_length": len(response),
            "has_code_blocks": has_code,
            "has_search_results": has_search,
            "model_signature": model_signature
        }

    def _extract_model_signature(self, response: str) -> str:
        """提取模型签名

        Args:
            response: 响应文本

        Returns:
            模型签名或空字符串
        """
        # 尝试从响应中提取模型信息
        # 这需要根据实际响应格式调整

        # 查找常见的模型签名模式
        patterns = [
            r'Model:\s*([^\n]+)',
            r'模型[:：]\s*([^\n]+)',
            r'Powered by\s+([^\n]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, response, re.I)
            if match:
                return match.group(1).strip()

        return ""

    async def _analyze_behavior_changes(self):
        """分析行为变化"""
        logger.info("分析行为变化...")

        # 获取历史测试结果
        historical_results = await self.storage.get_historical_test_results(days=7)

        if not historical_results:
            logger.info("没有历史数据用于比较")
            return

        # 对每个测试用例进行分析
        current_results = {r["prompt"]: r for r in self.results["test_results"]}

        for prompt, current in current_results.items():
            if "error" in current:
                continue

            # 找到相同提示的历史结果
            history = [r for r in historical_results if r.get("prompt") == prompt]

            if not history:
                continue

            # 计算基准指标
            baseline_metrics = self._calculate_baseline_metrics(history)
            current_metrics = current.get("metrics", {})

            # 检测异常
            anomalies = self._detect_anomalies(baseline_metrics, current_metrics)

            if anomalies:
                change = {
                    "type": "behavior_change",
                    "prompt": prompt,
                    "category": current.get("category"),
                    "anomalies": anomalies,
                    "baseline": baseline_metrics,
                    "current": current_metrics,
                    "detected_at": datetime.now().isoformat()
                }
                self.results["changes"].append(change)

                logger.warning(f"检测到行为变化: {prompt[:30]}...")
                for anomaly in anomalies:
                    logger.info(f"  [{anomaly['metric']}] {anomaly['description']}")

    def _calculate_baseline_metrics(self, history: List[Dict]) -> Dict:
        """计算基准指标

        Args:
            history: 历史测试结果列表

        Returns:
            基准指标字典
        """
        metrics_list = [h.get("metrics", {}) for h in history if "metrics" in h]

        if not metrics_list:
            return {}

        baseline = {}

        # 响应时间
        response_times = [m.get("response_time", 0) for m in metrics_list if m.get("response_time")]
        if response_times:
            baseline["response_time"] = {
                "mean": mean(response_times),
                "median": median(response_times),
                "min": min(response_times),
                "max": max(response_times)
            }

        # 响应长度
        response_lengths = [m.get("response_length", 0) for m in metrics_list if m.get("response_length")]
        if response_lengths:
            baseline["response_length"] = {
                "mean": mean(response_lengths),
                "median": median(response_lengths)
            }

        # 代码块出现频率
        has_code_count = sum(1 for m in metrics_list if m.get("has_code_blocks"))
        baseline["has_code_blocks_rate"] = has_code_count / len(metrics_list)

        # 搜索结果频率
        has_search_count = sum(1 for m in metrics_list if m.get("has_search_results"))
        baseline["has_search_results_rate"] = has_search_count / len(metrics_list)

        return baseline

    def _detect_anomalies(self, baseline: Dict, current: Dict) -> List[Dict]:
        """检测异常

        Args:
            baseline: 基准指标
            current: 当前指标

        Returns:
            异常列表
        """
        anomalies = []

        if not baseline or not current:
            return anomalies

        # 响应时间异常（超过基准的2倍）
        if "response_time" in baseline and "response_time" in current:
            rt_mean = baseline["response_time"]["mean"]
            rt_current = current["response_time"]

            if rt_current > rt_mean * 2:
                anomalies.append({
                    "metric": "response_time",
                    "description": f"响应时间异常: {rt_current:.2f}s (基准: {rt_mean:.2f}s)",
                    "baseline": rt_mean,
                    "current": rt_current
                })

        # 响应长度异常（变化超过50%）
        if "response_length" in baseline and "response_length" in current:
            length_mean = baseline["response_length"]["mean"]
            length_current = current["response_length"]

            if length_mean > 0:
                change_ratio = abs(length_current - length_mean) / length_mean
                if change_ratio > 0.5:
                    anomalies.append({
                        "metric": "response_length",
                        "description": f"响应长度变化: {length_current} (基准: {length_mean:.0f})",
                        "baseline": length_mean,
                        "current": length_current
                    })

        # 代码块特征变化
        if "has_code_blocks" in baseline and "has_code_blocks" in current:
            # 这里简化处理，实际应该比较频率变化
            pass

        return anomalies

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
