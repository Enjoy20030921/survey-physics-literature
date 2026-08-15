# 系统性物理文献调研

[English](README.md) | [简体中文](README.zh-CN.md)

这是一个面向 Codex 的可审计、可增量更新的物理文献调研 Skill，重点服务于高能物理和引力物理，尤其是 `hep-*` 与 `gr-qc` 方向。

它将中英文意图识别、可复现元数据检索、全文证据追踪、增量更新以及中英文 LaTeX 报告整合为一套工作流。报告采用自适应结构：章节组织由研究问题和证据决定，而不是套用固定模板。

## 主要特点

- 中文和英文的等价调研请求均可触发。
- 支持新建综述、从种子论文扩展引用网络、更新已有综述。
- 以 arXiv 和 INSPIRE 为主要信息源，并通过 Crossref 补全 DOI 与期刊元数据。
- 使用仅依赖 Python 标准库的确定性脚本完成检索、缓存、解析、去重、导出与校验。
- 优先按规范化 DOI、去版本 arXiv ID 和 INSPIRE recid 去重，再使用标题-作者-年份相似度。
- 严格区分标题摘要筛选与全文证据提取。
- 实质性科学结论必须对应章节、页码、公式、图或表等精确定位信息。
- 增量更新时保留稳定的记录 ID、证据 ID、筛选决定和 BibTeX 键。
- 可生成中文、英文或两份证据等价的独立双语报告。
- 环境具备 XeLaTeX 和 BibTeX 时可直接编译 PDF。
- 不预设统一章节，报告层级根据具体调研自适应生成。

本方法受 PRISMA 思路启发并强调可审计性，但不宣称正式符合 PRISMA 2020。

## 适用场景

适用于以下请求：

- 系统性物理文献调研或文献综述；
- 梳理研究脉络、进展和领域版图；
- 查找高能物理或 `gr-qc` 相关论文；
- 从一篇或多篇种子论文扩展引用网络；
- 对已有综述目录进行增量更新；
- 比较共识、矛盾、关键假设、局限和研究空白。

单独的物理计算或单篇论文摘要不应触发本 Skill，除非用户明确要求扩展为更广泛的文献调研。

## 安装

本仓库中的 Skill 源目录为：

```text
.codex/skills/survey-physics-literature/
```

OpenAI 当前文档将 `.agents/skills/` 列为独立 Codex Skill 的本地发现目录。请把本仓库中的 Skill 目录复制到目标项目：

```text
<目标项目>/.agents/skills/survey-physics-literature/
```

克隆本仓库后，可在类 Unix 环境中执行：

```bash
mkdir -p <目标项目>/.agents/skills
cp -R survey-physics-literature/.codex/skills/survey-physics-literature \
  <目标项目>/.agents/skills/
```

PowerShell：

```powershell
New-Item -ItemType Directory -Force <目标项目>\.agents\skills
Copy-Item -Recurse survey-physics-literature\.codex\skills\survey-physics-literature `
  <目标项目>\.agents\skills\survey-physics-literature
```

Codex 会自动检测受支持目录中的 Skill 变更。如果没有出现，请重启 Codex。最新的发现路径和调用方式见 [OpenAI Build skills 文档](https://learn.chatgpt.com/docs/build-skills)。

## 调用方式

显式调用：

```text
$survey-physics-literature
```

当请求与 `SKILL.md` 中的中英文描述匹配时，Codex 也可以隐式调用。

中文示例：

```text
请使用 $survey-physics-literature 调研黑洞信息问题中的岛公式。
研究问题：岛公式在半经典引力中解决 Page curve 问题的证据、假设和主要争议是什么？
arXiv 分类：hep-th, gr-qc
时间范围：all-time
纳入：原创论文、综述、讲义和相关会议论文
排除：只在摘要中提及 island、但正文没有实质讨论的文献
报告语言：中文
```

英文示例：

```text
Use $survey-physics-literature to review the island formula in the black-hole information problem.
Research question: What evidence, assumptions, and major disputes surround the island formula and the Page curve in semiclassical gravity?
arXiv categories: hep-th, gr-qc
Date range: all-time
Include: original papers, reviews, lectures, and relevant proceedings
Exclude: papers that mention islands only in the abstract without substantive full-text treatment
Report language: English
```

## 调研设置

| 设置 | 必填 | 说明 |
| --- | --- | --- |
| 研究问题 | 是 | 聚焦且可回答的物理问题。 |
| arXiv 分类 | 是 | 一个或多个分类，例如 `hep-th`、`hep-ph`、`gr-qc`。 |
| 时间范围 | 是 | 明确起止时间或 `all-time`。 |
| 纳入标准 | 是 | 可纳入的文献类型、物理体系、方法与范围。 |
| 排除标准 | 是 | 排除相关文献的明确理由。 |
| 种子论文标识符 | 否 | 用于引用扩展的 arXiv ID、DOI 或 INSPIRE recid。 |
| 用户检索词 | 否 | 概念、人物、观测量或同义术语。 |
| 已有综述目录 | 否 | 用于保留稳定标识符的增量更新。 |
| `report_language` | 否 | `zh`、`en` 或 `bilingual`；未指定时询问一次，无回答则回退为 `bilingual`。 |

支持 `中文`、`英文`、`中英双语`、`Chinese`、`English`、`bilingual` 等自然语言写法，规范化后的值记录在 `protocol.json` 中。

## 工作流

```mermaid
flowchart LR
    A[解析中英文意图] --> B[冻结调研协议]
    B --> C[扩展概念与检索式]
    C --> D[检索 arXiv 与 INSPIRE]
    D --> E[使用 Crossref 补全元数据]
    E --> F[规范化与去重]
    F --> G[标题摘要筛选]
    G --> H[获取合法全文]
    H --> I[全文筛选与引用扩展]
    I --> J[建立证据矩阵]
    J --> K[自适应综合]
    K --> L[审计引用并编译所需报告]
