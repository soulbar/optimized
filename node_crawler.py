import base64
import logging
from typing import Dict, List, Any, Optional

import requests
import yaml

from config import GITHUB_REPOS, GITHUB_TOKEN, DEFAULT_BRANCH

logger = logging.getLogger(__name__)


class GitHubNodeCrawler:
    """从多个 GitHub 仓库中爬取节点并解析"""

    def __init__(self) -> None:
        self.session = requests.Session()
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            )
        }
        # 配置了 Token 就自动带上，提升速率限制
        if GITHUB_TOKEN:
            headers["Authorization"] = f"token {GITHUB_TOKEN}"

        self.session.headers.update(headers)

    # ---------- GitHub 基础操作 ----------

    def get_github_file_content(self, repo: str, file_path: str) -> str:
        """获取 GitHub 文件内容（自动处理 base64 编码 & 速率限制日志）"""
        api_url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
        try:
            resp = self.session.get(api_url, timeout=10)

            if resp.status_code == 200:
                data = resp.json()

                # Content API 正常返回
                if isinstance(data, dict) and data.get("encoding") == "base64":
                    return base64.b64decode(data["content"]).decode(
                        "utf-8", errors="ignore"
                    )

                # 某些情况下可能直接返回文本
                if isinstance(data, dict) and isinstance(data.get("content"), str):
                    return data["content"]

                logger.warning(f"[crawler] 未知返回格式: {repo}/{file_path}")
                return ""

            if resp.status_code == 404:
                logger.debug(f"[crawler] 文件不存在: {repo}/{file_path}")
            elif resp.status_code == 403:
                logger.warning(
                    f"[crawler] 访问受限 (可能是 rate limit)，"
                    f"repo={repo}, path={file_path}, message={resp.text[:200]}"
                )
            else:
                logger.warning(
                    f"[crawler] 获取文件失败 {repo}/{file_path}: "
                    f"status={resp.status_code}, body={resp.text[:200]}"
                )
        except Exception as e:
            logger.error(f"[crawler] 获取文件内容失败 {repo}/{file_path}: {e}")

        return ""

    def search_github_files(self, repo: str) -> List[str]:
        """
        搜索 GitHub 仓库中的文件，返回可能包含节点的路径列表

        优先用 DEFAULT_BRANCH，其次尝试 master/main，全部失败则记录 warning。
        """
        branches_to_try = [DEFAULT_BRANCH, "master", "main"]
        tried = set()

        for branch in branches_to_try:
            if branch in tried:
                continue
            tried.add(branch)

            api_url = (
                f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"
            )
            try:
                resp = self.session.get(api_url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    files: List[str] = []
                    for item in data.get("tree", []):
                        if item.get("type") == "blob":
                            path = item.get("path", "")
                            # 只关心这些类型的文件
                            if any(
                                path.endswith(ext)
                                for ext in (".yaml", ".yml", ".txt", ".json")
                            ):
                                files.append(path)

                    logger.info(
                        f"[crawler] 仓库 {repo} 在分支 {branch} 找到 "
                        f"{len(files)} 个候选文件"
                    )
                    return files

                if resp.status_code == 404:
                    logger.debug(f"[crawler] 分支不存在: {repo}/{branch}")
                elif resp.status_code == 403:
                    logger.warning(
                        f"[crawler] 获取文件树受限 (rate limit?) "
                        f"{repo}/{branch}: {resp.text[:200]}"
                    )
                else:
                    logger.warning(
                        f"[crawler] 搜索文件失败 {repo}/{branch}: "
                        f"status={resp.status_code}, body={resp.text[:200]}"
                    )
            except Exception as e:
                logger.error(f"[crawler] 搜索文件失败 {repo}/{branch}: {e}")

        logger.warning(f"[crawler] 仓库 {repo} 无法获取文件树，请检查仓库是否存在/是否公开")
        return []

    # ---------- 解析逻辑 ----------

    def parse_clash_yaml(self, content: str) -> List[Dict[str, Any]]:
        """解析 Clash YAML 配置中的 proxies 节点"""
        try:
            data = yaml.safe_load(content)
            if not isinstance(data, dict):
                return []

            proxies = data.get("proxies") or []
            nodes: List[Dict[str, Any]] = []

            for p in proxies:
                if not isinstance(p, dict):
                    continue
                node = {
                    "type": p.get("type") or "unknown",
                    "name": p.get("name") or "unknown",
                    "server": p.get("server"),
                    "port": p.get("port"),
                    "config": p,
                }
                if node["server"] and node["port"]:
                    nodes.append(node)

            logger.info(f"[crawler] 从 Clash 配置解析到 {len(nodes)} 个节点")
            return nodes
        except Exception as e:
            logger.error(f"[crawler] 解析 Clash 配置失败: {e}")
            return []

    def parse_links_from_text(self, content: str) -> List[Dict[str, Any]]:
        """从纯文本中解析 ss://, vmess://, trojan:// 等链接（简化版）"""
        nodes: List[Dict[str, Any]] = []
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            if any(
                line.startswith(prefix)
                for prefix in ("ss://", "vmess://", "trojan://", "vless://")
            ):
                nodes.append(
                    {
                        "type": "url",
                        "name": "raw-link",
                        "server": None,
                        "port": None,
                        "config": {"link": line},
                    }
                )
        if nodes:
            logger.info(f"[crawler] 从文本解析到 {len(nodes)} 条链接节点")
        return nodes

    def parse_nodes_from_file(self, path: str, content: str) -> List[Dict[str, Any]]:
        """根据文件后缀和内容选择解析方式"""
        path_lower = path.lower()
        if path_lower.endswith((".yaml", ".yml")):
            return self.parse_clash_yaml(content)
        if path_lower.endswith(".txt"):
            return self.parse_links_from_text(content)
        if path_lower.endswith(".json"):
            # TODO: 根据实际 JSON 结构解析
            return []
        return []

    # ---------- 对外主入口 ----------

    def crawl_repo(self, repo: str) -> List[Dict[str, Any]]:
        """爬取单个仓库，返回解析后的节点列表"""
        logger.info(f"[crawler] 开始爬取仓库: {repo}")
        files = self.search_github_files(repo)
        all_nodes: List[Dict[str, Any]] = []

        for path in files:
            content = self.get_github_file_content(repo, path)
            if not content:
                continue
            nodes = self.parse_nodes_from_file(path, content)
            all_nodes.extend(nodes)

        logger.info(f"[crawler] 仓库 {repo} 共爬取到 {len(all_nodes)} 个节点（未去重）")
        return all_nodes

    def crawl_all(self, repos: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        爬取所有仓库并去重。

        兼容旧代码：
        - 如果传入 repos（例如 main.py 里传的 GITHUB_REPOS），就用传入的；
        - 否则默认用 config.GITHUB_REPOS。
        """
        if repos is None:
            repos = GITHUB_REPOS

        all_nodes: List[Dict[str, Any]] = []
        seen = set()

        for repo in repos:
            repo_nodes = self.crawl_repo(repo)
            for n in repo_nodes:
                key = (n.get("type"), n.get("server"), n.get("port"), n.get("name"))
                if key in seen:
                    continue
                seen.add(key)
                all_nodes.append(n)

        logger.info(f"[crawler] 去重后共 {len(all_nodes)} 个唯一节点")
        return all_nodes
