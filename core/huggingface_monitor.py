"""
Hugging Face 官方组织监控

重点关注：
1. 官方组织是否新增公开模型卡
2. 现有模型卡的 lastModified 是否变化
3. 组织级公开统计（模型数/Spaces/Followers）快照
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from loguru import logger


class HuggingFaceMonitor:
    def __init__(self, config: Dict, storage):
        self.config = config
        self.storage = storage
        self.monitor_config = config.get("huggingface", {})
        self.results = {
            "timestamp": None,
            "changes": [],
            "org": {},
            "models": [],
        }

    async def check(self) -> Dict[str, Any]:
        if not self.monitor_config.get("enabled", True):
            return self.results

        self.results = {
            "timestamp": datetime.now().isoformat(),
            "changes": [],
            "org": {},
            "models": [],
        }

        org_name = self.monitor_config.get("org", "deepseek-ai")

        try:
            snapshot = await self._fetch_snapshot(org_name)
            self.results["org"] = snapshot.get("org", {})
            self.results["models"] = snapshot.get("models", [])[:20]

            previous = await self.storage.get_last_huggingface_snapshot(org_name)
            change = self._build_change(org_name, previous, snapshot)
            if change:
                self.results["changes"].append(change)

            await self.storage.save_huggingface_snapshot(org_name, snapshot)
        except Exception as exc:
            detail = str(exc) or exc.__class__.__name__
            logger.warning(f"Hugging Face 监控失败 {org_name}: {detail}")

        return self.results

    async def _fetch_json(self, url: str) -> Any:
        user_agent = self.config.get("browser", {}).get(
            "user_agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        )
        timeout_seconds = str(self.config.get("monitoring", {}).get("timeout_seconds", 30))
        process = await asyncio.create_subprocess_exec(
            "curl",
            "--fail",
            "--silent",
            "--show-error",
            "--location",
            "--http1.1",
            "--max-time",
            timeout_seconds,
            "--user-agent",
            user_agent,
            url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(stderr.decode("utf-8", errors="ignore").strip() or f"curl exited with {process.returncode}")
        return json.loads(stdout.decode("utf-8"))

    async def _fetch_snapshot(self, org_name: str) -> Dict[str, Any]:
        base_url = self.monitor_config.get("base_url", "https://huggingface.co").rstrip("/")
        max_models = int(self.monitor_config.get("max_models", 50))

        overview_url = f"{base_url}/api/organizations/{org_name}/overview"
        models_url = (
            f"{base_url}/api/models?author={org_name}&sort=lastModified&direction=-1&limit={max_models}"
        )

        overview = await self._fetch_json(overview_url)
        models = await self._fetch_json(models_url)

        org = {
            "name": overview.get("name") or org_name,
            "fullname": overview.get("fullname") or "",
            "avatarUrl": overview.get("avatarUrl") or "",
            "isVerified": bool(overview.get("isVerified")),
            "numUsers": overview.get("numUsers"),
            "numModels": overview.get("numModels"),
            "numSpaces": overview.get("numSpaces"),
            "numDatasets": overview.get("numDatasets"),
            "numPapers": overview.get("numPapers"),
            "numFollowers": overview.get("numFollowers"),
            "org_url": f"{base_url}/{org_name}",
            "activity_url": f"{base_url}/organizations/{org_name}/activity/models",
            "models_url": f"{base_url}/{org_name}/models",
        }

        normalized_models: List[Dict[str, Any]] = []
        for item in models or []:
            model_id = item.get("id") or item.get("modelId")
            if not model_id:
                continue
            normalized_models.append({
                "id": model_id,
                "name": model_id.split("/")[-1],
                "url": f"{base_url}/{model_id}",
                "lastModified": item.get("lastModified") or "",
                "createdAt": item.get("createdAt") or "",
                "likes": item.get("likes", 0),
                "downloads": item.get("downloads", 0),
                "pipeline_tag": item.get("pipeline_tag") or "",
                "library_name": item.get("library_name") or "",
                "private": bool(item.get("private")),
                "tags": item.get("tags") or [],
            })

        signals = {
            "model_ids": [item["id"] for item in normalized_models],
            "latest_models": [item["name"] for item in normalized_models[:10]],
            "pipeline_tags": sorted({item["pipeline_tag"] for item in normalized_models if item.get("pipeline_tag")}),
            "notable_tags": sorted(
                {
                    tag
                    for item in normalized_models
                    for tag in item.get("tags", [])
                    if any(marker in tag.lower() for marker in ["deepseek", "ocr", "vision", "code", "agent"])
                }
            )[:30],
        }

        return {
            "org": org,
            "models": normalized_models,
            "signals": signals,
            "fetched_at": datetime.now().isoformat(),
        }

    def _build_change(self, org_name: str, previous: Optional[Dict], current: Dict) -> Optional[Dict]:
        if not previous:
            return None

        prev_models = {item["id"]: item for item in previous.get("models", [])}
        curr_models = {item["id"]: item for item in current.get("models", [])}

        added_models = [curr_models[key] for key in curr_models.keys() - prev_models.keys()]
        removed_models = [prev_models[key] for key in prev_models.keys() - curr_models.keys()]
        updated_models = []
        for model_id in curr_models.keys() & prev_models.keys():
            prev_item = prev_models[model_id]
            curr_item = curr_models[model_id]
            if (prev_item.get("lastModified") or "") != (curr_item.get("lastModified") or ""):
                updated_models.append({
                    "id": model_id,
                    "name": curr_item.get("name"),
                    "old_last_modified": prev_item.get("lastModified") or "",
                    "new_last_modified": curr_item.get("lastModified") or "",
                    "url": curr_item.get("url"),
                })

        significant_change = any([added_models, removed_models, updated_models])
        if not significant_change:
            return None

        added_models.sort(key=lambda item: item.get("lastModified") or "", reverse=True)
        removed_models.sort(key=lambda item: item.get("lastModified") or "", reverse=True)
        updated_models.sort(key=lambda item: item.get("new_last_modified") or "", reverse=True)

        prev_org = previous.get("org", {})
        curr_org = current.get("org", {})

        evidence: List[str] = []
        if added_models:
            evidence.append(
                "新增公开模型卡: " + ", ".join(item.get("name", item.get("id", "")) for item in added_models[:8])
            )
        if updated_models:
            evidence.append(
                "模型卡最近更新时间变化: "
                + ", ".join(
                    f"{item.get('name')} ({item.get('new_last_modified')})" for item in updated_models[:6]
                )
            )
        if removed_models:
            evidence.append(
                "公开列表移除模型卡: "
                + ", ".join(item.get("name", item.get("id", "")) for item in removed_models[:6])
            )
        if prev_org.get("numModels") != curr_org.get("numModels"):
            evidence.append(
                f"组织公开模型数变化: {prev_org.get('numModels', 0)} → {curr_org.get('numModels', 0)}"
            )

        summary = f"Hugging Face 官方组织 {org_name} 出现模型卡变化"
        if added_models:
            summary = f"Hugging Face 出现新模型卡: {', '.join(item['name'] for item in added_models[:3])}"
        elif updated_models:
            summary = f"Hugging Face 模型卡最近更新时间变化: {', '.join(item['name'] for item in updated_models[:3])}"
        elif removed_models:
            summary = f"Hugging Face 公开列表移除模型卡: {', '.join(item['name'] for item in removed_models[:3])}"

        changed_times = [
            item.get("lastModified") for item in added_models if item.get("lastModified")
        ] + [
            item.get("new_last_modified") for item in updated_models if item.get("new_last_modified")
        ]
        source_time = max(changed_times) if changed_times else ""
        observed_at = datetime.now().isoformat()

        return {
            "type": "huggingface_model_change",
            "org_name": org_name,
            "org_url": curr_org.get("org_url"),
            "models_url": curr_org.get("models_url"),
            "activity_url": curr_org.get("activity_url"),
            "summary": summary,
            "added_models": added_models,
            "removed_models": removed_models,
            "updated_models": updated_models,
            "source_time": source_time,
            "source_time_type": "huggingface_last_modified" if source_time else "scraped_signal",
            "observed_at": observed_at,
            "detected_at": observed_at,
            "evidence": evidence,
        }

    async def cleanup(self):
        return None