```

摘要只用于筛选。报告中的实质性结论必须映射到全文证据记录和精确定位信息。

## 输出文件

每次调研保存在 `literature-reviews/<topic-slug>/`，并包含：

```text
references.bib
protocol.json
records.jsonl
screening.csv
evidence.csv
search_runs.jsonl
update_summary.md
fulltext/
  manifest.jsonl
```

语言相关输出严格对应所选模式：

| 模式 | 生成报告 |
| --- | --- |
| `zh` | `report_zh.tex`、`report_zh.pdf` |
| `en` | `report_en.tex`、`report_en.pdf` |
| `bilingual` | 两套完整的 TeX/PDF 报告 |

切换语言模式时，过时的报告版本会被归档，避免把旧文件误认为当前结果。

## 自适应报告结构

Skill 不规定固定章节列表。它会在理解研究问题、证据聚类、目标读者和报告规模后，选择概念型、方法型、时间型、比较型、争议导向型或其他更合适的结构。

调研范围、检索来源、证据综合、分歧、不确定性、局限、引用和可审计性仍是必须覆盖的信息，但可以整合进正文、合并、重命名、放入附录，或保留在外部审计文件中。

检索摘要、筛选流程和纳入文献表是可选 LaTeX 片段，不是强制附录。

## 数据源与访问原则

- [arXiv API](https://info.arxiv.org/help/api/user-manual.html)：主要预印本来源。
- [INSPIRE REST API](https://github.com/inspirehep/rest-api-doc)：主要高能物理元数据与引用来源。
- [Crossref REST API](https://support.crossref.org/hc/en-us/articles/214320426-REST-API)：用于补全 DOI 与出版元数据。

检索层实现缓存、请求间隔、重试和来源级溯源。系统只下载合法可访问的全文，不绕过登录、付费墙或其他访问控制。

## 确定性命令行工具

脚本不会自行决定科学文献的纳入与排除，也不会替代模型或研究者撰写科学综合；它们负责让这些判断周围的数据操作可复现。

初始化调研：

```bash
python .codex/skills/survey-physics-literature/scripts/literature_pipeline.py init \
  literature-reviews/island-formula \
  --question "岛公式成立的主要证据和关键假设是什么？" \
  --categories hep-th gr-qc \
  --date-range all-time \
  --include "原创论文、综述、讲义和会议论文" \
  --exclude "只在摘要提及、正文无实质讨论的文献" \
  --language zh
```

在 `protocol.json` 中冻结精确检索式后：

```bash
python .codex/skills/survey-physics-literature/scripts/literature_pipeline.py search literature-reviews/island-formula
python .codex/skills/survey-physics-literature/scripts/literature_pipeline.py download literature-reviews/island-formula
python .codex/skills/survey-physics-literature/scripts/literature_pipeline.py render-audit literature-reviews/island-formula
```

审计并编译：

```bash
python .codex/skills/survey-physics-literature/scripts/audit_review.py literature-reviews/island-formula --require-reports
python .codex/skills/survey-physics-literature/scripts/compile_reports.py literature-reviews/island-formula
python .codex/skills/survey-physics-literature/scripts/audit_review.py literature-reviews/island-formula --require-reports --require-pdfs
```

如果缺少 XeLaTeX 或 BibTeX，编译脚本会保留有效源文件并返回明确诊断，不会自动安装 TeX 发行版。

## 验证

运行离线回归测试：

```bash
python -B .codex/skills/survey-physics-literature/scripts/test_skill_scripts.py
```

测试覆盖语言规范化、中英文触发、arXiv 与 INSPIRE 解析、旧式 arXiv ID、合作组作者、Unicode、去重、缓存、HTTP 429 重试、条件化语言输出和审计失败。

本 Skill 还通过了官方 `quick_validate.py` 校验，以及代表性中英文报告的 XeLaTeX -> BibTeX -> XeLaTeX x2 编译测试。

## 仓库结构

```text
.codex/skills/survey-physics-literature/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── assets/
│   ├── report_en.tex
│   ├── report_zh.tex
│   └── review-macros.tex
├── references/
│   ├── data-contracts.md
│   ├── methodology.md
│   ├── reporting.md
│   └── source-guides.md
└── scripts/
    ├── audit_review.py
    ├── compile_reports.py
    ├── literature_pipeline.py
    └── test_skill_scripts.py
```

## 科学与运行边界

- 检索覆盖面可以很广，但无法保证发现所有相关文献。
- 元数据服务可能存在缺失、延迟或暂时不可用。
- 摘要不能作为实质性科学结论的充分证据。
- 全文获取取决于合法可访问性。
- 自动规范化和去重过程必须保持可审计、可复核。
- 最终综合仍需要领域判断；确定性脚本支持判断，但不能替代判断。

## 致谢

本 Skill 遵循 OpenAI 面向可复用工作流的渐进披露设计，并使用 arXiv、INSPIRE 和 Crossref 的官方接口获取文献元数据。
