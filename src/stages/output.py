import logging
import os
from datetime import datetime
from src.pipeline.stage import PipelineContext
from src.models.article import Brief

logger = logging.getLogger(__name__)

# DeepSeek pricing (RMB per 1M tokens)
DEEPSEEK_INPUT_PRICE = 2.0   # ¥/1M prompt tokens
DEEPSEEK_OUTPUT_PRICE = 8.0  # ¥/1M completion tokens


class OutputStage:
    def process(self, ctx: PipelineContext) -> PipelineContext:
        brief: Brief = ctx.get("brief")
        output_dir: str = ctx.get("output_dir", "./output")
        template: str = ctx.get("output_template", "# AI 早报 — {date}\n\n{items}")

        os.makedirs(output_dir, exist_ok=True)

        date_str = brief.date.strftime("%Y-%m-%d")
        items_md = self._render_items(brief)
        cost_md = self._render_cost(ctx)
        md_content = template.format(
            date=date_str,
            items=items_md,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            cost=cost_md,
        )

        filename = f"morning-{date_str}.md"
        path = os.path.join(output_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(md_content)

        logger.info("Brief written to %s (%d items)", path, len(brief.items))
        ctx.set("output_path", path)
        return ctx

    def _render_items(self, brief: Brief) -> str:
        if not brief.items:
            return "_No articles today._"

        lines = []
        for item in brief.items:
            lines.append(
                f"### [{item.title}]({item.link})\n"
                f"**{item.source}** · 评分 {item.score}/10\n\n"
                f"{item.digest}\n"
            )
        return "\n".join(lines)

    def _render_cost(self, ctx: PipelineContext) -> str:
        adapter = ctx.get("llm_adapter")
        if adapter is None or adapter.calls == 0:
            return ""

        cost = (
            adapter.prompt_tokens / 1_000_000 * DEEPSEEK_INPUT_PRICE
            + adapter.completion_tokens / 1_000_000 * DEEPSEEK_OUTPUT_PRICE
        )
        return (
            f"\n---\n"
            f"> API 用量：{adapter.calls} 次调用 | "
            f"输入 {adapter.prompt_tokens:,} tokens | "
            f"输出 {adapter.completion_tokens:,} tokens | "
            f"预估费用 ¥{cost:.4f}\n"
        )
