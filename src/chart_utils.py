"""
src/chart_utils.py
==================
词云图渲染工具（纯 Python，不依赖 Streamlit）。

- get_font_path    : 自动检测可用的中文字体路径
- render_wordcloud : 词频构建 → 词云生成 → PNG bytes 输出
"""

import os
import platform
import re
from io import BytesIO

import pandas as pd

# ── 中文常见停用词 ─────────────────────────────────────────────────────────────
_ZH_STOPWORDS = frozenset({
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人",
    "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去",
    "你", "会", "着", "没有", "看", "好", "自己", "这", "那", "还",
    "什么", "来", "他", "吧", "他们", "把", "更", "么", "嗯", "从",
    "以", "被", "已", "等", "但", "于", "由", "对", "或", "其",
    "可", "能", "而", "及", "与", "若", "只", "便", "为", "当",
    "所", "如", "并", "各", "之", "内", "因", "后", "前", "下",
    "中", "外", "过", "又", "此", "时", "以及", "虽然", "尽管",
    "因此", "所以", "但是", "然而", "同时", "另外", "其中", "包括",
    "例如", "比如", "由于", "如果", "不过", "而且", "或者",
    "", " ",
})


def get_font_path() -> str | None:
    """
    自动检测可用的中文字体路径，按优先级：
    1. assets/fonts/SimHei.ttf（项目内置）
    2. 系统字体（Windows / Mac / Linux 各平台路径）
    3. 返回 None，降级为默认字体（中文字符将显示为方块）
    """
    project_font = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "assets", "fonts", "SimHei.ttf")
    )
    if os.path.exists(project_font):
        return project_font

    system_fonts = {
        "Windows": [
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/msyhbd.ttc",
        ],
        "Darwin": [
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ],
        "Linux": [
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ],
    }
    for path in system_fonts.get(platform.system(), []):
        if os.path.exists(path):
            return path

    print(
        "⚠️ 未找到中文字体，词云中文可能显示为方块。"
        "请将 SimHei.ttf 放入 assets/fonts/ 目录。"
    )
    return None


def _is_chinese(text: str) -> bool:
    """判断字符串中是否含有中文字符。"""
    return any("一" <= ch <= "鿿" for ch in text)


def _tokenize(text: str, language: str) -> list[str]:
    """
    对文本分词：
    - language='zh' 或 auto 检测到中文 → 优先用 jieba，jieba 未安装则降级为标点切分
    - 其他语言 → 按空格/标点切分
    """
    use_jieba = language == "zh" or (language == "auto" and _is_chinese(text))

    if use_jieba:
        try:
            import jieba
            return list(jieba.cut(text, cut_all=False))
        except ImportError:
            # jieba 未安装时降级，打印警告
            print(
                "⚠️ jieba 未安装，中文将以标点/空格切分，效果较差。"
                "可运行 pip install jieba 改善分词质量。"
            )
            # 按中文标点 + 空格切分
            return re.split(
                r"[\s　-〿＀-￯，。！？、；：「」【】《》]+", text
            )

    # 英文 / 葡萄牙语等：按空白和常见分隔符切分
    return re.split(r"[\s\-_/\\]+", text)


