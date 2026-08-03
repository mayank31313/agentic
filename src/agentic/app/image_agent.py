"""
Image Defect -> Fix-Prompt Agent
=================================

Takes a *defective* image as input and uses NVIDIA's hosted Kimi K2.6
vision-language model (via the OpenAI-compatible NIM endpoint, called
through LangChain's `ChatOpenAI` wrapper) to produce:

    1. `fix_prompt`      - a positive prompt describing the corrected,
                            clean version of the image
    2. `negative_prompt` - a negative prompt listing the exact defects
                            to avoid

These two prompts are meant to be fed straight into an image-edit /
inpainting model (e.g. SDXL inpaint, Flux Fill, Kolors Inpaint, etc.)
together with the original defective image, so that model can repair it.

Requirements
------------
    pip install langchain-openai langchain-core pydantic

Environment
-----------
    export NVIDIA_API_KEY="nvapi-..."      # from build.nvidia.com

Usage
-----
    python defect_fix_agent.py --image path/to/defective.png
    python defect_fix_agent.py --image path/to/defective.png --json
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# Structured output schema
# --------------------------------------------------------------------------

class FixPromptResult(BaseModel):
    """Structured result returned by the agent for a defective image."""

    defects_detected: List[str] = Field(
        description=(
            "Concise list of the specific visual defects found in the "
            "image (e.g. 'warped left hand with 6 fingers', "
            "'jpeg block artifacts in sky', 'watermark text bottom-right', "
            "'color banding in gradient background', 'blurry face')."
        )
    )
    fix_prompt: str = Field(
        description=(
            "A single, dense, positive prompt describing what the FINAL "
            "clean/corrected image should look like. It must preserve the "
            "original subject, composition, style, lighting and colors, "
            "and only correct the listed defects. Written for an "
            "image-editing / inpainting model."
        )
    )
    negative_prompt: str = Field(
        description=(
            "A comma-separated negative prompt that explicitly names the "
            "detected defects plus standard low-quality/artifact terms, "
            "so the image-edit model actively avoids reproducing them."
        )
    )
    confidence: Optional[str] = Field(
        default=None,
        description="'high', 'medium', or 'low' confidence in the defect analysis.",
    )


SYSTEM_PROMPT = """You are an expert prompt engineer for AI image-editing \
and inpainting models (Stable Diffusion inpaint, Flux Fill, Kolors, etc.).

You will be shown one defective image. Your job:
1. Carefully inspect it and identify every visible defect: anatomical \
errors, warped/duplicated body parts, artifacts, noise, blur, wrong \
perspective, broken text, watermarks, color banding, unnatural lighting, \
missing/extra objects, compression artifacts, etc.
2. Write a `fix_prompt`: describe the corrected image as it SHOULD look, \
keeping the same subject, pose, composition, art style, colors and \
lighting as the original -- only the defects should change. Be specific \
and visually descriptive, not just "fix the image".
3. Write a `negative_prompt`: a comma-separated list starting with the \
exact defects you found (in plain visual terms), followed by standard \
negative-prompt boilerplate (e.g. "blurry, lowres, jpeg artifacts, \
watermark, extra limbs, deformed hands, bad anatomy, distorted, noisy, \
oversaturated, text, signature").

