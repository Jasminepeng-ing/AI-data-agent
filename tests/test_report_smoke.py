"""
冒烟测试：markdown_to_word / markdown_to_pdf 基础渲染
使用最小 Mock 数据，不读取原始数据集。
"""
import sys
import os
import struct
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from report_builder import markdown_to_word, markdown_to_pdf


def _tiny_png() -> bytes:
    """生成一张 2×2 像素的合法 PNG bytes（不依赖 Pillow）。"""
    def chunk(tag: bytes, data: bytes) -> bytes:
        c = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', c)

    ihdr = struct.pack('>IIBBBBB', 2, 2, 8, 2, 0, 0, 0)
    raw  = b'\x00\xff\x00\x00' * 2 + b'\x00\x00\xff\x00' * 2
    idat = zlib.compress(raw)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')


# ── 测试用 Markdown（包含两种图表触发格式）────────────────────────────────────
SAMPLE_MD = """\
# 测试报告

## 一、数据概览

这是第一段正文，包含**加粗**文字和普通内容。

### 图表1：各类型用户数量分布

- 解读要点一：流失风险用户占比最高。
- 解读要点二：新用户与一般发展用户数量接近。

## 二、消费贡献分析

第二段正文，描述消费贡献情况。

图表2:各类型用户消费金额贡献

![图表2:各类型用户消费金额贡献]()

图表解读:

- 消费贡献曲线与用户数量曲线完全相反。
- 重要保持用户贡献了高比例的营收。

## 三、结论

#### 重要价值客户

结论段落，包含四级标题测试（emoji 已被过滤：🏆 → 空）。
"""

CAPTIONS  = ['各类型用户数量分布', '各类型用户消费金额贡献']
PNG_BYTES = [_tiny_png(), _tiny_png()]
TITLE     = '冒烟测试报告'


def test_word_basic():
    result = markdown_to_word(SAMPLE_MD, TITLE, CAPTIONS, PNG_BYTES)
    assert isinstance(result, bytes) and len(result) > 0, "Word 输出为空"
    # docx 是 ZIP 格式，以 PK 开头
    assert result[:2] == b'PK', f"Word 文件头不正确: {result[:4]}"
    print(f"[PASS] markdown_to_word  size={len(result):,} bytes")


def test_pdf_basic():
    result = markdown_to_pdf(SAMPLE_MD, TITLE,
                             chart_figures=[], chart_captions=CAPTIONS,
                             chart_png_bytes=PNG_BYTES)
    assert isinstance(result, bytes) and len(result) > 0, "PDF 输出为空"
    assert result[:4] == b'%PDF', f"PDF 文件头不正确: {result[:4]}"
    print(f"[PASS] markdown_to_pdf   size={len(result):,} bytes")


if __name__ == '__main__':
    print("=== report_builder 冒烟测试 ===")
    test_word_basic()
    test_pdf_basic()
    print("=== 全部通过 ===")
