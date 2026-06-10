# 修复计划（基于 REVIEW-2026-06-10.md）

> 执行模式：**逐步授权**。每步一个明确边界，完成并经用户确认后才进入下一步。
> 不得一次执行多步。每步完成后更新本文件的状态标记。
> 核心顺序逻辑：先建回滚点 → 再修影响生产的 → 恢复测试保护 → 清理 → 最后统一对齐文档。

## 第 1 步：git 固化现状 ✅（2026-06-10 执行）

- 落盘 REVIEW-2026-06-10.md（审查报告）+ PLAN.md（本文件）
- commit 全部已修改和未跟踪文件（6 修改 + 约 20 未跟踪，含 3 个生产 Stage）
- 停用 ai-daily-l0.timer（stop + disable，不删单元文件），DECISIONS.md 补记录
- commit message 注明"审查前现状固化，不含任何行为变更"

## 第 2 步：修两个影响每日生产的问题 ⬜（待授权）

- E 盘平方膨胀：改为每个日期文件夹只放**当天增量**，历史不重复复制（用户已裁决交付形态）
- run.sh 假错误处理：set -e 下 EXIT_CODE/PIPELINE_EXIT 捕获失效、失败路径不执行交付检查
- **验收：修完手动触发一次完整运行**，确认行为正确。不得只做静态修改就报告完成。

## 第 3 步：修 6 个失败测试，恢复回归保护 ⬜（待授权）

- 4 个日期硬编码（20260603）改动态日期
- 1 个 Stage 数断言（10 → 与 build_pipeline 实际对齐）
- 1 个真实网络依赖测试（test_real_url_capture）改 mock 或标记
- 放在清死代码之前：先让套件变绿，删除时才有保护网

## 第 4 步：清死代码 + 杂项 ⬜（待授权）

- daily-pipeline.py（连字符版，用户已裁决死代码）
- src/scheduler.py + tests/test_scheduler.py
- requirements.txt 移除 pydantic
- UTC 日期错位（structural_telemetry 与 report_date 对齐）
- outputs/ 目录去留
- **每删一项跑一次测试**

## 第 5 步：一次性更新文档 ⬜（待授权）

- STATE.md 全部漂移修正（至少 4 处错误，含"连字符版非死代码"的错误标注）
- PROJECT.md：Theme Memory 实际路径、docs/ 与根目录 spec 位置、config.yaml 版本控制状态
- PROJECT.md 第 6 节追加硬规则：**每次会话结束前 commit + 跑测试 + 同步 STATE**
- 中途各步不改文档，避免反复漂移

## Watchlist（挂起，不在本轮修复范围）

- **config.yaml 的 18 个固定 artifact URL**（06-04 一次性引入，从未修改）：
  等用户明确 L0 的观测意图——固定观测集（观察同批页面随时间变化）还是每日新鲜捕获——再决定去留。不影响生产正确性，只影响 L0 数据新鲜度。
- 校准权重解冻（原 STATE P2，等手动反馈数据）
- Editorial v2 discard 逻辑评估（跑满 30 天后）
- retry 补 openai SDK 异常类型（原 STATE P1）

## 歧义裁决记录（2026-06-10）

1. 双 timer → 遗留，stop + disable（第 1 步执行，DECISIONS.md 有记录）
2. 18 个 URL → 挂起，入上方 watchlist
3. E 盘交付 → 每日文件夹只放当天增量（第 2 步实施）
4. 连字符版 → 死代码（第 4 步删除）
5. 跨 skill snapshots 写入 → 保留耦合，DECISIONS.md 记录风险
