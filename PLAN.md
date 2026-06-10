# 修复计划（基于 REVIEW-2026-06-10.md）

> 执行模式：**逐步授权**。每步一个明确边界，完成并经用户确认后才进入下一步。
> 不得一次执行多步。每步完成后更新本文件的状态标记。
> 核心顺序逻辑：先建回滚点 → 再修影响生产的 → 恢复测试保护 → 清理 → 最后统一对齐文档。

## 第 1 步：git 固化现状 ✅（2026-06-10 执行）

- 落盘 REVIEW-2026-06-10.md（审查报告）+ PLAN.md（本文件）
- commit 全部已修改和未跟踪文件（6 修改 + 约 20 未跟踪，含 3 个生产 Stage）
- 停用 ai-daily-l0.timer（stop + disable，不删单元文件），DECISIONS.md 补记录
- commit message 注明"审查前现状固化，不含任何行为变更"

## 第 2 步：修两个影响每日生产的问题 ✅（2026-06-10 执行）

- E 盘交付改为仅当天增量：morning.md / .ir.json / summary.txt + articles/{date}/ + visual-{date}/ + daily-summaries/daily-{date}.json，逐项写入运行日志
- run.sh 错误处理重写：移除 set -e，改显式退出码检查 + fail() 统一失败出口（FATAL 日志 + logs/FAILED-{date}.flag 标记 + 非零退出）
  - 实现选择：不用 trap ERR——bash 在条件语境中会静默禁用 ERR trap；显式检查使"失败路径必然执行合同检查"成为结构保证而非运行时巧合
  - 设计取舍：main.py 失败 → 不交付、立即 fail；daily_pipeline 失败 → 先交付当天简报、再以非零退出（视觉管线故障不阻断简报交付，但保持可观察）
  - 测试缝：AI_DAILY_E_BASE 环境变量可覆盖交付基目录（仅测试用）；基目录必须预先存在，兼作 E 盘挂载检查
- 验证（均已执行，证据在 logs/run-2026-06-10.log 的 [TEST] 括号段内）：
  - 失败注入（临时重命名 config.yaml）：FATAL 日志 + flag 文件 + 退出码 1，无交付目录创建，config 已恢复（md5 与 HEAD 一致）
  - 成功路径 ×2（--resume）：隔离 /tmp 基目录运行证明交付仅含当天产物、零历史混入；真实 E 盘运行证明生产路径退出码 0

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

- **已膨胀的历史 E 盘文件夹**（E:\Jarvis\Outputs\2026-05-30~06-10_AI日报，每个含截至当日的全量历史副本）：
  删除 Windows 侧数据不可逆，本轮不动。由用户手动清理或单独授权。

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