def render_wordcloud(
    df: pd.DataFrame,
    text_col: str | None,
    word_col: str | None,
    freq_col: str | None,
    title: str,
    colormap: str = "viridis",
    max_words: int = 80,
    language: str = "auto",
) -> bytes:
    """
    渲染词云图，返回 PNG bytes（不依赖 Streamlit，方便单元测试）。

    两种输入模式（二选一）：
    - text_col 模式    : 原始文本列 → 自动分词 → 统计词频
    - word_col+freq_col: 已分词的词语列 + 数值词频列 → 直接构建词频字典

    Parameters
    ----------
    df         : 查询结果 DataFrame
    text_col   : 原始文本列名（与 word_col+freq_col 二选一）
    word_col   : 词语列名（已分词场景）
    freq_col   : 词频列名（已分词场景，必须为数值列）
    title      : 词云图标题（同时作为 matplotlib 标题）
    colormap   : Matplotlib 颜色方案，如 viridis / plasma / Blues / Reds
    max_words  : 最多展示词数，上限 200
    language   : 分词语言：'auto' 自动检测 / 'zh' 中文 / 'en' 英文

    Returns
    -------
    bytes : PNG 图像字节
    """
    try:
        from wordcloud import WordCloud
    except ImportError as exc:
        raise ImportError(
            "缺少 wordcloud 库，请运行: pip install wordcloud"
        ) from exc

    try:
        # 直接使用 Agg 后端类，绕开 matplotlib.use() 调用
        # matplotlib.use() 在 Streamlit 运行时可能失败（已有其他后端被加载）
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure
        from matplotlib import font_manager
    except ImportError as exc:
        raise ImportError(
            "缺少 matplotlib 库，请运行: pip install matplotlib"
        ) from exc

    # ── 1. max_words 安全限制 ──────────────────────────────────────────────────
    max_words = int(max_words) if max_words else 80
    if max_words > 200:
        print(f"⚠️ max_words={max_words} 超过上限 200，已自动截断为 200。")
        max_words = 200

    # ── 2. 构建词频字典 ────────────────────────────────────────────────────────
    freq_dict: dict[str, float] = {}

    if word_col and freq_col:
        # 已分词模式：直接累加词频
        for _, row in df.iterrows():
            word = str(row[word_col]).strip()
            try:
                freq = float(row[freq_col])
            except (ValueError, TypeError):
                continue
            if word and word not in _ZH_STOPWORDS and len(word) >= 1:
                freq_dict[word] = freq_dict.get(word, 0) + freq

    elif text_col:
        # 原始文本模式：合并所有文本 → 分词 → 统计
        texts = df[text_col].dropna().astype(str)
        combined = " ".join(texts.tolist())
        tokens = _tokenize(combined, language)
        for tok in tokens:
            tok = tok.strip()
            if len(tok) < 2:           # 过滤单字符（减少噪音）
                continue
            if tok in _ZH_STOPWORDS:
                continue
            freq_dict[tok] = freq_dict.get(tok, 0) + 1

    else:
        raise ValueError("参数错误：word_col+freq_col 或 text_col 至少需要提供一组。")

    if not freq_dict:
        raise ValueError(
            "词频字典为空，无法生成词云。"
            "可能原因：所有词均被停用词过滤，或文本为空。"
        )

    # ── 3. 生成词云对象 ────────────────────────────────────────────────────────
    font_path = get_font_path()
    wc_kwargs: dict = dict(
        width=900,
        height=450,
        background_color="white",
        colormap=colormap,
        max_words=max_words,
        prefer_horizontal=0.85,
        collocations=False,         # 避免词组（bigram）重复占位
    )
    if font_path:
        wc_kwargs["font_path"] = font_path

    wc = WordCloud(**wc_kwargs).generate_from_frequencies(freq_dict)

    # ── 4. Matplotlib 渲染（直接使用 FigureCanvasAgg，Streamlit 安全）────────
    fig = Figure(figsize=(12, 6))
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")

    # 标题字体：有中文字体时使用，否则 matplotlib 默认字体
    title_kwargs: dict = {"fontsize": 16, "pad": 10}
    if font_path:
        try:
            fp = font_manager.FontProperties(fname=font_path)
            title_kwargs["fontproperties"] = fp
        except Exception:
            pass   # 字体加载失败时静默降级，不影响图片生成
    ax.set_title(title, **title_kwargs)

    # ── 5. 输出 PNG bytes ──────────────────────────────────────────────────────
    buf = BytesIO()
    canvas.print_figure(buf, format="png", dpi=150, bbox_inches="tight")
    return buf.getvalue()
