# config.py
"""
集中配置：
- GitHub 仓库列表
- GitHub Token / 默认分支
- 测试站点 & 测速参数
- 并发数 & 输出文件名
"""

import os

# GitHub 节点仓库列表
# 支持从环境变量 GITHUB_REPOS 读取，格式: repo1,repo2,repo3
_env_repos = os.getenv("GITHUB_REPOS")
if _env_repos:
    GITHUB_REPOS = [r.strip() for r in _env_repos.split(",") if r.strip()]
else:
    # 默认值按你原来的来
    GITHUB_REPOS = [
        "freefq/free",
        "peasoft/NoMoreWalls",
        "ripaojiedian/free-ssr-ss-v2ray-vless-clash",
    ]

# GitHub Token（可选，用于提升 API 速率限制）
# 建议在 GitHub Actions 的 Secrets 中配置，例如 GITHUB_TOKEN
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# 默认分支名，用于爬取目标仓库文件树
# 可被环境变量 DEFAULT_BRANCH 覆盖
DEFAULT_BRANCH = os.getenv("DEFAULT_BRANCH", "main")

# 测试目标网站
TEST_URLS = {
    "youtube": "https://www.youtube.com",
    "github": "https://www.github.com",
    "chatgpt": "https://chat.openai.com",
    "netflix": "https://www.netflix.com",
}

# 测速配置
SPEED_TEST_URL = "https://www.google.com/generate_204"
MIN_SPEED = 100  # 最小速度 (KB/s)
MAX_SPEED = 300  # 最大速度 (KB/s)

# 超时设置
TIMEOUT = 10       # 连接超时（秒）
TEST_TIMEOUT = 15  # 测试超时（秒）

# 并发设置
MAX_CONCURRENT = 20  # 最大并发数

# 输出文件
OUTPUT_NODES_TXT = "nodes.txt"
OUTPUT_NODES_JSON = "nodes.json"
LOG_FILE = "log.txt"
