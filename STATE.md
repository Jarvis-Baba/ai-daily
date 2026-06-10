# 项目状态 (STATE.md)
> 唯一真相来源（当前状态）。只保留"现在在哪"，不堆历史、不放知识。

## 元信息
- 最近更新时间：2026-06-10
- 当前阶段：审查修复轮五步全闭环，等待 2026-06-11 早间运行的最终动态验证

## 续跑标记（接手第一眼看这里）
- 下一步：查 2026-06-11 07:02 systemd 运行结果，三点验证——
  ① E 盘 `2026-06-11_AI日报` 应为仅当天增量、run.sh 退出码 0（新 run.sh 在 systemd 环境首跑）
  ② 遥测文件应为 `structural_fingerprint_20260611.json` / `20260611.jsonl`（本地日期命名首次实战，旧代码会错写成 20260610）
  ③ 简报正常生成
- 从哪里继续：本轮诊断见 REVIEW-2026-06-10.md，执行记录与唯一待办清单见 PLAN.md
- 接手前注意：
  - config.yaml **在版本控制中**，API key 经 `${DEEPSEEK_API_KEY}` 占位由 .env 注入（.env 不入库、权限 600）
  - 管线唯一入口链：systemd timer `ai-daily.timer`（用户级，07:00 CST + ≤15min 抖动）→ run.sh → src/main.py → daily_pipeline.py（连字符版 daily-pipeline.py 已删；ai-daily-l0.timer 已停用，见 DECISIONS.md）
  - Theme Memory 在项目根 `.theme-memory.json`（gitignored）
  - E 盘交付自 2026-06-10 起为仅当天增量；历史膨胀文件夹清理挂 PLAN.md watchlist

## 运行概览
- 简报产出：2026-05-30 ~ 2026-06-10 共 12 份（morning-{date}.md + .ir.json，06-09 起含 summary-{date}.txt）
- 测试：pytest 默认 179 通过 / 0 失败（2 个真实网络测试标记 integration 默认排除，`pytest -m integration` 显式跑）
- 测试不变量（2026-06-10 md5 实证）：pytest 对真实工作区零写入

## 当前待办
唯一待办清单 = PLAN.md 的 Watchlist，本文件不重复维护。
### P0
- 2026-06-11 早间三点验证（见续跑标记）
### P1/P2
- 见 PLAN.md Watchlist

## 当前阻塞
- 无

## 已完成（只列里程碑，细节去 CHANGELOG）
- 2026-06-10：审查修复轮五步闭环（REVIEW-2026-06-10.md + PLAN.md）——现状固化 b6a15a4 / E 盘增量交付 + run.sh 错误处理 36fbbfb / 测试套件修复 f11a670 / 死代码清理 e5bc5cd + 遥测日期对齐 f37571e / checkpoint 污染修复 8a29111 + 文档对齐
- 2026-06-09：审查修复（渲染循环 6 类、DummyAdapter 属性、visual_plan 文件名）+ summary.txt 消费端反馈
- 2026-06-03~04：Ontology v2、四段 Yield 链、EDITORIAL-ABI v1.0、EVIDENCE-ABI v1.0
- 2026-06-02：Content IR v1.0
- 2026-05~06：DESIGN v2.1（Alpha 重定义、加权加法评分、Action Framework 三级、Counter Signal、Theme Memory）
