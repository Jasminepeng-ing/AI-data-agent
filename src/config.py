"""
src/config.py
=============
全局配置：从 .env 读取 API Key，定义 LLM 相关常量。
Streamlit Cloud 部署时通过 st.secrets 注入，本地开发从 .env 读取。
"""

import os
from dotenv import load_dotenv

# 向上两级找到项目根目录，确保无论从哪里 import 都能找到 .env
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))


def _get_secret(key: str, default: str = "") -> str:
    """优先从 st.secrets 读取（Streamlit Cloud），回退到环境变量（本地 .env）。"""
    try:
        import streamlit as st
        return st.secrets[key]
    except (KeyError, FileNotFoundError, Exception):
        return os.environ.get(key, default)


DEEPSEEK_API_KEY: str = _get_secret("DEEPSEEK_API_KEY")

DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
MODEL_NAME: str = "deepseek-chat"
MAX_TOKENS: int = 4000
LARGE_QUERY_ROW_THRESHOLD: int = 100_000  # 超过此行数才弹确认
