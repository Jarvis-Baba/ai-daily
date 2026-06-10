# ai-daily — AI 行业每日简报生成器

多源抓取 → LLM 筛选评分 → 结构化合成为可行动决策简报，输出到微信公众号。

## 快速开始

```bash
./run.sh            # 完整运行（断点续跑：--resume）
python3 src/main.py -c config.yaml   # 直接调用主流程
```

## 输出结构

```
output/
├── morning-{date}.md        # Markdown 简报
├── morning-{date}.ir.json   # Content IR（结构化中间表示）
├── summary-{date}.txt       # 每日 3 行摘要（给人看的）
├── articles/{date}/         # V-Kernel 文章 + PNG
└── artifacts/{date}/        # 抓取原始数据
```

输出自动复制到 `E:\Jarvis\Outputs\{date}_AI日报\`。

## 项目结构

```
ai-daily/
├── src/           # 管线代码（13 Stage：L0Capture → … → Output）
│   ├── stages/    # 各处理阶段
│   ├── adapters/  # LLM 适配器
│   ├── models/    # 数据模型
│   └── pipeline/  # 管线框架
├── config.yaml    # RSS 源 + LLM 配置（不入版本控制）
├── docs/          # 设计文档、ABI Spec、Ontology
├── tests/         # pytest
└── run.sh         # systemd timer 入口
```

## 接手须知

- 先读 STATE.md 了解当前阶段和下一步
- 规则和架构见 PROJECT.md
- 关键决策及原因见 DECISIONS.md
- 历史变更见 CHANGELOG.md
