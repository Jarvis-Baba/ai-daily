import logging
import os
from datetime import datetime
from src.pipeline.stage import PipelineContext
from src.models.article import Brief

logger = logging.getLogger(__name__)


class OutputStage:
    def process(self, ctx: PipelineContext) -> PipelineContext:
        brief: Brief = ctx.get("brief")
        output_dir: str = ctx.get("output_dir", "./output")
        template: str = ctx.get("output_template", "# AI 早报 — {date}\n\n{items}")

        os.makedirs(output_dir, exist_ok=True)

        date_str = brief.date.strftime("%Y-%m-%d")
        items_md = self._render_items(brief)
        md_content = template.format(
            date=date_str,
            items=items_md,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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
