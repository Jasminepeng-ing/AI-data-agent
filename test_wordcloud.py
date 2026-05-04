"""
test_wordcloud.py
=================
独立测试 render_wordcloud 是否能正常返回 PNG bytes。
运行方式（在项目根目录）：
    python test_wordcloud.py
"""

import sys
import os

# 把 src 加入路径，使 chart_utils 可导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import pandas as pd
from chart_utils import render_wordcloud


def test_word_freq_mode():
    """word_col + freq_col 模式：直接传词语和词频。"""
    df = pd.DataFrame({
        "product_category": [
            "bed_bath_table", "health_beauty", "computers_accessories",
            "sports_leisure", "furniture_decor", "housewares",
            "telephony", "watches_gifts", "garden_tools", "toys",
        ],
        "order_count": [12000, 9800, 8700, 7600, 6500, 5400, 4300, 3200, 2100, 1800],
    })

    print("[1] 测试 word_col+freq_col 模式...")
    result = render_wordcloud(
        df=df,
        text_col=None,
        word_col="product_category",
        freq_col="order_count",
        title="2017年品类订单量词云",
        colormap="Blues",
        max_words=50,
        language="en",
    )

    assert isinstance(result, bytes), f"Expected bytes, got {type(result)}"
    assert len(result) > 1000, f"PNG too small ({len(result)} bytes)"
    print(f"  PASS: returned {len(result):,} bytes PNG")
    return result


def test_text_col_mode():
    """text_col mode: raw text tokenized and counted."""
    df = pd.DataFrame({
        "review_comment": [
            "product arrived quickly and was well packaged very happy",
            "the quality is excellent delivery was fast and on time",
            "great product fast delivery excellent quality happy",
            "delivery on time product quality is very good",
            "quick delivery good packaging product quality excellent",
        ]
    })

    print("[2] Testing text_col mode (English)...")
    result = render_wordcloud(
        df=df,
        text_col="review_comment",
        word_col=None,
        freq_col=None,
        title="Customer Review Wordcloud",
        colormap="viridis",
        max_words=30,
        language="en",
    )

    assert isinstance(result, bytes), f"Expected bytes, got {type(result)}"
    assert len(result) > 1000, f"PNG too small ({len(result)} bytes)"
    print(f"  PASS: returned {len(result):,} bytes PNG")
    return result


def test_save_sample(png_bytes: bytes, filename: str = "sample_wordcloud.png"):
    """Save PNG to disk for visual inspection."""
    out_path = os.path.join(os.path.dirname(__file__), filename)
    with open(out_path, "wb") as f:
        f.write(png_bytes)
    print(f"  Saved: {out_path}")


if __name__ == "__main__":
    print("=" * 50)
    print("Wordcloud Render Test")
    print("=" * 50)

    try:
        png1 = test_word_freq_mode()
        test_save_sample(png1, "test_wordcloud_freq.png")

        png2 = test_text_col_mode()
        test_save_sample(png2, "test_wordcloud_text.png")

        print("\nAll tests passed!")

    except ImportError as e:
        print(f"\nMissing library: {e}")
        print("Run: pip install wordcloud matplotlib")
        sys.exit(1)

    except Exception as e:
        import traceback
        print(f"\nTest failed: {e}")
        traceback.print_exc()
        sys.exit(1)
