"""Plan-based AI editing routes for the story editor.

This module provides endpoints for the two-phase AI editing approach:
1. Generate Plan: LLM creates a structured execution plan
2. Execute Plan: Plan is executed step-by-step with SSE streaming

This avoids the step-limit issue with direct tool calling.
"""

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Any, Dict, List, AsyncGenerator
import json
import logging
import asyncio
import re

from ..utils.plan_executor import (
    PlanExecutor,
    ExecutionPlan,
    PlanStep,
    PlanType,
    PlanScope,
    build_plan_generation_prompt,
    get_outline_generation_prompt,
    get_outline_expansion_prompt,
    get_outline_refinement_prompt,
    get_outline_set_refinement_prompt,
    get_detailed_outline_refinement_prompt
)
from ..utils.import_prompts import (
    validate_import_draft,
    get_import_outline_generation_prompt,
    get_import_outline_expansion_prompt,
    get_import_conversion_prompt,
)
from ..utils.editor_function_executor import SSEEvent, EventType
from ..utils.story_conductor import StoryConductor, ConductorEvent, ConductorEventType
from ..utils.story_reviewer import StoryReviewAgent, ReviewReport, IssueSeverity

logger = logging.getLogger(__name__)


def _build_llm_error_response(action: str, error: Exception) -> JSONResponse:
    """Convert common upstream LLM failures into clearer HTTP responses."""
    message = str(error)
    lowered = message.lower()
    status_code = 500

    if "403" in lowered or "forbidden" in lowered or "permissiondenied" in lowered:
        status_code = 503
        user_message = (
            f"{action} failed because the configured LLM provider rejected the request. "
            "Check the configured model, API key, and account permissions."
        )
    elif "401" in lowered or "unauthorized" in lowered or "authentication" in lowered:
        status_code = 503
        user_message = (
            f"{action} failed because the configured LLM provider could not authenticate. "
            "Check the configured API key or credentials."
        )
    elif "429" in lowered or "rate limit" in lowered:
        status_code = 503
        user_message = (
            f"{action} failed because the LLM provider rate-limited the request. "
            "Please try again shortly."
        )
    else:
        user_message = f"{action} failed: {message}"

    return JSONResponse({
        "error": user_message,
        "details": message
    }, status_code=status_code)


