"""
前端资源监控模块

监控 DeepSeek 网页端的前端资源变化：
1. JS/CSS 文件 hash 变化
2. commit-id 和 commit-datetime 变化
3. Feature Flags 快照和变化
4. API 端点列表变化
5. CDN 资源 Last-Modified 追踪
6. 法律文档更新检测
"""

import asyncio
import json
import re
import hashlib
from difflib import SequenceMatcher
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup
from loguru import logger

from utils.hash_utils import calculate_file_hash
from utils.diff_utils import extract_code_patterns, compare_patterns
from utils.bundle_inspector import (
    analyze_js_bundle,
    analyze_css_bundle,
    summarize_bundle_diff,
    insights_equal,
)


class FrontendMonitor:
    """前端资源监控器"""

    def __init__(self, config: Dict, storage):
        """初始化前端监控器

        Args:
            config: 配置字典
            storage: 存储管理器实例
        """
        self.config = config
        self.storage = storage
        self.targets = config.get("targets", {})
        self.frontend_config = config.get("frontend", {})

        self.session = None
        self._resource_hash_state = {}
        self.results = {
            "timestamp": None,
            "changes": [],
            "resources": {},
            "patterns": {},
            "commit": {},
            "feature_flags": {},
            "api_endpoints": [],
            "legal_docs": {},
            "model_configs": {},
            "bundle_insights": {},
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 HTTP session"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(
                total=self.config.get("monitoring", {}).get("timeout_seconds", 30)
            )
            user_agent = self.config.get("browser", {}).get(
                "user_agent",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            )
            headers = {"User-Agent": user_agent}
            self.session = aiohttp.ClientSession(timeout=timeout, headers=headers)
        return self.session

    async def check(self) -> Dict[str, Any]:
        """执行前端资源检查

        Returns:
            检查结果字典
        """
        logger.info("开始前端资源检查...")
        self.results["timestamp"] = datetime.now().isoformat()

        try:
            # 1. 获取主页 HTML
            html_content = await self._fetch_main_page()

            # 2. 提取 commit-id
            await self._extract_commit_id(html_content)

            # 3. 提取前端资源 URL
            resources = self._extract_resources(html_content)
            self.results["resources"] = resources

            # 4. 检查资源变化
            await self._check_resource_changes(resources)

            # 5. 分析关键代码模式
            await self._analyze_code_patterns(resources)

            # 6. 提取 feature flags
            await self._extract_feature_flags(resources)

            # 7. 提取 API 端点
            await self._extract_api_endpoints(resources)

            # 8. 检查 CDN Last-Modified
            await self._check_cdn_last_modified(resources)

            # 9. 检测新功能
            await self._detect_new_features(resources)

            # 10. 检查法律文档更新
            await self._check_legal_docs()

            # 11. 检查 model_configs（需 auth_token，否则记录空响应）
            await self._check_model_configs()

            # 12. 深度拆解关键 bundles
            await self._inspect_bundles(resources)

        except Exception as e:
            logger.error(f"前端资源检查失败: {e}", exc_info=True)
            self.results["error"] = str(e)

        return self.results

    def _stamp_change(
        self,
        change: Dict[str, Any],
        source_time: str = "",
        source_time_type: str = "unknown",
    ) -> Dict[str, Any]:
        observed_at = datetime.now().isoformat()
        change["observed_at"] = observed_at
        change["detected_at"] = observed_at
        if source_time:
            change["source_time"] = source_time
            change["source_time_type"] = source_time_type
        return change

    def _normalize_text(self, text: str) -> str:
        lines = []
        for line in text.splitlines():
            compact = re.sub(r"\s+", " ", line).strip()
            if compact:
                lines.append(compact)
        return "\n".join(lines)

    def _summarize_text_diff(self, old_text: str, new_text: str) -> List[str]:
        old_lines = [line for line in old_text.splitlines() if line.strip()]
        new_lines = [line for line in new_text.splitlines() if line.strip()]
        matcher = SequenceMatcher(None, old_lines, new_lines)
        evidence = []
        for opcode, i1, i2, j1, j2 in matcher.get_opcodes():
            if opcode == "equal":
                continue
            added = [line for line in new_lines[j1:j2] if len(line) >= 10][:2]
            removed = [line for line in old_lines[i1:i2] if len(line) >= 10][:2]
            if added:
                evidence.append("正文新增: " + " | ".join(added))
            if removed:
                evidence.append("正文移除: " + " | ".join(removed))
            if len(evidence) >= 4:
                break
        return evidence

    async def _fetch_main_page(self) -> str:
        """获取主页 HTML 内容

        Returns:
            HTML 内容字符串
        """
        base_url = self.targets.get("base_url")
        session = await self._get_session()

        logger.info(f"获取主页: {base_url}")

        async with session.get(base_url) as response:
            response.raise_for_status()
            return await response.text()

    async def _extract_commit_id(self, html: str):
        """从 HTML 中提取 commit-id

        Args:
            html: HTML 内容
        """
        logger.info("提取 commit-id...")

        soup = BeautifulSoup(html, "html.parser")

        # 从 <meta name="commit-id"> 提取
        commit_id = None
        meta = soup.find("meta", {"name": "commit-id"})
        if meta:
            commit_id = meta.get("content", "").strip()
            logger.info(f"  commit-id: {commit_id}")
        else:
            logger.warning("  未找到 commit-id meta 标签")

        if not commit_id:
            return

        # 获取历史记录
        last_commit = await self.storage.get_last_commit()
        is_new = await self.storage.save_commit(commit_id)

        if last_commit and last_commit["commit_id"] != commit_id:
            change = self._stamp_change({
                "type": "commit_change",
                "old_commit": last_commit["commit_id"],
                "new_commit": commit_id,
                "last_seen": last_commit.get("timestamp"),
            })
            self.results["changes"].append(change)
            logger.warning(f"检测到 commit-id 变化: {last_commit['commit_id']} -> {commit_id}")
        elif is_new:
            logger.info(f"首次记录 commit-id: {commit_id}")

        self.results["commit"]["id"] = commit_id

    def _extract_resources(self, html: str) -> Dict[str, Dict]:
        """从 HTML 中提取前端资源 URL

        Args:
            html: HTML 内容

        Returns:
            资源字典 {类型: {文件名: URL}}
        """
        soup = BeautifulSoup(html, "html.parser")
        resources = {
            "js": {},
            "css": {}
        }

        # 提取 JS 文件 - 使用所有 script 标签，不过滤
        for script in soup.find_all("script", {"src": True}):
            src = script["src"]
            if "static/" in src or ".js" in src:
                filename = src.split("/")[-1].split("?")[0]
                full_url = src if src.startswith("http") else urljoin(
                    self.targets.get("cdn_base", ""), src
                )
                resources["js"][filename] = full_url
                logger.debug(f"发现 JS 文件: {filename}")

        # 提取 CSS 文件
        for link in soup.find_all("link", {"rel": "stylesheet", "href": True}):
            href = link["href"]
            if "static/" in href or ".css" in href:
                filename = href.split("/")[-1].split("?")[0]
                full_url = href if href.startswith("http") else urljoin(
                    self.targets.get("cdn_base", ""), href
                )
                resources["css"][filename] = full_url
                logger.debug(f"发现 CSS 文件: {filename}")

        logger.info(f"提取到 {len(resources['js'])} 个 JS 文件, {len(resources['css'])} 个 CSS 文件")

        return resources

    async def _check_resource_changes(self, resources: Dict):
        """检查资源文件变化

        Args:
            resources: 资源字典
        """
        logger.info("检查资源文件变化...")

        session = await self._get_session()

        for resource_type, files in resources.items():
            for filename, url in files.items():
                try:
                    file_hash = await self._calculate_remote_file_hash(session, url)

                    last_hash = await self.storage.get_last_resource_hash(filename)

                    if last_hash:
                        if file_hash != last_hash["hash"]:
                            self._resource_hash_state[filename] = {
                                "current_hash": file_hash,
                                "hash_changed": True,
                            }
                            change = self._stamp_change({
                                "type": "resource_change",
                                "resource_type": resource_type,
                                "filename": filename,
                                "url": url,
                                "old_hash": last_hash["hash"],
                                "new_hash": file_hash,
                                "last_seen": last_hash["timestamp"],
                            })
                            self.results["changes"].append(change)
                            logger.warning(f"检测到 {resource_type.upper()} 文件变化: {filename}")
                            logger.info(f"  旧 hash: {last_hash['hash'][:16]}...")
                            logger.info(f"  新 hash: {file_hash[:16]}...")
                        else:
                            self._resource_hash_state[filename] = {
                                "current_hash": file_hash,
                                "hash_changed": False,
                            }
                            logger.debug(f"{filename} 未变化")
                    else:
                        self._resource_hash_state[filename] = {
                            "current_hash": file_hash,
                            "hash_changed": True,
                        }
                        logger.info(f"首次发现文件: {filename}")
                        change = self._stamp_change({
                            "type": "new_resource",
                            "resource_type": resource_type,
                            "filename": filename,
                            "url": url,
                            "hash": file_hash,
                        })
                        self.results["changes"].append(change)

                    await self.storage.save_resource_hash(filename, file_hash, url)

                except Exception as e:
                    logger.error(f"检查文件 {filename} 失败: {e}")

    async def _calculate_remote_file_hash(self, session: aiohttp.ClientSession, url: str) -> str:
        """计算远程文件的 hash

        Args:
            session: HTTP session
            url: 文件 URL

        Returns:
            文件的 MD5 hash
        """
        async with session.get(url) as response:
            response.raise_for_status()
            content = await response.read()
            return hashlib.md5(content).hexdigest()

    async def _analyze_code_patterns(self, resources: Dict):
        """分析关键代码模式

        Args:
            resources: 资源字典
        """
        logger.info("分析关键代码模式...")

        session = await self._get_session()
        key_patterns = self.frontend_config.get("key_patterns", [])

        main_js = self._find_main_js_file(resources["js"])
        if not main_js:
            logger.warning("未找到 main.js 文件")
            return

        filename, url = main_js
        logger.info(f"分析文件: {filename}")

        try:
            async with session.get(url) as response:
                response.raise_for_status()
                js_content = await response.text()

            commit_id = self.results.get("commit", {}).get("id")

            # 提取 commit-datetime
            dt_match = re.search(r'commit_datetime:"([^"]*)"', js_content)
            if dt_match:
                commit_dt = dt_match.group(1)
                self.results["commit"]["datetime"] = commit_dt
                logger.info(f"  commit-datetime: {commit_dt}")
                for change in reversed(self.results["changes"]):
                    if change.get("type") == "commit_change" and change.get("new_commit") == commit_id:
                        change["source_time"] = commit_dt
                        change["source_time_type"] = "bundle_commit_datetime"
                        break

            # 提取前端包版本
            ver_match = re.search(r'@deepseek/chat[^"]*"\s*:\s*"([^"]+)"', js_content)
            if not ver_match:
                ver_match = re.search(r'@deepseek/chat[^"]*version\s*:\s*"([^"]+)"', js_content)
            if ver_match:
                self.results["commit"]["package_version"] = ver_match.group(1)
                logger.info(f"  package: @deepseek/chat {ver_match.group(1)}")

            # 更新 commit 记录中的 datetime 和 package_version
            if commit_id:
                await self.storage.save_commit(
                    commit_id,
                    commit_datetime=self.results["commit"].get("datetime"),
                    package_version=self.results["commit"].get("package_version"),
                )

            # 提取代码模式
            extracted_patterns = extract_code_patterns(js_content, key_patterns)
            self.results["patterns"] = extracted_patterns

            last_patterns = await self.storage.get_last_code_patterns(filename)

            if last_patterns:
                pattern_changes = compare_patterns(last_patterns["patterns"], extracted_patterns)

                if pattern_changes:
                    change = self._stamp_change({
                        "type": "pattern_change",
                        "filename": filename,
                        "changes": pattern_changes,
                    })
                    self.results["changes"].append(change)
                    logger.warning(f"检测到 {len(pattern_changes)} 个代码模式变化")

                    for pc in pattern_changes:
                        logger.info(f"  [{pc['pattern_name']}] {pc['change_type']}")
                        if pc.get("old_value"):
                            logger.info(f"    旧值: {pc['old_value'][:100]}...")
                        if pc.get("new_value"):
                            logger.info(f"    新值: {pc['new_value'][:100]}...")
            else:
                logger.info("首次保存代码模式")

            await self.storage.save_code_patterns(filename, extracted_patterns)

        except Exception as e:
            logger.error(f"代码模式分析失败: {e}", exc_info=True)

    async def _extract_feature_flags(self, resources: Dict):
        """从 JS 内容中提取 feature flags

        Args:
            resources: 资源字典
        """
        logger.info("提取 Feature Flags...")

        session = await self._get_session()
        main_js = self._find_main_js_file(resources["js"])
        if not main_js:
            return

        filename, url = main_js

        try:
            async with session.get(url) as response:
                response.raise_for_status()
                js_content = await response.text()

            # 提取 getFeature("name", default) 调用
            pattern = r'getFeature\("([^"]+)",\s*([^)]+)\)'
            matches = re.findall(pattern, js_content)
            flags = {}
            for name, default in matches:
                flags[name] = default

            if not flags:
                logger.info("  未提取到 feature flags")
                return

            self.results["feature_flags"] = flags
            logger.info(f"  提取到 {len(flags)} 个 feature flags:")
            for name, default in sorted(flags.items()):
                logger.info(f"    {name} = {default}")

            # 与上次对比
            last_flags = await self.storage.get_last_feature_flags()
            if last_flags and last_flags["flags"] != flags:
                # 找出差异
                old_flags = last_flags["flags"]
                added = set(flags.keys()) - set(old_flags.keys())
                removed = set(old_flags.keys()) - set(flags.keys())
                changed = {k for k in set(flags.keys()) & set(old_flags.keys())
                           if flags[k] != old_flags[k]}

                if added or removed or changed:
                    change = self._stamp_change({
                        "type": "feature_flags_change",
                        "added": list(added),
                        "removed": list(removed),
                        "changed": {k: {"old": old_flags[k], "new": flags[k]} for k in changed},
                    })
                    self.results["changes"].append(change)
                    if added:
                        logger.warning(f"  新增 flags: {added}")
                    if removed:
                        logger.warning(f"  移除 flags: {removed}")
                    if changed:
                        logger.warning(f"  变化 flags: {changed}")

            await self.storage.save_feature_flags(flags)

        except Exception as e:
            logger.error(f"Feature flags 提取失败: {e}")

    async def _extract_api_endpoints(self, resources: Dict):
        """从 JS 内容中提取 API 端点

        Args:
            resources: 资源字典
        """
        logger.info("提取 API 端点...")

        session = await self._get_session()
        main_js = self._find_main_js_file(resources["js"])
        if not main_js:
            return

        filename, url = main_js

        try:
            async with session.get(url) as response:
                response.raise_for_status()
                js_content = await response.text()

            endpoints = sorted(set(re.findall(r'"/api/v0/[^"]*"', js_content)))
            # 去掉双引号
            endpoints = [ep.strip('"') for ep in endpoints]
            self.results["api_endpoints"] = endpoints
            logger.info(f"  提取到 {len(endpoints)} 个 API 端点")

            # 与上次对比
            last_endpoints = await self.storage.get_last_api_endpoints()
            if last_endpoints:
                old_set = set(last_endpoints["endpoints"])
                new_set = set(endpoints)
                added = new_set - old_set
                removed = old_set - new_set

                if added or removed:
                    change = self._stamp_change({
                        "type": "api_endpoints_change",
                        "added": list(added),
                        "removed": list(removed),
                    })
                    self.results["changes"].append(change)
                    if added:
                        logger.warning(f"  新增端点: {added}")
                    if removed:
                        logger.warning(f"  移除端点: {removed}")

            await self.storage.save_api_endpoints(endpoints)

        except Exception as e:
            logger.error(f"API 端点提取失败: {e}")

    async def _check_cdn_last_modified(self, resources: Dict):
        """检查 CDN 资源的 Last-Modified

        Args:
            resources: 资源字典
        """
        logger.info("检查 CDN Last-Modified...")

        session = await self._get_session()

        for resource_type, files in resources.items():
            for filename, url in files.items():
                try:
                    async with session.head(url) as response:
                        last_modified = response.headers.get("Last-Modified", "")
                        etag = response.headers.get("ETag", "")
                        content_length = response.headers.get("Content-Length", "")

                    if not last_modified:
                        continue

                    last_record = await self.storage.get_last_cdn_resource(filename)
                    hash_changed = self._resource_hash_state.get(filename, {}).get("hash_changed", False)

                    if last_record and last_record["last_modified"] != last_modified:
                        # CDN 的 Last-Modified 会偶发抖动。只有在内容或其他签名也变时才认为是有效更新。
                        etag_changed = (last_record.get("etag") or "") != (etag or "")
                        size_changed = (last_record.get("content_length") or 0) != (int(content_length) if content_length else 0)
                        if not any([hash_changed, etag_changed, size_changed]):
                            logger.info(
                                f"忽略 CDN Last-Modified 抖动: {filename} "
                                f"{last_record['last_modified']} -> {last_modified}"
                            )
                            await self.storage.save_cdn_resource(
                                filename, last_modified, etag,
                                int(content_length) if content_length else None
                            )
                            continue
                        change = self._stamp_change({
                            "type": "cdn_update",
                            "filename": filename,
                            "old_modified": last_record["last_modified"],
                            "new_modified": last_modified,
                            "etag_changed": etag_changed,
                            "size_changed": size_changed,
                            "content_changed": hash_changed,
                        }, source_time=last_modified, source_time_type="http_last_modified")
                        self.results["changes"].append(change)
                        logger.warning(f"CDN 资源更新: {filename}")
                        logger.info(f"  旧: {last_record['last_modified']}")
                        logger.info(f"  新: {last_modified}")

                    await self.storage.save_cdn_resource(
                        filename, last_modified, etag,
                        int(content_length) if content_length else None
                    )

                except Exception as e:
                    logger.debug(f"检查 CDN {filename} 失败: {e}")

    async def _check_legal_docs(self):
        """检查法律文档更新"""
        legal_urls = self.config.get("tracking", {}).get("legal_docs", [])
        if not legal_urls:
            return

        logger.info("检查法律文档更新...")

        session = await self._get_session()

        for doc in legal_urls:
            name = doc["name"]
            url = doc["url"]

            try:
                async with session.get(url) as response:
                    last_modified = response.headers.get("Last-Modified", "")
                    etag = response.headers.get("ETag", "")
                    content_type = response.headers.get("Content-Type", "")
                    html = await response.text()

                if not last_modified:
                    continue

                last_record = await self.storage.get_last_legal_doc(name)
                previous_snapshot = await self.storage.get_last_surface_snapshot(url)
                current_text = self._normalize_text(BeautifulSoup(html, "html.parser").get_text("\n", strip=True))
                current_snapshot = {
                    "final_url": url,
                    "title": name,
                    "last_modified": last_modified,
                    "etag": etag,
                    "content_type": content_type,
                    "status_code": 200,
                    "html_hash": hashlib.md5(html.encode("utf-8")).hexdigest(),
                    "text_hash": hashlib.md5(current_text.encode("utf-8")).hexdigest(),
                    "normalized_text": current_text,
                    "signals": {
                        "text_preview": current_text.splitlines()[:20],
                    },
                }

                if last_record and last_record["last_modified"] != last_modified:
                    evidence = []
                    if previous_snapshot:
                        evidence = self._summarize_text_diff(
                            previous_snapshot.get("normalized_text", ""),
                            current_snapshot["normalized_text"],
                        )
                    change = self._stamp_change({
                        "type": "legal_doc_update",
                        "doc_name": name,
                        "old_modified": last_record["last_modified"],
                        "new_modified": last_modified,
                        "url": url,
                        "summary": f"{name} 更新时间变化",
                        "evidence": evidence,
                    }, source_time=last_modified, source_time_type="http_last_modified")
                    self.results["changes"].append(change)
                    logger.warning(f"法律文档更新: {name}")
                    logger.info(f"  旧: {last_record['last_modified']}")
                    logger.info(f"  新: {last_modified}")

                await self.storage.save_legal_doc(name, last_modified, url)
                await self.storage.save_surface_snapshot(url, name, "legal_doc", current_snapshot)
                self.results["legal_docs"][name] = last_modified

            except Exception as e:
                logger.debug(f"检查法律文档 {name} 失败: {e}")

    async def _check_model_configs(self):
        """检查 /api/v0/client/settings 返回的 model_configs（灰度追踪）"""
        base_url = self.targets.get("base_url")
        auth_token = self.targets.get("auth_token", "")
        url = f"{base_url}/api/v0/client/settings"
        session = await self._get_session()

        headers = {}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        try:
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()
                data = await response.json()

            api_data = data.get("data")
            model_count = 0
            has_real_model_configs = False
            if isinstance(api_data, dict):
                model_count = len(api_data.get("model_configs", []))
                has_real_model_configs = "model_configs" in api_data

            self.results["model_configs"] = {
                "has_data": api_data is not None,
                "model_count": model_count,
                "raw_data": api_data,
                "raw_response": data,
            }

            # 与上次对比
            last = await self.storage.get_last_model_config()
            if last:
                last_str = json.dumps(last["config"], ensure_ascii=False, sort_keys=True)
                curr_str = json.dumps(api_data if api_data is not None else {}, ensure_ascii=False, sort_keys=True)
                last_has_real = isinstance(last["config"], dict) and "model_configs" in last["config"]
                if last_str != curr_str and (has_real_model_configs or last_has_real):
                    change = self._stamp_change({
                        "type": "model_configs_change",
                        "old": last["config"],
                        "new": api_data if api_data is not None else {},
                    })
                    self.results["changes"].append(change)
                    logger.warning("检测到 model_configs 变化")
                    logger.info(f"  旧: {last_str[:200]}...")
                    logger.info(f"  新: {curr_str[:200]}...")
                else:
                    logger.debug("model_configs 未变化")
            else:
                logger.info("首次记录 model_configs")

            # 仅保存真实 model_configs 数据，避免错误响应/空数据污染历史
            if has_real_model_configs:
                await self.storage.save_model_config(api_data)

        except Exception as e:
            logger.error(f"model_configs 检查失败: {e}")

    def _find_main_js_file(self, js_files: Dict[str, str]) -> Optional[tuple]:
        """找到 main JS 文件

        Args:
            js_files: JS 文件字典

        Returns:
            (filename, url) 元组，如果找不到返回 None
        """
        for filename, url in js_files.items():
            if filename.startswith("main.") and filename.endswith(".js"):
                return (filename, url)
        return None

    async def _detect_new_features(self, resources: Dict):
        """检测新功能

        Args:
            resources: 资源字典
        """
        logger.info("检测新功能...")

        patterns = self.results.get("patterns", {})

        # 检测三模型模式
        if any("三模型" in str(v) or "three_model" in str(v).lower() for v in patterns.values()):
            if not await self.storage.was_feature_detected("three_model_mode"):
                change = self._stamp_change({
                    "type": "new_feature",
                    "feature_name": "三模型模式",
                    "description": "检测到可能支持三种模型选择的功能",
                })
                self.results["changes"].append(change)
                logger.info("检测到新功能: 三模型模式")
                await self.storage.mark_feature_detected("three_model_mode")

        # 检测文件上传功能
        file_feature = patterns.get("file_feature", {})
        if file_feature and not await self.storage.was_feature_detected("file_upload"):
            change = self._stamp_change({
                "type": "new_feature",
                "feature_name": "文件上传",
                "description": f"检测到文件上传配置: {file_feature}",
            })
            self.results["changes"].append(change)
            logger.info("检测到新功能: 文件上传")
            await self.storage.mark_feature_detected("file_upload")

        # 基于 feature flags 检测新功能
        flags = self.results.get("feature_flags", {})
        new_flag_features = {
            "chat_hcaptcha": "hCaptcha 验证码",
            "allow_file_with_search": "联网搜索+文件上传组合",
            "pow_prefetch": "PoW 反滥用预取",
            "session_prefetch": "会话预取",
            "sse_auto_resume_timeout": "SSE 断线自动重连",
        }
        for flag, desc in new_flag_features.items():
            if flag in flags and not await self.storage.was_feature_detected(f"flag_{flag}"):
                change = self._stamp_change({
                    "type": "new_feature",
                    "feature_name": desc,
                    "description": f"Feature flag: {flag} = {flags[flag]}",
                })
                self.results["changes"].append(change)
                logger.info(f"检测到新功能: {desc} ({flag})")
                await self.storage.mark_feature_detected(f"flag_{flag}")

    async def _inspect_bundles(self, resources: Dict):
        """深度分析关键 bundles，提取 API/依赖/UI 语义信号。"""
        logger.info("深度拆解关键 bundles...")

        session = await self._get_session()
        targets = []

        main_js = self._find_main_js_file(resources["js"])
        if main_js:
            targets.append(("js", main_js[0], main_js[1]))

        for filename, url in resources.get("js", {}).items():
            if filename.startswith("default-vendors.") and filename.endswith(".js"):
                targets.append(("js", filename, url))
                break

        for filename, url in resources.get("css", {}).items():
            if filename.startswith("main.") and filename.endswith(".css"):
                targets.append(("css", filename, url))
                break

        for bundle_type, filename, url in targets:
            try:
                async with session.get(url) as response:
                    response.raise_for_status()
                    content = await response.text()

                if bundle_type == "css":
                    insights = analyze_css_bundle(filename, content)
                else:
                    insights = analyze_js_bundle(filename, content)

                self.results["bundle_insights"][filename] = insights
                last = await self.storage.get_last_bundle_insights(filename)
                if last and not insights_equal(last["insights"], insights):
                    evidence = summarize_bundle_diff(last["insights"], insights)
                    change = self._stamp_change({
                        "type": "bundle_insights_change",
                        "filename": filename,
                        "bundle_role": insights.get("bundle_role"),
                        "summary": f"{filename} 的语义分析结果发生变化",
                        "evidence": evidence,
                    }, source_time=self.results.get("commit", {}).get("datetime", ""), source_time_type="bundle_commit_datetime")
                    self.results["changes"].append(change)
                    logger.warning(f"bundle 语义变化: {filename}")
                    for item in evidence[:5]:
                        logger.info(f"  {item}")

                await self.storage.save_bundle_insights(
                    filename,
                    insights.get("bundle_role", bundle_type),
                    insights,
                )
            except Exception as e:
                logger.error(f"bundle 深度分析失败 {filename}: {e}")

    async def cleanup(self):
        """清理资源"""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.debug("前端监控器 HTTP session 已关闭")
