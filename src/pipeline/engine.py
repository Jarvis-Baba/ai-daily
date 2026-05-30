from src.pipeline.stage import Stage, PipelineContext


class PipelineEngine:
    def __init__(self, stages: list[Stage]):
        self._stages = stages

    def run(self, ctx: PipelineContext) -> PipelineContext:
        for stage in self._stages:
            ctx = stage.process(ctx)
        return ctx