def register_plan_routes(app: FastAPI, game_kernel: Any, story_manager: Any):
    """Register plan-based AI editing routes.
    
    Args:
        app: The FastAPI application
        game_kernel: The game kernel instance (for LLM access)
        story_manager: The story manager instance
    """
    
    @app.post("/api/editor/generate-plan")
    async def generate_plan(request: Request):
        """Generate an execution plan for the user's request.
        
        This endpoint takes the user's prompt and current editor state,
        then uses the LLM to generate a structured plan that can be
        reviewed and executed.
        
        Request body:
            - prompt: User's edit request
            - nodes: Current nodes from ReactFlow
            - edges: Current edges
            - characters: Current characters
            - objects: Current objects
            - parameters: Current initial_variables
            - selected_node_ids: IDs of selected nodes (optional)
            - story_metadata: Story title, genre, etc. (optional)
            
        Returns:
            JSON with the generated plan
        """
        try:
            json_data = await request.json()
        except Exception as e:
            return JSONResponse({"error": f"Invalid JSON: {e}"}, status_code=400)
        
        prompt = json_data.get("prompt")
        if not prompt:
            return JSONResponse({"error": "Prompt is required"}, status_code=400)
        
        if not game_kernel or not game_kernel.llm_provider:
            return JSONResponse({"error": "LLM provider not configured"}, status_code=503)
        
        nodes = json_data.get("nodes", [])
        edges = json_data.get("edges", [])
        characters = json_data.get("characters", [])
        objects = json_data.get("objects", [])
        parameters = json_data.get("parameters", {})
        selected_node_ids = json_data.get("selected_node_ids", [])
        story_metadata = json_data.get("story_metadata", {})
        
        # Build the plan generation prompt
        system_prompt = build_plan_generation_prompt(
            user_prompt=prompt,
            nodes=nodes,
            edges=edges,
            characters=characters,
            objects=objects,
            parameters=parameters,
            selected_node_ids=selected_node_ids,
            story_metadata=story_metadata
        )
        
        try:
            # Call LLM to generate the plan
            logger.info(f"Generating plan for prompt: {prompt[:100]}...")
            
            response = await game_kernel.llm_provider.generate_response(system_prompt)
            
            # Parse the JSON response
            plan_json = _extract_json_from_response(response)
            
            if not plan_json:
                return JSONResponse({
                    "error": "Failed to parse plan from LLM response",
                    "raw_response": response[:500]
                }, status_code=500)
            
            # Validate the plan structure
            try:
                plan = ExecutionPlan.from_dict(plan_json)
                errors = plan.validate()
                if errors:
                    return JSONResponse({
                        "error": f"Plan validation failed: {'; '.join(errors)}",
                        "plan": plan_json
                    }, status_code=400)
            except Exception as e:
                return JSONResponse({
                    "error": f"Invalid plan structure: {e}",
                    "plan": plan_json
                }, status_code=400)
            
            return JSONResponse({
                "success": True,
                "plan": plan.to_dict()
            })
            
        except Exception as e:
            logger.error(f"Error generating plan: {e}", exc_info=True)
            return JSONResponse({"error": str(e)}, status_code=500)
    
    @app.post("/api/editor/execute-plan")
    async def execute_plan(request: Request):
        """Execute a plan step-by-step with SSE streaming.
        
        Request body:
            - plan: The execution plan to run
            - nodes: Current nodes
            - edges: Current edges
            - characters: Current characters
            - objects: Current objects
            - parameters: Current parameters
            
        Returns:
            SSE stream with step-by-step updates
        """
        try:
            json_data = await request.json()
        except Exception as e:
            return JSONResponse({"error": f"Invalid JSON: {e}"}, status_code=400)
        
        plan_data = json_data.get("plan")
        if not plan_data:
            return JSONResponse({"error": "Plan is required"}, status_code=400)
        
        nodes = json_data.get("nodes", [])
        edges = json_data.get("edges", [])
        characters = json_data.get("characters", [])
        objects = json_data.get("objects", [])
        parameters = json_data.get("parameters", {})
        
        try:
            plan = ExecutionPlan.from_dict(plan_data)
        except Exception as e:
            return JSONResponse({"error": f"Invalid plan: {e}"}, status_code=400)
        
        # Validate plan
        errors = plan.validate()
        if errors:
            return JSONResponse({
                "error": f"Plan validation failed: {'; '.join(errors)}"
            }, status_code=400)
        
        return StreamingResponse(
            _stream_plan_execution(plan, nodes, edges, characters, objects, parameters),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    
    @app.post("/api/editor/generate-outlines")
    async def generate_outlines(request: Request):
        """Generate multiple story outline options for user selection.
        
        Used in the story creation wizard when the user provides a vague idea.
        
        Request body:
            - idea: User's initial story idea
            - num_options: Number of outline options to generate (default: 3)
            
        Returns:
            JSON with array of outline options
        """
        try:
            json_data = await request.json()
        except Exception as e:
            return JSONResponse({"error": f"Invalid JSON: {e}"}, status_code=400)
        
        idea = json_data.get("idea")
        if not idea:
            return JSONResponse({"error": "Story idea is required"}, status_code=400)
        
        if not game_kernel or not game_kernel.llm_provider:
            return JSONResponse({"error": "LLM provider not configured"}, status_code=503)
        
        num_options = json_data.get("num_options", 3)
        
        prompt = get_outline_generation_prompt(idea, num_options)
        
        try:
            logger.info(f"Generating {num_options} outlines for idea: {idea[:100]}...")
            
            response = await game_kernel.llm_provider.generate_response(prompt)
            outlines_json = _extract_json_from_response(response)
            
            if not outlines_json or "outlines" not in outlines_json:
                return JSONResponse({
                    "error": "Failed to parse outlines from LLM response",
                    "raw_response": response[:500]
                }, status_code=500)
            
            return JSONResponse({
                "success": True,
                "outlines": outlines_json["outlines"]
            })
            
        except Exception as e:
            logger.error(f"Error generating outlines: {e}", exc_info=True)
            return _build_llm_error_response("Outline generation", e)

    @app.post("/api/editor/import/generate-outlines")
    async def generate_import_outlines(request: Request):
        """Generate outline options from normalized imported source material."""
        try:
            json_data = await request.json()
        except Exception as e:
            return JSONResponse({"error": f"Invalid JSON: {e}"}, status_code=400)

        import_draft = json_data.get("import_draft")
        writer_intent = json_data.get("writer_intent")
        num_options = json_data.get("num_options", 3)

        if not import_draft:
            return JSONResponse({"error": "import_draft is required"}, status_code=400)
        if not writer_intent:
            return JSONResponse({"error": "writer_intent is required"}, status_code=400)
        if not game_kernel or not game_kernel.llm_provider:
            return JSONResponse({"error": "LLM provider not configured"}, status_code=503)

        is_valid, errors, normalized_import = validate_import_draft(import_draft)
        if not is_valid:
            return JSONResponse({
                "error": f"Invalid import draft: {'; '.join(errors)}"
            }, status_code=400)

        prompt = get_import_outline_generation_prompt(normalized_import, writer_intent, num_options)

        try:
            logger.info(
                "Generating %s import outlines for source '%s'",
                num_options,
                normalized_import.get("title", "Untitled Import"),
            )

            response = await game_kernel.llm_provider.generate_response(prompt)
            outlines_json = _extract_json_from_response(response)

            if not outlines_json or "outlines" not in outlines_json:
                return JSONResponse({
                    "error": "Failed to parse outlines from LLM response",
                    "raw_response": response[:500]
                }, status_code=500)

            return JSONResponse({
                "success": True,
                "outlines": outlines_json["outlines"],
                "normalized_import": normalized_import,
            })

        except Exception as e:
            logger.error(f"Error generating import outlines: {e}", exc_info=True)
            return _build_llm_error_response("Import outline generation", e)

    @app.post("/api/editor/import/prepare-conversion")
    async def prepare_import_conversion(request: Request):
        """Convert imported source material directly into one reviewable detailed outline."""
        try:
            json_data = await request.json()
        except Exception as e:
            return JSONResponse({"error": f"Invalid JSON: {e}"}, status_code=400)

        import_draft = json_data.get("import_draft")
        writer_intent = json_data.get("writer_intent")

        if not import_draft:
            return JSONResponse({"error": "import_draft is required"}, status_code=400)
        if not writer_intent:
            return JSONResponse({"error": "writer_intent is required"}, status_code=400)
        if not game_kernel or not game_kernel.llm_provider:
            return JSONResponse({"error": "LLM provider not configured"}, status_code=503)

        is_valid, errors, normalized_import = validate_import_draft(import_draft)
        if not is_valid:
            return JSONResponse({
                "error": f"Invalid import draft: {'; '.join(errors)}"
            }, status_code=400)

        prompt = get_import_conversion_prompt(normalized_import, writer_intent)

        try:
            logger.info(
                "Preparing import conversion for source '%s'",
                normalized_import.get("title", "Untitled Import"),
            )

            response = await game_kernel.llm_provider.generate_response(prompt)
            conversion_json = _extract_json_from_response(response)

            if not conversion_json:
                return JSONResponse({
                    "error": "Failed to parse conversion draft from LLM response",
                    "raw_response": response[:500]
                }, status_code=500)

            detailed_outline = conversion_json.get("detailed_outline", {})
            lore_outline = conversion_json.get("lore_outline", "")
            plan_steps = _build_plan_from_detailed_outline(detailed_outline, lore_outline)

            plan = ExecutionPlan(
                plan_type=PlanType.STORY_CREATION,
                scope=PlanScope.FULL_STORY,
                summary=f"Create story: {detailed_outline.get('title', 'Untitled')}",
                steps=plan_steps,
                lore_outline=lore_outline,
                estimated_changes={
                    "nodes_created": len(detailed_outline.get("major_locations", [])),
                    "characters_created": len(detailed_outline.get("characters", [])),
                    "objects_created": len(detailed_outline.get("key_items", [])),
                    "parameters_set": 2
                }
            )

            return JSONResponse({
                "success": True,
                "detailed_outline": detailed_outline,
                "lore_outline": lore_outline,
                "plan": plan.to_dict(),
                "normalized_import": normalized_import,
            })

        except Exception as e:
            logger.error(f"Error preparing import conversion: {e}", exc_info=True)
            return _build_llm_error_response("Import conversion", e)
    
    @app.post("/api/editor/expand-outline")
    async def expand_outline(request: Request):
        """Expand a selected outline into a detailed story structure.
        
        Request body:
            - outline: The selected outline option
            - modifications: User's requested changes (optional)
            
        Returns:
            JSON with detailed story structure and execution plan
        """
        try:
            json_data = await request.json()
        except Exception as e:
            return JSONResponse({"error": f"Invalid JSON: {e}"}, status_code=400)
        
        outline = json_data.get("outline")
        if not outline:
            return JSONResponse({"error": "Outline is required"}, status_code=400)
        
        if not game_kernel or not game_kernel.llm_provider:
            return JSONResponse({"error": "LLM provider not configured"}, status_code=503)
        
        modifications = json_data.get("modifications")
        
        prompt = get_outline_expansion_prompt(outline, modifications)
        
        try:
            logger.info(f"Expanding outline: {outline.get('title', 'Untitled')}")
            
            response = await game_kernel.llm_provider.generate_response(prompt)
            expansion_json = _extract_json_from_response(response)
            
            if not expansion_json:
                return JSONResponse({
                    "error": "Failed to parse expansion from LLM response",
                    "raw_response": response[:500]
                }, status_code=500)
            
            # Also generate the execution plan from the detailed outline
            detailed_outline = expansion_json.get("detailed_outline", {})
            lore_outline = expansion_json.get("lore_outline", "")
            
            # Build execution plan from the detailed outline
            plan_steps = _build_plan_from_detailed_outline(detailed_outline, lore_outline)
            
            plan = ExecutionPlan(
                plan_type=PlanType.STORY_CREATION,
                scope=PlanScope.FULL_STORY,
                summary=f"Create story: {detailed_outline.get('title', 'Untitled')}",
                steps=plan_steps,
                lore_outline=lore_outline,
                estimated_changes={
                    "nodes_created": len(detailed_outline.get("major_locations", [])),
                    "characters_created": len(detailed_outline.get("characters", [])),
                    "objects_created": len(detailed_outline.get("key_items", [])),
                    "parameters_set": 2  # lore_outline + lore_writing_style
                }
            )
            
            return JSONResponse({
                "success": True,
                "detailed_outline": detailed_outline,
                "lore_outline": lore_outline,
                "plan": plan.to_dict()
            })
            
        except Exception as e:
            logger.error(f"Error expanding outline: {e}", exc_info=True)
            return _build_llm_error_response("Outline expansion", e)

    @app.post("/api/editor/import/expand-outline")
    async def expand_import_outline(request: Request):
        """Expand an import-derived outline into a detailed structure and plan."""
        try:
            json_data = await request.json()
        except Exception as e:
            return JSONResponse({"error": f"Invalid JSON: {e}"}, status_code=400)

        import_draft = json_data.get("import_draft")
        outline = json_data.get("outline")
        modifications = json_data.get("modifications")

        if not import_draft:
            return JSONResponse({"error": "import_draft is required"}, status_code=400)
        if not outline:
            return JSONResponse({"error": "Outline is required"}, status_code=400)
        if not game_kernel or not game_kernel.llm_provider:
            return JSONResponse({"error": "LLM provider not configured"}, status_code=503)

        is_valid, errors, normalized_import = validate_import_draft(import_draft)
        if not is_valid:
            return JSONResponse({
                "error": f"Invalid import draft: {'; '.join(errors)}"
            }, status_code=400)

        prompt = get_import_outline_expansion_prompt(normalized_import, outline, modifications)

        try:
            logger.info(
                "Expanding import outline '%s' from source '%s'",
                outline.get("title", "Untitled"),
                normalized_import.get("title", "Untitled Import"),
            )

            response = await game_kernel.llm_provider.generate_response(prompt)
            expansion_json = _extract_json_from_response(response)

            if not expansion_json:
                return JSONResponse({
                    "error": "Failed to parse expansion from LLM response",
                    "raw_response": response[:500]
                }, status_code=500)

            detailed_outline = expansion_json.get("detailed_outline", {})
            lore_outline = expansion_json.get("lore_outline", "")

            plan_steps = _build_plan_from_detailed_outline(detailed_outline, lore_outline)

            plan = ExecutionPlan(
                plan_type=PlanType.STORY_CREATION,
                scope=PlanScope.FULL_STORY,
                summary=f"Create story: {detailed_outline.get('title', 'Untitled')}",
                steps=plan_steps,
                lore_outline=lore_outline,
                estimated_changes={
                    "nodes_created": len(detailed_outline.get("major_locations", [])),
                    "characters_created": len(detailed_outline.get("characters", [])),
                    "objects_created": len(detailed_outline.get("key_items", [])),
                    "parameters_set": 2
                }
            )

            return JSONResponse({
                "success": True,
                "detailed_outline": detailed_outline,
                "lore_outline": lore_outline,
                "plan": plan.to_dict(),
                "normalized_import": normalized_import,
            })

        except Exception as e:
            logger.error(f"Error expanding import outline: {e}", exc_info=True)
            return _build_llm_error_response("Import outline expansion", e)
    
    @app.post("/api/editor/refine-outline")
    async def refine_outline(request: Request):
        """Refine a single outline based on user feedback.
        
        Used for AI-assisted modifications to individual direction cards.
        
        Request body:
            - outline: The current outline to refine
            - feedback: User's modification request
            
        Returns:
            JSON with the refined outline
        """
        try:
            json_data = await request.json()
        except Exception as e:
            return JSONResponse({"error": f"Invalid JSON: {e}"}, status_code=400)
        
        outline = json_data.get("outline")
        feedback = json_data.get("feedback")
        
        if not outline:
            return JSONResponse({"error": "Outline is required"}, status_code=400)
        if not feedback:
            return JSONResponse({"error": "Feedback is required"}, status_code=400)
        
        if not game_kernel or not game_kernel.llm_provider:
            return JSONResponse({"error": "LLM provider not configured"}, status_code=503)
        
        prompt = get_outline_refinement_prompt(outline, feedback)
        
        try:
            logger.info(f"Refining outline: {outline.get('title', 'Untitled')} with feedback: {feedback[:50]}...")
            
            response = await game_kernel.llm_provider.generate_response(prompt)
            refined_json = _extract_json_from_response(response)
            
            if not refined_json or "refined_outline" not in refined_json:
                return JSONResponse({
                    "error": "Failed to parse refined outline from LLM response",
                    "raw_response": response[:500]
                }, status_code=500)
            
            return JSONResponse({
                "success": True,
                "refined_outline": refined_json["refined_outline"]
            })
            
        except Exception as e:
            logger.error(f"Error refining outline: {e}", exc_info=True)
            return _build_llm_error_response("Outline refinement", e)

    @app.post("/api/editor/refine-outlines")
    async def refine_outlines(request: Request):
        """Refine the current set of outline directions in place."""
        try:
            json_data = await request.json()
        except Exception as e:
            return JSONResponse({"error": f"Invalid JSON: {e}"}, status_code=400)

        outlines = json_data.get("outlines")
        feedback = json_data.get("feedback")
        selected_index = json_data.get("selected_index")

        if not outlines or not isinstance(outlines, list):
            return JSONResponse({"error": "outlines is required"}, status_code=400)
        if not feedback:
            return JSONResponse({"error": "Feedback is required"}, status_code=400)
        if not game_kernel or not game_kernel.llm_provider:
            return JSONResponse({"error": "LLM provider not configured"}, status_code=503)

        prompt = get_outline_set_refinement_prompt(outlines, feedback, selected_index)

        try:
            logger.info("Refining %s outlines with feedback: %s...", len(outlines), feedback[:80])

            response = await game_kernel.llm_provider.generate_response(prompt)
            refined_json = _extract_json_from_response(response)

            if not refined_json or "updated_outlines" not in refined_json:
                return JSONResponse({
                    "error": "Failed to parse refined outlines from LLM response",
                    "raw_response": response[:500]
                }, status_code=500)

            return JSONResponse({
                "success": True,
                "updated_outlines": refined_json["updated_outlines"],
                "selected_index": refined_json.get("selected_index", selected_index)
            })

        except Exception as e:
            logger.error(f"Error refining outlines: {e}", exc_info=True)
            return _build_llm_error_response("Outline set refinement", e)

    @app.post("/api/editor/refine-detailed-outline")
    async def refine_detailed_outline(request: Request):
        """Refine the current detailed outline and regenerate its execution plan."""
        try:
            json_data = await request.json()
        except Exception as e:
            return JSONResponse({"error": f"Invalid JSON: {e}"}, status_code=400)

        detailed_outline = json_data.get("detailed_outline")
        feedback = json_data.get("feedback")

        if not detailed_outline:
            return JSONResponse({"error": "detailed_outline is required"}, status_code=400)
        if not feedback:
            return JSONResponse({"error": "Feedback is required"}, status_code=400)
        if not game_kernel or not game_kernel.llm_provider:
            return JSONResponse({"error": "LLM provider not configured"}, status_code=503)

        prompt = get_detailed_outline_refinement_prompt(detailed_outline, feedback)

        try:
            logger.info(
                "Refining detailed outline '%s' with feedback: %s...",
                detailed_outline.get("title", "Untitled"),
                feedback[:80]
            )

            response = await game_kernel.llm_provider.generate_response(prompt)
            refined_json = _extract_json_from_response(response)

            if not refined_json or "detailed_outline" not in refined_json:
                return JSONResponse({
                    "error": "Failed to parse refined detailed outline from LLM response",
                    "raw_response": response[:500]
                }, status_code=500)

            refined_detailed_outline = refined_json.get("detailed_outline", {})
            lore_outline = refined_json.get("lore_outline", "")
            plan_steps = _build_plan_from_detailed_outline(refined_detailed_outline, lore_outline)

            plan = ExecutionPlan(
                plan_type=PlanType.STORY_CREATION,
                scope=PlanScope.FULL_STORY,
                summary=f"Create story: {refined_detailed_outline.get('title', 'Untitled')}",
                steps=plan_steps,
                lore_outline=lore_outline,
                estimated_changes={
                    "nodes_created": len(refined_detailed_outline.get("major_locations", [])),
                    "characters_created": len(refined_detailed_outline.get("characters", [])),
                    "objects_created": len(refined_detailed_outline.get("key_items", [])),
                    "parameters_set": 2
                }
            )

            return JSONResponse({
                "success": True,
                "detailed_outline": refined_detailed_outline,
                "lore_outline": lore_outline,
                "plan": plan.to_dict()
            })

        except Exception as e:
            logger.error(f"Error refining detailed outline: {e}", exc_info=True)
            return _build_llm_error_response("Detailed outline refinement", e)
    
    @app.post("/api/editor/quick-generate")
    async def quick_generate(request: Request):
        """One-shot generation: generate plan and execute immediately.
        
        For simpler requests where plan review isn't needed.
        Streams the plan generation thinking, then execution.
        
        Request body:
            - prompt: User's edit request
            - nodes, edges, characters, objects, parameters: Current state
            - selected_node_ids: Selected nodes (optional)
            
        Returns:
            SSE stream with thinking + execution updates
        """
        try:
            json_data = await request.json()
        except Exception as e:
            return JSONResponse({"error": f"Invalid JSON: {e}"}, status_code=400)
        
        prompt = json_data.get("prompt")
        if not prompt:
            return JSONResponse({"error": "Prompt is required"}, status_code=400)
        
        if not game_kernel or not game_kernel.llm_provider:
            return JSONResponse({"error": "LLM provider not configured"}, status_code=503)
        
        return StreamingResponse(
            _stream_quick_generate(
                llm_provider=game_kernel.llm_provider,
                prompt=prompt,
                nodes=json_data.get("nodes", []),
                edges=json_data.get("edges", []),
                characters=json_data.get("characters", []),
                objects=json_data.get("objects", []),
                parameters=json_data.get("parameters", {}),
                selected_node_ids=json_data.get("selected_node_ids", []),
                story_metadata=json_data.get("story_metadata", {})
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    
    @app.post("/api/editor/conduct-story")
    async def conduct_story(request: Request):
        """Conduct story generation: expand skeleton into complete story.
        
        This endpoint takes a skeleton story (from expand-outline) and uses
        parallel LLM calls to expand each node into rich, playable content.
        
        Request body:
            - skeleton: The skeleton story structure (nodes, characters, etc.)
            - detailed_outline: The detailed outline with story structure
            - max_concurrent: Maximum parallel LLM calls (default: 3)
            
        Returns:
            SSE stream with real-time progress updates
        """
        try:
            json_data = await request.json()
        except Exception as e:
            return JSONResponse({"error": f"Invalid JSON: {e}"}, status_code=400)
        
        skeleton = json_data.get("skeleton")
        detailed_outline = json_data.get("detailed_outline")
        
        if not skeleton:
            return JSONResponse({"error": "Skeleton story is required"}, status_code=400)
        if not detailed_outline:
            return JSONResponse({"error": "Detailed outline is required"}, status_code=400)
        
        if not game_kernel or not game_kernel.llm_provider:
            return JSONResponse({"error": "LLM provider not configured"}, status_code=503)
        
        max_concurrent = json_data.get("max_concurrent", 3)
        
        return StreamingResponse(
            _stream_story_conducting(
                llm_provider=game_kernel.llm_provider,
                skeleton=skeleton,
                detailed_outline=detailed_outline,
                max_concurrent=max_concurrent
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    
    @app.post("/api/editor/review-story")
    async def review_story(request: Request):
        """Review a story for structural, reference, numerical, and quality issues.
        
        This endpoint performs comprehensive analysis of a story including:
        - Structural analysis (reachability, dead ends, orphan nodes)
        - Reference integrity (missing nodes, characters, objects)
        - Numerical balance (economy, difficulty curves)
        - Content quality (empty descriptions, missing actions)
        
        Request body:
            - story: The complete story data to review
            - include_llm_analysis: Whether to use LLM for deeper narrative analysis (optional)
            
        Returns:
            JSON with comprehensive review report
        """
        try:
            json_data = await request.json()
        except Exception as e:
            return JSONResponse({"error": f"Invalid JSON: {e}"}, status_code=400)
        
        story = json_data.get("story")
        if not story:
            return JSONResponse({"error": "Story data is required"}, status_code=400)
        
        include_llm = json_data.get("include_llm_analysis", False)
        
        try:
            # Create reviewer with LLM if requested
            llm_provider = game_kernel.llm_provider if include_llm and game_kernel else None
            reviewer = StoryReviewAgent(llm_provider=llm_provider)
            
            # Perform review
            if include_llm and llm_provider:
                report_dict = await reviewer.review_with_llm(story)
            else:
                report = reviewer.review(story)
                report_dict = report.to_dict()
            
            # Add success flag and message
            issue_counts = report_dict.get("summary", {}).get("issue_counts", {})
            critical_count = issue_counts.get("critical", 0)
            error_count = issue_counts.get("error", 0)
            warning_count = issue_counts.get("warning", 0)
            
            if critical_count > 0:
                status = "critical"
                message = f"Found {critical_count} critical issues that need immediate attention"
            elif error_count > 0:
                status = "error"
                message = f"Found {error_count} errors that should be fixed"
            elif warning_count > 0:
                status = "warning"
                message = f"Found {warning_count} warnings to review"
            else:
                status = "ok"
                message = "Story structure looks good!"
            
            return JSONResponse({
                "success": True,
                "status": status,
                "message": message,
                "report": report_dict
            })
            
        except Exception as e:
            logger.error(f"Error reviewing story: {e}", exc_info=True)
            return JSONResponse({"error": str(e)}, status_code=500)
    
    @app.post("/api/editor/validate-quick")
    async def validate_quick(request: Request):
        """Quick validation for real-time editing feedback.
        
        This is a lightweight validation endpoint designed for real-time
        feedback during editing. It checks only the most critical issues.
        
        Request body:
            - node_id: The node being edited
            - node_data: The current node data
            - context: Minimal context (adjacent nodes, story parameters)
            
        Returns:
            JSON with validation issues for this specific node
        """
        try:
            json_data = await request.json()
        except Exception as e:
            return JSONResponse({"error": f"Invalid JSON: {e}"}, status_code=400)
        
        node_id = json_data.get("node_id")
        node_data = json_data.get("node_data")
        
        if not node_id or not node_data:
            return JSONResponse({"error": "node_id and node_data are required"}, status_code=400)
        
        # Quick validation of a single node
        issues = []
        
        # Check description
        description = node_data.get("description", node_data.get("explicit_state", ""))
        if not description or not description.strip():
            issues.append({
                "severity": "warning",
                "message": "Node has no description",
                "suggestion": "Add a explicit_state for this location"
            })
        elif len(description.split()) < 15:
            issues.append({
                "severity": "info",
                "message": f"Description is short ({len(description.split())} words)",
                "suggestion": "Consider adding more detail"
            })
        
        # Check actions
        actions = node_data.get("actions", [])
        if not actions:
            issues.append({
                "severity": "info",
                "message": "No actions defined",
                "suggestion": "Add at least one action"
            })
        else:
            # Check for duplicate action IDs
            action_ids = {}
            for action in actions:
                action_id = action.get("id", "")
                if action_id in action_ids:
                    issues.append({
                        "severity": "error",
                        "message": f"Duplicate action ID: {action_id}",
                        "suggestion": "Use unique action IDs"
                    })
                action_ids[action_id] = True
                
                # Check for actions without effects
                effects = action.get("effects", [])
                if not effects:
                    issues.append({
                        "severity": "warning",
                        "message": f"Action '{action_id}' has no effects",
                        "suggestion": "Add at least one effect"
                    })
        
        return JSONResponse({
            "success": True,
            "node_id": node_id,
            "issues": issues,
            "is_valid": len([i for i in issues if i["severity"] == "error"]) == 0
        })


async def _stream_story_conducting(
    llm_provider: Any,
    skeleton: Dict[str, Any],
    detailed_outline: Dict[str, Any],
    max_concurrent: int = 3
) -> AsyncGenerator[str, None]:
    """Stream story conducting via SSE.
    
    Args:
        llm_provider: The LLM provider instance
        skeleton: The skeleton story structure
        detailed_outline: The detailed story outline
        max_concurrent: Maximum parallel LLM calls
        
    Yields:
        SSE formatted strings
    """
    conductor = StoryConductor(
        llm_provider=llm_provider,
        max_concurrent=max_concurrent
    )
    
    async for event in conductor.conduct_story(skeleton, detailed_outline):
        yield event.to_sse()


async def _stream_plan_execution(
    plan: ExecutionPlan,
    nodes: List[Dict],
    edges: List[Dict],
    characters: List[Dict],
    objects: List[Dict],
    parameters: Dict[str, Any]
) -> AsyncGenerator[str, None]:
    """Stream plan execution via SSE.
    
    Args:
        plan: The execution plan to run
        nodes, edges, characters, objects, parameters: Current state
        
    Yields:
        SSE formatted strings
    """
    executor = PlanExecutor(
        initial_nodes=nodes,
        initial_edges=edges,
        initial_characters=characters,
        initial_objects=objects,
        initial_parameters=parameters
    )
    
    async for event in executor.execute_plan_streaming(plan):
        yield event.to_sse()


async def _stream_quick_generate(
    llm_provider: Any,
    prompt: str,
    nodes: List[Dict],
    edges: List[Dict],
    characters: List[Dict],
    objects: List[Dict],
    parameters: Dict[str, Any],
    selected_node_ids: List[str],
    story_metadata: Dict[str, Any]
) -> AsyncGenerator[str, None]:
    """Generate plan and execute in one streaming response.
    
    Args:
        llm_provider: The LLM provider instance
        prompt: User's request
        nodes, edges, etc.: Current state
        
    Yields:
        SSE formatted strings
    """
    # Phase 1: Generate plan
    yield SSEEvent(EventType.THINKING, {
        "message": "Analyzing your request and creating a plan...",
        "phase": "planning"
    }).to_sse()
    await asyncio.sleep(0.05)
    
    system_prompt = build_plan_generation_prompt(
        user_prompt=prompt,
        nodes=nodes,
        edges=edges,
        characters=characters,
        objects=objects,
        parameters=parameters,
        selected_node_ids=selected_node_ids,
        story_metadata=story_metadata
    )
    
    try:
        response = await llm_provider.generate_response(system_prompt)
        plan_json = _extract_json_from_response(response)
        
        if not plan_json:
            yield SSEEvent(EventType.ERROR, {
                "error": "Failed to generate a valid plan",
                "raw_response": response[:300]
            }).to_sse()
            return
        
        plan = ExecutionPlan.from_dict(plan_json)
        errors = plan.validate()
        
        if errors:
            yield SSEEvent(EventType.ERROR, {
                "error": f"Plan validation failed: {'; '.join(errors)}"
            }).to_sse()
            return
        
        # Emit plan summary
        yield SSEEvent(EventType.THINKING, {
            "message": f"Plan ready: {plan.summary}",
            "phase": "executing",
            "total_steps": len(plan.steps),
            "plan_summary": {
                "type": plan.plan_type.value,
                "scope": plan.scope.value,
                "steps": len(plan.steps)
            }
        }).to_sse()
        await asyncio.sleep(0.1)
        
        # Phase 2: Execute plan
        executor = PlanExecutor(
            initial_nodes=nodes,
            initial_edges=edges,
            initial_characters=characters,
            initial_objects=objects,
            initial_parameters=parameters
        )
        
        async for event in executor.execute_plan_streaming(plan):
            yield event.to_sse()
            
    except Exception as e:
        logger.error(f"Error in quick generate: {e}", exc_info=True)
        yield SSEEvent(EventType.ERROR, {"error": str(e)}).to_sse()


def _extract_json_from_response(response: str) -> Dict[str, Any]:
    """Extract JSON from LLM response, handling markdown code blocks.
    
    Args:
        response: Raw LLM response string
        
    Returns:
        Parsed JSON dict, or None if parsing failed
    """
    # Try to extract from markdown code block first
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response, re.DOTALL)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        # Try the whole response
        json_str = response.strip()

    candidates = [json_str]

    # Try to find JSON object boundaries
    start = json_str.find('{')
    end = json_str.rfind('}')
    if start != -1 and end != -1:
        bounded = json_str[start:end+1]
        if bounded != json_str:
            candidates.append(bounded)

    for candidate in candidates:
        parsed = _load_json_with_minimal_repairs(candidate)
        if parsed is not None:
            return parsed

    return None


def _load_json_with_minimal_repairs(json_str: str) -> Dict[str, Any] | None:
    """Try loading JSON, then apply narrow repairs for common LLM mistakes.

    The repair pass is intentionally conservative:
    - escape unescaped double quotes that appear inside an already-open string
    - escape literal newlines inside strings

    This keeps the current text-based JSON flow usable while the endpoint remains
    on plain `generate_response(...)`. The longer-term direction should be moving
    outline endpoints to structured output / schema-based generation.
    """
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        repaired = _repair_common_llm_json_issues(json_str)
        if repaired != json_str:
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                return None
    return None


def _repair_common_llm_json_issues(json_str: str) -> str:
    """Repair a small set of common JSON mistakes from LLM text output."""
    result: list[str] = []
    in_string = False
    escaped = False
    length = len(json_str)
    i = 0

    while i < length:
        char = json_str[i]

        if not in_string:
            result.append(char)
            if char == '"':
                in_string = True
                escaped = False
            i += 1
            continue

        if escaped:
            result.append(char)
            escaped = False
            i += 1
            continue

        if char == '\\':
            result.append(char)
            escaped = True
            i += 1
            continue

        if char in ('\n', '\r'):
            # Literal newlines are invalid inside JSON strings.
            if char == '\n':
                result.append('\\n')
            else:
                result.append('\\r')
            i += 1
            continue

        if char == '"':
            next_non_ws = ''
            j = i + 1
            while j < length:
                if not json_str[j].isspace():
                    next_non_ws = json_str[j]
                    break
                j += 1

            if next_non_ws in {',', '}', ']', ':'} or not next_non_ws:
                result.append(char)
                in_string = False
            else:
                # Treat it as an inner quote inside the current string value.
                result.append('\\"')
            i += 1
            continue

        result.append(char)
        i += 1

    return ''.join(result)


def _build_plan_from_detailed_outline(
    detailed_outline: Dict[str, Any],
    lore_outline: str
) -> List[PlanStep]:
    """Convert a high-level outline into executable plan steps.
    
    This creates a skeleton story structure with:
    - Lore and writing style parameters
    - Key game variables
    - Main characters with starting locations
    - Key items as objects
    - A start node
    - Placeholder nodes for major locations
    - Ending nodes
    - Story structure stored for conducting phase
    
    Args:
        detailed_outline: The expanded outline with story elements
        lore_outline: The lore text to store
        
    Returns:
        List of PlanStep objects
    """
    steps = []
    step_id = 1
    
    def normalize_id(name: str) -> str:
        """Normalize a name to a valid ID."""
        return name.lower().replace(" ", "_").replace("'", "").replace("-", "_").replace("(", "").replace(")", "").replace(",", "")
    
    # Step 1: Set lore outline (story context for LLM)
    if lore_outline:
        steps.append(PlanStep(
            id=step_id,
            action="set_parameter",
            params={"key": "lore_outline", "value": lore_outline},
            description="Store story outline"
        ))
        step_id += 1
    
    # Step 2: Set writing style
    if detailed_outline.get("writing_style"):
        steps.append(PlanStep(
            id=step_id,
            action="set_parameter",
            params={"key": "lore_writing_style", "value": detailed_outline["writing_style"]},
            description="Set writing style"
        ))
        step_id += 1
    
    # Step 3: Set theme and tone
    theme_info = f"Theme: {detailed_outline.get('theme', '')}. Tone: {detailed_outline.get('tone', '')}"
    if theme_info.strip() != "Theme: . Tone:":
        steps.append(PlanStep(
            id=step_id,
            action="set_parameter",
            params={"key": "lore_theme", "value": theme_info},
            description="Set story theme"
        ))
        step_id += 1
    
    # Step 4: Store story structure for conducting phase
    story_structure = detailed_outline.get("story_structure", {})
    if story_structure:
        steps.append(PlanStep(
            id=step_id,
            action="set_parameter",
            params={"key": "lore_story_structure", "value": json.dumps(story_structure)},
            description="Store story structure"
        ))
        step_id += 1
    
    # Step 5: Store game mechanics for conducting phase
    game_mechanics = detailed_outline.get("game_mechanics", {})
    if game_mechanics:
        steps.append(PlanStep(
            id=step_id,
            action="set_parameter",
            params={"key": "lore_game_mechanics", "value": json.dumps(game_mechanics)},
            description="Store game mechanics"
        ))
        step_id += 1
    
    # Step 6: Set up key game variables from mechanics
    for var in game_mechanics.get("key_variables", []):
        var_name = var.get("name", "")
        var_type = var.get("type", "number")
        if var_name:
            # Set initial value based on type
            initial_value = 0 if var_type == "number" else (False if var_type == "boolean" else "")
            steps.append(PlanStep(
                id=step_id,
                action="set_parameter",
                params={"key": var_name, "value": initial_value},
                description=f"Initialize variable: {var_name} ({var.get('purpose', '')})"
            ))
            step_id += 1
    
    # Collect major locations for character starting positions
    major_locations = detailed_outline.get("major_locations", [])
    location_ids = ["start"] + [normalize_id(loc) for loc in major_locations[:10]]
    
    # Step 7: Create main characters with starting locations
    characters = detailed_outline.get("characters", [])
    for i, char in enumerate(characters):
        char_id = char.get("id", "")
        if not char_id:
            continue
        
        role = char.get("role", "").lower()
        description = char.get("one_liner", "") or char.get("role", "")
        
        # Determine starting location based on role
        location = ""
        if role == "protagonist":
            # Protagonist doesn't need a fixed starting location here.
            pass
        elif role == "antagonist":
            # Antagonist appears near the end.
            if len(location_ids) > 2:
                location = location_ids[-1]
        elif role in ["ally", "ally/unknown", "npc"]:
            # Place allies/NPCs in middle locations.
            mid_idx = len(location_ids) // 2
            if mid_idx < len(location_ids):
                location = location_ids[mid_idx]
        
        steps.append(PlanStep(
            id=step_id,
            action="create_character",
            params={
                "id": char_id,
                "name": char.get("name", char_id),
                "definition": (
                    f"[Identity]\n{description}\n\n"
                    f"[Behavior Rules]\nStay aligned with the story role: {char.get('role', 'npc')}."
                ),
                "explicit_state": description,
                "properties": {"location": location} if location else {}
            },
            description=f"Create character: {char.get('name', char_id)}"
        ))
        step_id += 1
    
    # Step 8: Create key items as objects
    key_items = detailed_outline.get("key_items", [])
    for item in key_items:
        item_id = item.get("id", "")
        if not item_id:
            continue
        item_purpose = item.get("purpose", "")
        steps.append(PlanStep(
            id=step_id,
            action="create_object",
            params={
                "id": item_id,
                "name": item.get("name", item_id),
                "definition": f"Item: {item.get('name', item_id)}. {item_purpose}",
                "explicit_state": f"A {item.get('name', item_id)}.",
                "properties": {"status": []},
            },
            description=f"Create item: {item.get('name', item_id)}"
        ))
        step_id += 1
    
    # Step 9: Create start node with story setup
    act_1 = story_structure.get("act_1", "The story begins...")
    start_setting = detailed_outline.get('setting', '')
    
    steps.append(PlanStep(
        id=step_id,
        action="create_node",
        params={
            "id": "start",
            "name": detailed_outline.get("title", "Start"),
            "definition": f"Starting location of the story. Setting: {start_setting}",
            "explicit_state": f"[To be expanded] {start_setting} {act_1}",
            "implicit_state": "This is where the player's journey begins.",
            "properties": {"status": []},
            "actions": [],
            "is_start_node": True
        },
        description="Create start node"
    ))
    step_id += 1
    
    # Step 10: Create skeleton nodes for major locations
    prev_location = "start"
    for i, loc_name in enumerate(major_locations[:10]):  # Increased limit to 10
        loc_id = normalize_id(loc_name)
        if loc_id == "start":
            continue
        
        # Determine which act this location belongs to
        total_locs = len(major_locations)
        if i < total_locs / 3:
            act_hint = story_structure.get("act_1", "")
        elif i < 2 * total_locs / 3:
            act_hint = story_structure.get("act_2", "")
        else:
            act_hint = story_structure.get("act_3", "")
        
        steps.append(PlanStep(
            id=step_id,
            action="create_node",
            params={
                "id": loc_id,
                "name": loc_name,
                "definition": f"Location: {loc_name}. Story beat: {act_hint[:100] if act_hint else 'Continue exploring.'}",
                "explicit_state": f"[To be expanded] You are in {loc_name}.",
                "implicit_state": "",
                "properties": {"status": []},
                "actions": []
            },
            description=f"Create location: {loc_name}"
        ))
        step_id += 1
        
        # Add navigation action from previous location
        steps.append(PlanStep(
            id=step_id,
            action="add_action_to_node",
            params={
                "node_id": prev_location,
                "action": {
                    "id": f"go_to_{loc_id}",
                    "text": f"Go to {loc_name}",
                    "effects": [{"type": "goto_node", "target": loc_id}]
                }
            },
            description=f"Add navigation: {prev_location} -> {loc_id}"
        ))
        step_id += 1
        prev_location = loc_id
    
    # Step 11: Create ending nodes
    endings = detailed_outline.get("endings", [])
    for ending in endings:
        ending_title = ending.get("title", "Ending")
        ending_id = normalize_id(ending_title)
        ending_type = ending.get("type", "neutral")
        ending_trigger = ending.get("trigger", "")
        
        # Determine ending type label
        if ending_type == "good":
            ending_label = "GOOD ENDING"
        elif ending_type == "bad":
            ending_label = "BAD ENDING"
        else:
            ending_label = "ENDING"
        
        steps.append(PlanStep(
            id=step_id,
            action="create_node",
            params={
                "id": ending_id,
                "name": ending_title,
                "definition": f"[{ending_label}] {ending_title}. Trigger: {ending_trigger}",
                "explicit_state": f"[To be expanded] The story reaches its conclusion: {ending_title}.",
                "implicit_state": f"This is a {ending_type} ending. {ending_trigger}",
                "properties": {"status": [], "ending_type": ending_type},
                "actions": [],
                "is_ending": True
            },
            description=f"Create ending: {ending_title} ({ending_type})"
        ))
        step_id += 1
        
        # Add action from last location to this ending
        # (The actual conditions will be set during conducting)
        steps.append(PlanStep(
            id=step_id,
            action="add_action_to_node",
            params={
                "node_id": prev_location,
                "action": {
                    "id": f"ending_{ending_id}",
                    "text": f"[{ending_type.upper()}] {ending_title}",
                    "effects": [{"type": "goto_node", "target": ending_id}]
                }
            },
            description=f"Add ending path: {prev_location} -> {ending_id}"
        ))
        step_id += 1
    
    return steps
