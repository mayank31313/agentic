import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from cndi.annotations import Component
from cndi.env import getContextEnvironment
from fastmcp.tools import ToolResult, tool
from httpx import ConnectError
from mcp.types import TextContent
from pydantic import BaseModel, Field

from agentic.app.agents import get_image_agent
from agentic.app.constants import (
    EXTERNAL_API_LOCALAI_BASE_URL_PROP,
    EXTERNAL_API_LOCALAI_DEFAULT_IMAGE_MODEL_PROP,
    EXTERNAL_API_LOCALAI_REQUEST_TIMEOUT_PROP,
)
from agentic.app.image_agent import DefectFixPromptAgent

logger = logging.getLogger(__name__)


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(
        ...,
        description=(
            "A detailed, descriptive prompt for the image generation model. "
            "For best results, be specific and include: "
            "(1) the main subject and its pose/action, "
            "(2) setting/background, "
            "(3) art style or medium (e.g. 'photorealistic', 'oil painting', 'anime', '3D render'), "
            "(4) lighting and mood (e.g. 'golden hour', 'dramatic shadows', 'soft diffused light'), "
            "(5) camera/composition details if relevant (e.g. 'close-up portrait', 'wide angle', 'aerial view'), "
            "and (6) quality boosters (e.g. 'highly detailed', '8k', 'sharp focus'). "
            "Use comma-separated descriptive phrases rather than full sentences — this matches how "
            "diffusion models were trained and produces more accurate results. "
            "Example: 'a red fox sitting in a snowy forest, golden hour lighting, "
            "photorealistic, highly detailed fur, shallow depth of field, 8k'."
        ),
    )
    negative_prompt: str = Field(
        description=(
            "Comma-separated list of elements, styles, or artifacts to exclude from the image. "
            "Commonly used to suppress low-quality artifacts (e.g. 'blurry, low quality, distorted, "
            "extra limbs, watermark, text') or to steer away from unwanted styles/subjects the prompt "
            "didn't already rule out. Leave empty if no specific exclusions are needed."
        ),
    )
    temperature: float = Field(
        default=2.5,
        ge=0.0,
        le=3.0,
        description=(
            "Controls randomness/creativity of generation. Lower values (e.g. 0.3-0.5) produce "
            "more predictable results closely matching the prompt; higher values (e.g. 1.0-1.5) "
            "introduce more variation and creative interpretation, at some risk of straying from "
            "the prompt's intent. Default of 0.7 balances fidelity and variety for most requests."
        ),
    )
    num_images: int = Field(
        default=1, ge=1, le=4, description="Number of images to generate in a batch"
    )
    init_image_path: str | None = Field(
        default=None,
        description=(
            "Optional path to an initial image for image-to-image generation. If provided, the model will use this image as a starting point and apply the prompt to modify it. "
            "If not provided, the model will generate an image from scratch based solely on the prompt."
        ),
    )


