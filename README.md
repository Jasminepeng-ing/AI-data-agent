# AI Data Analysis Agent

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-red)
![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek-brightgreen)
![DuckDB](https://img.shields.io/badge/DB-DuckDB-yellow)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

**用自然语言提问，AI 自动完成数据查询、可视化分析、专业报告生成的全流程 Agent。**

> 一个由数据分析师亲手打造、面向分析师痛点的 AI 自动化分析工具。
> Demo：https://jasmine-data-aiagent.streamlit.app/

---

## 背景与动机 Background

作为一名工作了 3 年半的数据分析师，我每天的工作大量时间都花在：

- 重复编写相似的 SQL 查询
- 手动调整图表样式和布局
- 将数据结论整理成 Word/PPT 报告

这些步骤**技术门槛不高，却极其耗时**。与此同时，业务同学想自助查数据，却因为不懂 SQL 而频繁找分析师帮忙——双方都低效。

**我想验证一件事：AI 能不能替代这条流水线？**

于是我用 DeepSeek API 的 Function Calling 能力，配合 Streamlit 搭建了这个 Agent，从零构建了整个分析闭环。

---

## 它能解决什么问题 What Problem It Solves

| 场景 | 传统方式 | 使用本 Agent |
|------|----------|--------------|
| 业务同学想看某类数据 | 找分析师排期写 SQL | 直接用自然语言提问 |
| 出图需要调颜色/格式 | 手动改 Python/Excel | AI 自动选图表类型并生成 |
| 汇报需要出报告 | 手动整理 Word/PDF | 一键导出三种格式 |
| 有一份临时 Excel 要分析 | 导入数据库或用透视表 | 上传即可对话分析 |
| 指标下降了，原因是什么 | 人工逐维度拆解 | 自动多维度归因分析 |

---

## 功能亮点 Features

**1. 自然语言转 SQL**
直接用中文提问，Agent 自动生成 SQL、执行查询、返回结果，并在界面展示执行的 SQL 语句供审查。

**2. 智能可视化（11 种图表）**
- 柱状图、横向柱状图、折线图、面积图
- 饼图、环形图（超过 12 个类别自动降级并提示）
- 散点图、气泡图（支持三维数值关系展示）
- 热力图、组合双轴图
- 数据表格（含合计 / 统计行）

**3. 指标多维归因分析**
内置 `diagnose_metric` 工具，对任意指标按多个维度自动拆解，快速定位"为什么这个指标变了"。

**4. 一键生成专业报告**
同一份分析结果，支持导出三种格式：
- **Markdown**：对话框内直接预览
- **Word (.docx)**：带样式、页眉页脚，可直接编辑
- **PDF (.pdf)**：专业排版，适合对外输出

**5. 上传即分析**
将 Excel 或 CSV 拖入上传区，系统自动注册为可查询的数据视图，无需任何额外配置。

**6. 大查询安全拦截**
查询结果超过 10 万行时自动暂停，弹出确认框，防止意外拉取海量数据。

**7. SQL 出错自动修复**
查询失败时，Agent 读取报错信息，自动调整 SQL 重试，无需人工介入。

**8. 内置真实数据集**
预置巴西电商 Olist 数据（9 张表、15 万+ 行），包括订单、用户、商品、评论、支付等，启动即可体验完整分析流程。

---

## 技术架构 Architecture

```
用户输入（自然语言）
        │
        ▼
  [Streamlit UI]  ←────────────── 侧边栏：表管理 / 文件上传 / SQL 历史
        │
        ▼
  [Agent Loop]  (agent.py)
  DeepSeek Function Calling
        │
        ├──► query_database    → DuckDB SQL 执行 → 结果缓存
        ├──► make_chart        → Plotly / WordCloud 图表生成
        ├──► analyze_dataframe → 统计描述 / 相关性 / 分组分析
        ├──► diagnose_metric   → 多维度指标拆解
        └──► generate_report   → Word / PDF / Markdown 报告输出
```

**技术栈一览**

| 模块 | 技术选型 |
|------|----------|
| LLM | DeepSeek API（deepseek-chat，Function Calling） |
| 前端 UI | Streamlit |
| 数据库 | DuckDB（进程内 SQL，无需服务端） |
| 交互式图表 | Plotly |
| 词云 | WordCloud + jieba |
| Word 报告 | python-docx |
| PDF 报告 | WeasyPrint |
| 数据处理 | pandas + NumPy |

---

## 快速上手 Quick Start

### 环境要求
- Python 3.10+
- DeepSeek API Key（[申请地址](https://platform.deepseek.com/)）
- Windows / macOS / Linux 均可

### 安装步骤

```bash
# 1. 克隆项目
git clone https://github.com/your-username/AI-data-agent.git
cd AI-data-agent

# 2. 创建虚拟环境并激活
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置 API Key
# 在项目根目录创建 .env 文件，写入：
# DEEPSEEK_API_KEY=sk-your-key-here

# 5. 初始化内置数据库
python scripts/init_db.py

# 6. 启动应用
streamlit run src/app.py
```

浏览器访问 `http://localhost:8501`，即可开始使用。

---

## 使用示例 Example Usage

以下是一些可以直接输入的问题示例（基于内置 Olist 数据集）：

```
# 数据查询
每个州的订单量是多少？用条形图展示。

# 趋势分析
2017年到2018年，每月订单量的变化趋势如何？

# 用户分析
哪些产品类别的评分最低？找出评分低于3分的类别。

# 指标归因
近3个月订单量下降了，请从州、品类、支付方式三个维度分析原因。

# 报告生成
基于以上分析，生成一份 PDF 报告。

# 自定义数据
（上传 Excel 后）帮我分析这份销售数据，找出增长最快的区域。
```

---

## 目录结构 Project Structure

```
AI-data-agent/
├── src/
│   ├── app.py            # Streamlit 主界面
│   ├── agent.py          # Agent 循环（Function Calling）
│   ├── tools.py          # 工具函数实现
│   ├── data_source.py    # 数据访问层（DuckDB 封装）
│   ├── report_builder.py # Word / PDF 报告生成
│   ├── chart_utils.py    # 词云渲染
│   ├── validators.py     # 图表类型验证与降级
│   ├── prompts.py        # LLM 系统提示词
│   └── config.py         # 配置常量
├── scripts/
│   └── init_db.py        # 数据库初始化脚本
├── data/
│   ├── raw/              # Olist 原始 CSV 文件（9 张表）
│   └── olist.db          # DuckDB 数据库文件
├── assets/
│   └── fonts/            # 词云中文字体
├── tests/                # 单元测试
├── .env                  # API Key（不提交 Git）
├── requirements.txt
└── README.md
```

---

## 未来规划 Roadmap

- [ ] 支持接入 MySQL / PostgreSQL 外部数据源
- [ ] 支持多数据集关联查询（Join 向导）
- [ ] 图表样式自定义（主题色、字体）
- [ ] 分析历史记录保存与回溯
- [ ] 支持 OpenAI / 通义千问等其他 LLM 接入

---

## 关于作者 About

这个项目是我作为**个人学习探索项目**独立完成的。  
**目标**：验证 AI Agent 在数据分析场景中的落地可行性，并积累全栈 AI 应用的开发经验。

如果你也是数据分析从业者，或者对 AI + BI 方向感兴趣，欢迎 Star、Fork 或提 Issue 交流。

---

