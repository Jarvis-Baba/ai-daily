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

## 第 5 步：顺手修复 + 扫描 + 文档统一对齐 ✅（2026-06-10 执行）

- A 顺手修复（commit 8a29111）：checkpoint 污染消除。授权点名 test_pipeline_engine.py
  三处；验收线"checkpoint 零改写"首轮 md5 对比仍 FAIL，溯源出第二个同类污染源
  test_metrics.py（5 个 engine.run 未设 output_dir），一并修复。实证：全量 pytest 前后
  checkpoint / .theme-memory.json / 当日简报 md5 三者一致，重复运行 PASS ×2
- B 只读扫描：默认路径风险面清点完毕，残余项（均为潜伏未触发）入下方 Watchlist
- C 文档对齐：STATE.md 全面重写（简报 12 份、config.yaml 在 VCS、theme-memory 在项目根、
  单入口链、五步摘要）；PROJECT.md 修 docs/ 与 spec 位置、Theme Memory 路径、§6 增会话
  硬纪律；README 修 config.yaml 描述；PLAN 即本文件

## 量化验收线（长期不变量，违反即回归）

1. pytest 默认运行 0 失败（当前 179 passed + 2 integration deselected）
2. 单测零真实网络访问（integration 标记隔离，`pytest -m integration` 显式跑）
3. 测试对真实工作区零写入（checkpoint / .theme-memory.json / 当日简报 md5 前后一致；2026-06-10 双重实证）

## Watchlist（唯一待办清单）

### P0 — 有明确时点
- ✅ 三点验证（2026-06-11 13:28 完成，用户裁决归档）：实际为 Persistent 补跑（WSL 在 07:00 离线，13:24 启动后 systemd 追赶触发——意外多验证了补跑分支）。① systemd 触发 exit 0，E 盘文件夹出生即干净（6 类当日产物、零历史混入）✅；② 文件名 20260611 正确，但 13:28 运行时 CST/UTC 同日期，今日实战无区分力——保留意见：实战级区分证据待 07:00-07:59 CST 窗口运行，单元级（冻结时钟）证据有效 ✅*；③ 简报存在、日期正确、结构完整 ✅

### P1/P2 — 等数据或等裁决
- 遥测修复的实战级区分验证（被动观察项）：等任意一天 07:00–07:59 CST 窗口内的真实运行，看日志时顺带确认遥测文件名为当日而非前一日。不专门安排，自然发生
- 早报时效性——观察至 2026-06-25：每日看日志时顺手记录实际触发时间（run log 首行时间戳即是）；准点率 <90% 或出现整日缺报（含补跑也未发生）再裁决方案。背景：07:00 timer 依赖 WSL 当时在线，2026-06-11 实况为 13:28 补跑（晚收报而非丢报）
- L0 观测意图裁决 → config.yaml 18 个固定 artifact URL 去留（06-04 一次性引入后零修改）
- Artifact/Evidence ID 的 UTC 日期是否统一为本地（artifact_capture.py / evidence_compiler.py）：改则需同步镜像测试并接受切换日去重接缝
- 测试默认路径残余风险（第 5 步 B 扫描，均潜伏未触发——全量 pytest 后 .theme-memory.json md5 不变为证）：
  - test_synthesize_stage.py 4 处 `SynthesizeStage(llm)` 未传 memory_path（默认项目根 .theme-memory.json）
  - test_evidence_compiler.py 3 处 `L1EvidenceStage(llm_adapter=...)` 未传 artifact_base_dir（默认 None → 落 config/约定目录；当前仅走空输入早退路径）
  - test_evidence_compiler.py 固定路径 /tmp/l1-test（不在工作区，但跨运行共享、无清理）
  - test_artifact_capture.py FakeConfig 默认 output_dir="."（当前仅 skip 路径使用，无写入）
  - 建议（待授权）：conftest 增加全局守卫 fixture，pytest 结束断言工作区关键文件未变
- 校准权重解冻（等手动反馈数据积累）
- Editorial v2 discard 逻辑评估（跑满 30 天后）
- retry 补全 openai SDK 异常类型

### 已接受的已知项
- run.sh 三条失败路径中"E 盘可达但交付中途失败"分支未注入验证（注入成本高于风险，2026-06-10 验收时接受）

## 歧义裁决记录（2026-06-10）

1. 双 timer → 遗留，stop + disable（第 1 步执行，DECISIONS.md 有记录）
2. 18 个 URL → 挂起，入上方 watchlist
3. E 盘交付 → 每日文件夹只放当天增量（第 2 步实施）
4. 连字符版 → 死代码（第 4 步删除）
5. 跨 skill snapshots 写入 → 保留耦合，DECISIONS.md 记录风险