async def save_image_bytes_async(image_bytes: bytes, path: str) -> Path:
    file_path = Path(path)
    await asyncio.to_thread(file_path.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(file_path.write_bytes, image_bytes)
    return file_path


async def fetch_image_from_url(
    url: str, max_retries: int = 3, delay: float = 1.0
) -> bytes:
    last_error = None
    async with httpx.AsyncClient(timeout=60) as client:
        for attempt in range(max_retries):
            try:
                response = await client.get(url)
                response.raise_for_status()
                return response.content
            except (httpx.HTTPStatusError, httpx.TransportError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay * (attempt + 1))
    raise last_error


class ModelOutput(BaseModel):
    id: str
    data: list[Any]


@Component
class LocalAiApi:
    def __init__(self, url=None, image_model=None):
        self.url = url or getContextEnvironment(
            EXTERNAL_API_LOCALAI_BASE_URL_PROP,
            os.getenv("AGENTIC_BOT_LOCAL_API_BASE_URL"),
        )
        self.image_model = image_model or getContextEnvironment(
            EXTERNAL_API_LOCALAI_DEFAULT_IMAGE_MODEL_PROP,
            os.getenv("AGENTIC_BOT_LOCAL_API_IMAGE_MODEL"),
        )
        self.request_timeout = getContextEnvironment(
            EXTERNAL_API_LOCALAI_REQUEST_TIMEOUT_PROP, castFunc=int, defaultValue=1200
        )

    async def wait_for_task_completion(self, task_id: str, poll_interval: float = 2.0):
        elapsed_time = 0.0
        while elapsed_time < self.request_timeout:
            response = await self._get(path=f"tasks/{task_id}")
            status = response.get("status")
            if status == "COMPLETED":
                return response
            elif status == "FAILED":
                raise Exception(f"Image generation task {task_id} failed.")
            await asyncio.sleep(poll_interval)
            elapsed_time += poll_interval
        raise TimeoutError(
            f"Image generation task {task_id} did not complete within {self.request_timeout} seconds."
        )

    async def generate_image_as_task(
        self, image_generation_request: ImageGenerationRequest
    ):
        payload = {
            "prompt": image_generation_request.prompt,
            "negative_prompt": image_generation_request.negative_prompt,
            # "n": image_generation_request.num_images,
            # "size": '512x512',
            "model": self.image_model,
            # "temperature": image_generation_request.temperature
        }
        task_id = (await self._post(path="images/generations", json=payload)).get(
            "task_id"
        )

        return await asyncio.wait_for(
            self.wait_for_task_completion(task_id), timeout=self.request_timeout
        )

    async def generate_image_to_image_as_task(
        self, image_generation_request: ImageGenerationRequest
    ):
        payload = {
            "prompt": image_generation_request.prompt,
            "negative_prompt": image_generation_request.negative_prompt,
            # "n": image_generation_request.num_images,
            # "size": '512x512',
            "model": self.image_model,
            # "temperature": image_generation_request.temperature
            "init_image": dict(
                type="base64",
                data=DefectFixPromptAgent.image_to_data_url(
                    image_generation_request.init_image_path
                ),
            ),
        }
        task_id = (await self._post(path="images/img2img", json=payload)).get("task_id")

        return await asyncio.wait_for(
            self.wait_for_task_completion(task_id), timeout=self.request_timeout
        )

    async def generate_image(self, image_generation_request: ImageGenerationRequest):
        payload = {
            "prompt": image_generation_request.prompt,
            "negative_prompt": image_generation_request.negative_prompt,
            # "n": image_generation_request.num_images,
            # "size": '512x512',
            "model": self.image_model,
            # "temperature": image_generation_request.temperature
        }
        return await self._post(path="images/generations", json=payload)

    async def _get(self, path):
        async with httpx.AsyncClient(timeout=self.request_timeout) as client:
            response = await client.get(
                f"{self.url}/{path}",
            )
            response.raise_for_status()
            return response.json()

    async def _post(self, path, json):
        async with httpx.AsyncClient(timeout=self.request_timeout) as client:
            response = await client.post(
                f"{self.url}/{path}",
                json=json,
            )
            response.raise_for_status()
            return response.json()


SYSTEM_PROMPT = """\
You are a meticulous image-prompt QA reviewer for a text-to-image pipeline.

You will be shown a generated image, the prompt that was used to generate it, and \
(optionally) the negative prompt that was used. Your job is to judge how well the \
image matches the INTENT of the prompt, and produce a corrected prompt/negative \
prompt pair that would fix any problems on a regeneration attempt.

Be specific and visual in your reasoning — reference exact discrepancies you can see \
(wrong number of objects/limbs, missing described elements, wrong colors, wrong pose, \
anatomical errors, compositional issues, artifacts, wrong art style, text/watermark \
errors, etc.). Do not give vague praise or vague criticism.

Scoring guide:
  0.9-1.0 = matches prompt closely, no notable defects
  0.7-0.89 = matches overall intent, minor defects or omissions
  0.4-0.69 = partially matches, significant defects or missing elements
  0.0-0.39 = does not match the prompt's core intent, or has severe artifacts

When writing fix_prompt:
  - Keep everything from the original prompt that IS working.
  - Add or sharpen specific details that address the defects you found.
  - Don't pad with generic quality tags unless they'd plausibly fix a real defect you saw.

When writing negative_prompt:
  - Base it on what actually went wrong in THIS image, not a generic boilerplate list.
  - If nothing went wrong, keep it minimal (standard defect avoidance is fine).

Respond ONLY with the JSON object matching the required schema. No extra commentary.
"""

USER_PROMPT_TEMPLATE = """\
Original prompt: {original_prompt}
Original negative prompt: {original_negative_prompt}

Evaluate the attached image against the original prompt's intent and return the \
structured analysis.
"""


class ImageAnalysisResult(BaseModel):
    fix_prompt: str = Field(
        description="Corrected version of the original prompt that would better "
        "produce the intended image. If the image already matches the prompt well, "
        "this can be the same as the original prompt."
    )
    negative_prompt: str = Field(
        description="Negative prompt describing what to avoid in a regeneration, "
        "based specifically on defects observed in this image (not generic boilerplate)."
    )
    score: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score 0-1 for how well the image matches the original "
        "prompt's intent. 1.0 = perfect match, 0.0 = completely unrelated.",
    )
    reason: str = Field(
        description="Concrete explanation of why the image does or doesn't match the "
        "prompt — cite specific visual discrepancies (missing elements, wrong count, "
        "wrong pose, artifacts, wrong style, etc.), not generic commentary."
    )


def analyse_image(image_generation_request: ImageGenerationRequest, image_url):
    image_agent = get_image_agent().with_structured_output(ImageAnalysisResult)

    prompt = image_generation_request.prompt
    negative_prompt = image_generation_request.negative_prompt

    lc_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": USER_PROMPT_TEMPLATE.format(
                        original_prompt=prompt,
                        original_negative_prompt=negative_prompt or "(none provided)",
                    ),
                },
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        },
    ]

    response = image_agent.invoke(lc_messages)
    return response


def get_image_tools(localai_api: LocalAiApi):
    @tool(timeout=1200)
    async def generate_image(
        image_generation_request: ImageGenerationRequest,
    ) -> ToolResult:
        """Call this tool when user request to generate image."""
        try:
            response_object = (
                await localai_api.generate_image_as_task(image_generation_request)
            ).get("output")
            data = response_object["data"]

            content_blocks = [
                TextContent(
                    text=f"Image generation completed. Generated {len(data)} image(s).",
                    type="text",
                )
            ]
            for i, d in enumerate(data):
                found = False
                for _ in range(3):
                    try:
                        url = d["url"]
                        content_blocks.append(
                            dict(type="image_url", image_url=dict(url=url))
                        )
                        found = True
                        break
                    except ConnectError:
                        logger.error(
                            f"Failed to retrive image from {d['url']} trying again in {1 * _} second"
                        )
                        await asyncio.sleep(1 * _)
                if not found:
                    raise Exception(f"Could not fetch image from {d['url']}")

            return ToolResult(content=content_blocks)
        except Exception as e:
            return ToolResult(
                content=[TextContent(text=f"Image generation failed: {e}", type="text")]
            )

    return [generate_image]
