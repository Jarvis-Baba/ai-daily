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
- 待闭环验证点：2026-06-11 07:02 systemd 环境首跑新 run.sh（环境变量/PATH/用户上下文与手动 shell 不同，是手动验证覆盖不到的最后一块）——确认 2026-06-11_AI日报 为干净增量且退出码 0
- 验证（均已执行，证据在 logs/run-2026-06-10.log 的 [TEST] 括号段内）：
  - 失败注入（临时重命名 config.yaml）：FATAL 日志 + flag 文件 + 退出码 1，无交付目录创建，config 已恢复（md5 与 HEAD 一致）
  - 成功路径 ×2（--resume）：隔离 /tmp 基目录运行证明交付仅含当天产物、零历史混入；真实 E 盘运行证明生产路径退出码 0

## 第 3 步：修 6 个失败测试，恢复回归保护 ✅（2026-06-10 执行）

- 4 个日期硬编码改为动态镜像生产逻辑（datetime.now(timezone.utc)，调用前后双采样防 UTC 午夜跨越）
- test_build_batches 改为从实现常量（_BATCH_SIZE/_BATCH_CHAR_LIMIT）推导期望 + 不变量断言（无丢失/无重排/守上限）
- Stage 断言改为完整有序类名列表（变更探测器）：纯计数放过 Stage 替换、动态读取管线定义则同义反复，列表两者皆防；注释要求改管线必须有意识更新此处
- 真实网络测试 ×2（test_real_url_capture + test_idempotent_skip，后者虽未失败但同样打网）标记 @pytest.mark.integration，新建 pytest.ini 默认排除（pytest -m integration 显式运行）
- 红线遵守：src/ 零改动；6 个失败均确认为测试自身问题，未发现生产 bug

## 第 4 步：清死代码 + 杂项 ✅（2026-06-10 执行）

- 已删（每删一项跑一次 pytest，6 次全绿）：daily-pipeline.py、src/scheduler.py +
  tests/test_scheduler.py、requirements.txt 的 pydantic、outputs/、
  media/f771d4f56ad4dbaa.png（integration 测试残留）、EVIDENCE-PACKAGE-001/（裁决1，
  git 历史 b6a15a4 可找回）
- 遥测日期对齐（单独 commit，生产代码变更）：UTC 命名家族共 4 处——
  structural_telemetry.py（指纹文件名）、telemetry.py（JSONL 文件名）、
  telemetry_analyzer.py（analyze_day 默认日期 + analyze_range 基准）——统一改本地日期，
  与 report_date（main.py 的 date.today()）对齐；记录内 ISO 时间戳保持 UTC（时间戳非 join 键）
  - 范围边界：artifact_capture.py / evidence_compiler.py 的 UTC 日期是 Artifact/Evidence
    **ID 命名空间**而非 dashboard join 键，未动（改动会切换 ID 语义并在当日去重上制造接缝），
    挂 watchlist 待裁决
  - dashboard 的 day-1 回退逻辑（load_data.ts）保留：对修复后的新文件自动失效为兼容
    旧文件的死分支，无害
  - 验证：冻结时钟模拟明早 06:30 CST（UTC 仍是前一天 22:30）→ 文件名取本地日期；
    --resume 全链路实跑一次确认落盘正常
- 已知过渡现象：structural_fingerprint_20260610.json 含今晚 20:08 验证运行的统计
  （该次因 checkpoint 被测试污染实际全量重跑，见 watchlist 新发现条目）；06-10 早间
  生产数据在 _20260609.json（旧 UTC 命名）。存量文件名按授权不改，接缝随明日运行自愈

## 第 5 步：一次性更新文档 ⬜（待授权）

- STATE.md 全部漂移修正（至少 4 处错误，含"连字符版非死代码"的错误标注）
- PROJECT.md：Theme Memory 实际路径、docs/ 与根目录 spec 位置、config.yaml 版本控制状态
- PROJECT.md 第 6 节追加硬规则：**每次会话结束前 commit + 跑测试 + 同步 STATE**
- 中途各步不改文档，避免反复漂移

## Watchlist（挂起，不在本轮修复范围）

- **已知未实测分支**：run.sh 三条失败路径中“E 盘可达但交付中途失败”（cp 失败 → fail）未注入验证；
  注入成本（模拟写入中途失败）高于风险，2026-06-10 验收时确认接受，留作已知项。
- **Artifact/Evidence ID 的 UTC 日期**（artifact_capture.py:189、evidence_compiler.py:245）：
  第 4 步遥测对齐时按"只对齐 join 键、不动业务 ID"划界未改。若也要统一为本地日期，
  需同步改第 3 步写的镜像测试，并接受切换日的当日去重接缝——待用户裁决是否做。
- **新发现：pytest 污染生产 checkpoint（2026-06-10 第 4 步验证中发现，修复待授权）**：
  tests/test_pipeline_engine.py 有三个测试跑引擎时未设 output_dir，引擎按默认值
  "./output" 把 checkpoint 写进真实输出目录——每跑一次 pytest，当日
  .checkpoint-{date}.json 即被改写为 ['AppendStage']（该文件的 dummy stage 名），
  其后任何 --resume 退化为全量重跑。今晚 20:08 遥测验证运行即被此污染（简报被 LLM
  重新生成并覆盖交付，含成本）。19:45/19:47 两次 resume 在 checkpoint 完好时正确
  全部跳过，证明 resume 跳过语义本身正常。修复为三处补 tmpdir 的小改动（纯测试），
  待授权。明日 07:02 生产运行不带 --resume，不受此影响。

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
