# 变更记录 (CHANGELOG.md)
> 历史进度流水，每完成一单元追加一行，最新在最上。可以很长 —— 它替 STATE 承载历史。

| 时间 | 完成的单元 | 产出/落点 | 备注 |
|---|---|---|---|
| 2026-06-10 | 修复 6 个失败测试，回归保护恢复 | tests/, pytest.ini | 日期硬编码改动态、Stage 断言改类名列表、2 个网络测试入 integration 分组；src/ 零改动 |
| 2026-06-10 | E 盘交付改为仅当天增量 + run.sh 错误处理重写 | run.sh | 失败注入 + 双成功路径验证通过；历史膨胀文件夹挂 PLAN.md watchlist |
| 2026-06-10 | 只读审查落盘 + 五步修复计划 | REVIEW-2026-06-10.md, PLAN.md | 全链路审查（静态+运行验证），逐步授权执行 |
| 2026-06-10 | 停用 ai-daily-l0.timer（遗留脚手架） | systemd user units | stop+disable 不删除；决策见 DECISIONS.md |
| 2026-06-10 | 审查前现状固化 commit | git | 6 修改文件 + 全部未跟踪文件，不含行为变更 |
| 2026-06-09 | 审查修复 #1：_render_event_ledger 补全 6 类型渲染 | src/stages/output.py | 此前 research_result/governance/ecosystem 静默丢失 |
| 2026-06-09 | 审查修复 #2：DummyAdapter 补 calls/prompt_tokens/completion_tokens | src/adapters/llm.py | dummy 模式不再 AttributeError |
| 2026-06-09 | 审查修复 #3：visual_plan.yaml → visual_plan.json | src/stages/article_compiler.py, article_composer.py | 文件名与格式对齐 |
| 2026-06-09 | summary.txt 消费端反馈 | src/stages/output.py | 每日 3 行摘要，随输出复制到 E 盘 |
| 2026-06-09 | Project OS 落盘：STATE.md / CHANGELOG.md / README.md | 项目根目录 | 从模板状态切换到运营状态 |