Only return the structured fields requested. Do not include any \
commentary outside of them."""


# --------------------------------------------------------------------------
# Agent
# --------------------------------------------------------------------------


class DefectFixPromptAgent:
    """Wraps Kimi K2.6 (via NVIDIA NIM + LangChain OpenAI wrapper) to turn
    a defective image into a ready-to-use (fix_prompt, negative_prompt) pair.
    """

    def __init__(
        self,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ):
        # LangChain's OpenAI wrapper works out of the box against any
        # OpenAI-compatible endpoint -- NVIDIA NIM is OpenAI-compatible.
        self.llm = ChatOpenAI(
            model="mistralai/Mistral-Large-3-675B-Instruct-2512-Eagle",
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Ask the model to return the Pydantic schema directly
        # (uses tool-calling / JSON-schema mode under the hood).
        self.structured_llm = self.llm.with_structured_output(FixPromptResult)

    @staticmethod
    def image_to_data_url(image_path: str) -> str:
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(f"Image not found: {image_path}")

        mime_type, _ = mimetypes.guess_type(path.name)
        if mime_type is None:
            mime_type = "image/png"

        b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
        # return f"data:{mime_type};base64,{b64}"
        return b64

    def analyze(
        self,
        image_path: str,
        extra_instructions: Optional[str] = None,
    ) -> FixPromptResult:
        """Run the agent on a defective image and return structured
        fix_prompt / negative_prompt output.
        """
        data_url = self.image_to_data_url(image_path)

        user_text = "Analyze this defective image and produce the fix prompt and negative prompt."
        if extra_instructions:
            user_text += f"\n\nAdditional context from the user: {extra_instructions}"

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=[
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]
            ),
        ]

        result: FixPromptResult = self.structured_llm.invoke(messages)
        return result

    # ----------------------------------------------------------------
    # Loop 1: batch over a folder of defective images
    # ----------------------------------------------------------------

    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}

    def analyze_batch(
        self,
        image_paths: List[str],
        extra_instructions: Optional[str] = None,
        on_error: str = "skip",  # "skip" or "raise"
    ) -> "dict[str, Optional[FixPromptResult]]":
        """Run `analyze` over a list of images, one by one.

        Returns a dict mapping image_path -> FixPromptResult (or None if
        that image failed and on_error="skip").
        """
        results: "dict[str, Optional[FixPromptResult]]" = {}
        for path in image_paths:
            print(f"[batch] analyzing {path} ...")
            try:
                results[path] = self.analyze(path, extra_instructions=extra_instructions)
            except Exception as exc:
                print(f"[batch]   failed: {exc}", file=sys.stderr)
                if on_error == "raise":
                    raise
                results[path] = None
        return results

    @classmethod
    def iter_images_in_dir(cls, directory: str) -> List[str]:
        """Helper: list image files in a directory (non-recursive)."""
        d = Path(directory)
        return sorted(
            str(p) for p in d.iterdir()
            if p.is_file() and p.suffix.lower() in cls.IMAGE_EXTENSIONS
        )

    # ----------------------------------------------------------------
    # Loop 2: iterative refine -> edit -> re-check until clean
    # ----------------------------------------------------------------

    def refine_until_clean(
        self,
        image_path: str,
        apply_edit_fn,
        max_iterations: int = 3,
        clean_confidence: str = "high",
    ) -> "dict":
        """Iteratively: analyze defects -> call an external image-edit
        function with (fix_prompt, negative_prompt) -> re-analyze the
        edited result -> repeat until either no defects are reported,
        confidence reaches `clean_confidence`, or `max_iterations` is hit.

        `apply_edit_fn` must have the signature:
            apply_edit_fn(image_path: str, fix_prompt: str, negative_prompt: str) -> str
        and return the file path of the newly edited image (e.g. it writes
        "fixed_iter1.png" to disk and returns that path). Plug in your real
        image-edit / inpainting model here.

        Returns a dict with the history of every iteration and the final
        image path.
        """
        history = []
        current_image = image_path

        for i in range(1, max_iterations + 1):
            print(f"[refine] iteration {i}/{max_iterations} on {current_image}")
            result = self.analyze(current_image)
            history.append({"iteration": i, "image": current_image, "result": result})

            no_defects_left = len(result.defects_detected) == 0
            confident_enough = (result.confidence or "").lower() == clean_confidence.lower()

            if no_defects_left or confident_enough:
                print(f"[refine] stopping early at iteration {i}: image looks clean.")
                break

            if i == max_iterations:
                print("[refine] reached max_iterations without a fully clean result.")
                break

            current_image = apply_edit_fn(current_image, result.fix_prompt, result.negative_prompt)

        return {"history": history, "final_image": current_image}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a fix/negative prompt pair for a defective image.")
    parser.add_argument("--image", help="Path to a single defective image")
    parser.add_argument("--batch-dir", help="Path to a directory of defective images to process in a loop")
    parser.add_argument("--notes", default=None, help="Optional extra context about the defect")
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of formatted text")
    args = parser.parse_args()

    if not args.image and not args.batch_dir:
        print("Error: pass either --image or --batch-dir", file=sys.stderr)
        sys.exit(1)

    try:
        agent = DefectFixPromptAgent()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.batch_dir:
        image_paths = DefectFixPromptAgent.iter_images_in_dir(args.batch_dir)
        if not image_paths:
            print(f"No images found in {args.batch_dir}", file=sys.stderr)
            sys.exit(1)

        results = agent.analyze_batch(image_paths, extra_instructions=args.notes)

        if args.json:
            print(json.dumps(
                {p: (r.model_dump() if r else None) for p, r in results.items()},
                indent=2,
            ))
        else:
            for path, result in results.items():
                print(f"\n=== {path} ===")
                if result is None:
                    print("  (failed - see error above)")
                    continue
                print("  Defects:", ", ".join(result.defects_detected) or "none")
                print("  Fix prompt:", result.fix_prompt)
                print("  Negative prompt:", result.negative_prompt)
        return

    try:
        result = agent.analyze(args.image, extra_instructions=args.notes)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(result.model_dump(), indent=2))
    else:
        print("Defects detected:")
        for d in result.defects_detected:
            print(f"  - {d}")
        print(f"\nConfidence: {result.confidence or 'n/a'}")
        print("\nFix prompt:")
        print(f"  {result.fix_prompt}")
        print("\nNegative prompt:")
        print(f"  {result.negative_prompt}")


if __name__ == "__main__":
    main()