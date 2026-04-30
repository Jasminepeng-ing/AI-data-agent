"""
src/config.py
=============
全局配置：从 .env 读取 API Key，定义 LLM 相关常量。
"""

import os
from dotenv import load_dotenv

# 向上两级找到项目根目录，确保无论从哪里 import 都能找到 .env
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

DEEPSEEK_API_KEY: str = os.environ.get("DEEPSEEK_API_KEY", "")

DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
MODEL_NAME: str = "deepseek-chat"
MAX_TOKENS: int = 4000
LARGE_QUERY_ROW_THRESHOLD: int = 100_000  # 超过此行数才弹确认
