# ai-daily

AI 早报生成器。多 RSS 源抓取 → LLM 筛选评分 → LLM 摘要 → Markdown 输出。

## 快速开始

```bash
pip install -r requirements.txt
python3 src/main.py -c config.yaml
```

## 配置

编辑 `config.yaml`：

- `feeds` — RSS 源列表，`enabled: false` 可临时停用
- `llm.provider` — `dummy`（调试）| `openai`（生产）
- `filter.top_n` — 最终入选文章数
- `filter.min_score` — 最低评分阈值（1-10）
- `output.dir` — 早报输出目录

## 项目结构

```
src/
├── main.py           # 入口
├── models/           # 数据模型
├── config/           # 配置加载
├── pipeline/         # 管线引擎
├── adapters/         # RSS/LLM 适配器
└── stages/           # Fetch → Filter → Summarize → Output
```

## 运行测试

```bash
python3 -m pytest tests/ -v
```
