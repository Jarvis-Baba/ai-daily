# 项目状态 (STATE.md)
> 唯一真相来源（当前状态）。只保留"现在在哪"，不堆历史、不放知识。

## 元信息
- 最近更新时间：2026-06-09
- 当前阶段：稳定运行 + 日常消费验证

## 续跑标记（接手第一眼看这里）
- 下一步：让 systemd timer 每天自动跑，早上看 summary.txt
- 从哪里继续：`./run.sh` 或 systemd timer 触发
- 接手前注意：
  - 配置文件 `config.yaml` 含 API key，不在版本控制中
  - `daily_pipeline.py` / `daily-pipeline.py` 是 run.sh 调用的 cron 入口，非死代码
  - 输出写入 `output/` 并复制到 `E:\Jarvis\Outputs\<date>_AI日报\`

## 运行概览
- 累计产出：9 份 morning 简报（2026-05-31 ~ 2026-06-08）
- 触发方式：systemd timer → run.sh → main.py → daily_pipeline.py
- 输出位置：`output/` → 自动同步到 `E:\Jarvis\Outputs\`

## 当前待办
### P0
- 无

### P1
- 决定三个游离文件的去向（daily_pipeline.py / daily-pipeline.py / content-bridge.py）
- 补全 retry 异常类型（openai SDK 异常类）

### P2
- 校准权重解冻（当前 0.0，等手动反馈数据积累后开启）
- 跑满 30 天后评估 Editorial v2 discard 逻辑

## 当前阻塞
- 无

## 已完成（只列里程碑，细节去 CHANGELOG）
- 2026-06-09：审查报告修复（渲染循环 6 类、DummyAdapter 属性、visual_plan 文件名）+ summary.txt 消费端反馈
- 2026-06-03~04：Ontology v2、四段 Yield 链、EDITORIAL-ABI v1.0、EVIDENCE-ABI v1.0
- 2026-06-02：Content IR v1.0
- 2026-05~06：DESIGN v2.1（Alpha 重定义、评分模型乘法→加权加法、Action Framework 三级、Counter Signal、Theme Memory）
