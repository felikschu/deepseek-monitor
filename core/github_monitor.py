"""
GitHub 监控模块

追踪 DeepSeek 官方 GitHub 组织 (deepseek-ai) 的活动：
1. 新仓库创建
2. 仓库推送（代码更新）
3. Release/Tag 发布
4. Star 数变化
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

import aiohttp
from loguru import logger


GITHUB_ORG = "deepseek-ai"
GITHUB_API = "https://api.github.com"


class GitHubMonitor:
    """DeepSeek GitHub 组织活动监控器"""

    def __init__(self, config: Dict, storage):
        self.config = config
        self.storage = storage
        self.session = None
        self.results = {
            "timestamp": None,
            "changes": [],
            "repos": [],
            "new_repos": [],
            "updated_repos": [],
            "releases": [],
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "DeepSeek-Monitor",
            }
            # 尝试用 gh auth token
            try:
                import subprocess
                token = subprocess.check_output(
                    ["gh", "auth", "token"], stderr=subprocess.DEVNULL
                ).decode().strip()
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                    logger.debug("使用 gh CLI token 认证")
            except Exception:
                logger.debug("未找到 gh token，使用匿名访问（60 req/hr 限制）")

            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout, headers=headers)
        return self.session

    async def check(self) -> Dict[str, Any]:
        """执行 GitHub 检查"""
        logger.info("开始 GitHub 组织检查...")
        self.results["timestamp"] = datetime.utcnow().isoformat()

        try:
            session = await self._get_session()

            # 1. 获取所有仓库
            repos = await self._fetch_all_repos(session)
            self.results["repos"] = repos
            logger.info(f"获取到 {len(repos)} 个仓库")

            # 2. 检测新仓库
            await self._detect_new_repos(repos)

            # 3. 检测仓库更新
            await self._detect_repo_updates(repos)

            # 4. 检测新的 Release/Tag
            await self._detect_releases(session, repos)

            # 5. 保存快照
            await self._save_snapshot(repos)

        except Exception as e:
            logger.error(f"GitHub 检查失败: {e}", exc_info=True)
            self.results["error"] = str(e)

        return self.results

    async def _fetch_all_repos(self, session: aiohttp.ClientSession) -> List[Dict]:
        """获取组织的所有仓库"""
        repos = []
        page = 1
        while True:
            url = f"{GITHUB_API}/orgs/{GITHUB_ORG}/repos?sort=pushed&direction=desc&per_page=100&page={page}"
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.warning(f"GitHub API 返回 {resp.status}")
                    break
                data = await resp.json()
                if not data:
                    break
                repos.extend(data)
                if len(data) < 100:
                    break
                page += 1

        # 只保留关键字段
        return [
            {
                "name": r["name"],
                "full_name": r["full_name"],
                "description": r.get("description", ""),
                "html_url": r["html_url"],
                "stars": r["stargazers_count"],
                "forks": r["forks_count"],
                "language": r.get("language"),
                "created_at": r["created_at"],
                "pushed_at": r.get("pushed_at"),
                "updated_at": r["updated_at"],
                "topics": r.get("topics", []),
                "archived": r.get("archived", False),
            }
            for r in repos
        ]

    async def _detect_new_repos(self, repos: List[Dict]):
        """检测新创建的仓库"""
        logger.info("检测新仓库...")
        last_snapshot = await self.storage.get_last_github_snapshot()
        if not last_snapshot:
            logger.info("首次运行，跳过新仓库检测")
            return

        known_repos = {r["name"] for r in last_snapshot.get("repos", [])}
        for repo in repos:
            if repo["name"] not in known_repos:
                change = {
                    "type": "new_repo",
                    "repo_name": repo["name"],
                    "repo_url": repo["html_url"],
                    "description": repo.get("description", ""),
                    "stars": repo["stars"],
                    "created_at": repo["created_at"],
                    "detected_at": datetime.utcnow().isoformat(),
                }
                self.results["changes"].append(change)
                self.results["new_repos"].append(repo)
                logger.warning(f"新仓库: {repo['name']} (★{repo['stars']})")

    async def _detect_repo_updates(self, repos: List[Dict]):
        """检测有代码更新的仓库"""
        logger.info("检测仓库更新...")
        last_snapshot = await self.storage.get_last_github_snapshot()
        if not last_snapshot:
            return

        old_by_name = {r["name"]: r for r in last_snapshot.get("repos", [])}

        for repo in repos:
            name = repo["name"]
            if name not in old_by_name:
                continue

            old = old_by_name[name]

            # 检测 pushed_at 变化
            if repo.get("pushed_at") and old.get("pushed_at"):
                if repo["pushed_at"] != old["pushed_at"]:
                    change = {
                        "type": "repo_push",
                        "repo_name": name,
                        "repo_url": repo["html_url"],
                        "old_pushed": old["pushed_at"],
                        "new_pushed": repo["pushed_at"],
                        "detected_at": datetime.utcnow().isoformat(),
                    }
                    self.results["changes"].append(change)
                    self.results["updated_repos"].append(repo)
                    logger.info(f"仓库更新: {name} ({old['pushed_at'][:10]} → {repo['pushed_at'][:10]})")

            # 检测 star 数显著变化
            old_stars = old.get("stars", 0)
            new_stars = repo["stars"]
            if old_stars > 0 and abs(new_stars - old_stars) / old_stars > 0.05:
                change = {
                    "type": "stars_change",
                    "repo_name": name,
                    "old_stars": old_stars,
                    "new_stars": new_stars,
                    "diff": new_stars - old_stars,
                    "detected_at": datetime.utcnow().isoformat(),
                }
                self.results["changes"].append(change)

    async def _detect_releases(self, session: aiohttp.ClientSession, repos: List[Dict]):
        """检测最近的 Release"""
        logger.info("检测 Release...")

        # 只检查最近有更新的仓库
        recent_repos = [r for r in repos if r.get("pushed_at")]
        recent_repos.sort(key=lambda r: r.get("pushed_at", ""), reverse=True)
        check_repos = recent_repos[:15]  # 最多检查15个

        for repo in check_repos:
            try:
                url = f"{GITHUB_API}/repos/{GITHUB_ORG}/{repo['name']}/releases?per_page=3"
                async with session.get(url) as resp:
                    if resp.status != 200:
                        continue
                    releases = await resp.json()

                for rel in releases:
                    published = rel.get("published_at", "")
                    if not published:
                        continue

                    # 检查是否已知
                    is_known = await self.storage.is_github_release_known(
                        repo["name"], rel["tag_name"]
                    )
                    if not is_known:
                        change = {
                            "type": "new_release",
                            "repo_name": repo["name"],
                            "repo_url": repo["html_url"],
                            "tag": rel["tag_name"],
                            "title": rel.get("name", rel["tag_name"]),
                            "url": rel.get("html_url", ""),
                            "published_at": published,
                            "prerelease": rel.get("prerelease", False),
                            "detected_at": datetime.utcnow().isoformat(),
                        }
                        self.results["changes"].append(change)
                        self.results["releases"].append(change)
                        logger.warning(
                            f"新 Release: {repo['name']} {rel['tag_name']} ({published[:10]})"
                        )
                        await self.storage.save_github_release(
                            repo["name"], rel["tag_name"], published, change
                        )
            except Exception as e:
                logger.debug(f"检查 {repo['name']} releases 失败: {e}")

    async def _save_snapshot(self, repos: List[Dict]):
        """保存快照"""
        await self.storage.save_github_snapshot(repos)

    async def cleanup(self):
        if self.session and not self.session.closed:
            await self.session.close()
