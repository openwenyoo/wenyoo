"""Validation, semantic review, and isolated author playtests for unsaved editor data."""
import asyncio

from fastapi import HTTPException
from pydantic import BaseModel, Field

from src.core.story_playtester import playtest_story
from src.core.story_validation import validate_story_data
from src.core.story_versions import story_diff


class StoryCheck(BaseModel):
    story: dict


class StoryComparison(BaseModel):
    before: dict
    after: dict


class PlaytestRequest(StoryCheck):
    max_steps: int = Field(default=8, ge=1, le=30)
    max_depth: int = Field(default=4, ge=1, le=10)
    commands: list[str] = Field(default_factory=list, max_length=10)


def register_story_quality_routes(app, game_kernel):
    @app.post("/api/story-quality/validate")
    async def validate(request: StoryCheck):
        issues = validate_story_data(request.story)
        return {"issues": issues, "valid": not any(i["severity"] == "error" for i in issues)}

    @app.post("/api/story-quality/diff")
    async def compare(request: StoryComparison):
        return story_diff(request.before, request.after)

    @app.post("/api/story-quality/playtest")
    async def playtest(request: PlaytestRequest):
        issues = validate_story_data(request.story)
        if any(i["severity"] == "error" for i in issues):
            return {"status": "invalid", "findings": issues, "steps": [], "visited_nodes": [],
                    "ending_nodes": [], "unvisited_nodes": list(request.story.get("nodes", {})), "limited": False}
        if not game_kernel.llm_provider:
            raise HTTPException(503, "Configure an LLM provider to run the automated playtester.")
        if any(not c.strip() or len(c) > 1000 for c in request.commands):
            raise HTTPException(422, "Sample commands must contain 1–1000 characters.")
        try:
            return await asyncio.wait_for(playtest_story(
                request.story, game_kernel.llm_provider, max_steps=request.max_steps,
                max_depth=request.max_depth, commands=request.commands,
            ), timeout=180)
        except asyncio.TimeoutError:
            raise HTTPException(408, "Playtest timed out. Reduce the turn budget and retry.")
