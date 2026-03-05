#!/usr/bin/env python3
"""Bridge script between Pot plugin runtime and openocr-python."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import wordninja  # type: ignore
except Exception:  # pragma: no cover
    wordninja = None


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="OpenOCR bridge for Pot plugin")
    parser.add_argument("--image", required=True, help="Input image path")
    parser.add_argument("--lang", default="auto", help="Requested language from Pot")
    parser.add_argument("--task", default="ocr", choices=["ocr", "unirec"], help="OpenOCR task")
    parser.add_argument("--mode", default="mobile", choices=["mobile", "server"], help="Model mode")
    parser.add_argument(
        "--backend",
        default="onnx",
        choices=["onnx", "onnxruntime", "torch"],
        help="Inference backend",
    )
    parser.add_argument(
        "--merge-lines",
        default="1",
        choices=["0", "1"],
        help="Return joined text instead of line array",
    )
    return parser.parse_args()


def dedupe_lines(lines: list[str]) -> list[str]:
    """Dedupe text lines while preserving order."""
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def fix_english_spacing(text: str) -> str:
    """Fix common missing-space patterns in Latin text."""
    if not text:
        return text

    cjk_count = len(re.findall(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]", text))
    latin_count = len(re.findall(r"[A-Za-z]", text))
    if cjk_count > latin_count:
        return text

    fixed = text
    fixed = re.sub(r"(?<=[0-9,.\-+%@])@(?=[0-9,.\-+%@])", "0", fixed)
    fixed = re.sub(r"(?<=[0-9,.\-+%@])@(?=[A-Za-z])", "0", fixed)
    fixed = re.sub(
        r"(?<![A-Za-z])[@0-9][@0-9,.\-+%]*(?![A-Za-z])",
        lambda m: normalize_numeric_token(m.group(0)),
        fixed,
    )
    fixed = re.sub(
        r"\b(\d),(\d),(\d{3})(?=\b|[A-Za-z])",
        lambda m: f"{m.group(1)}{m.group(2)},{m.group(3)}",
        fixed,
    )
    fixed = re.sub(r"([;:!?])(?=[A-Za-z0-9])", r"\1 ", fixed)
    fixed = re.sub(r",(?=[A-Za-z])", ", ", fixed)
    fixed = re.sub(r"(?<=[A-Za-z0-9])\.(?=[A-Za-z])", ". ", fixed)
    fixed = re.sub(r"%(?=[A-Za-z0-9])", "% ", fixed)
    fixed = re.sub(r"(?<=[A-Za-z])(?=[0-9])", " ", fixed)
    fixed = re.sub(r"(?<=[0-9])(?=[A-Za-z])", " ", fixed)
    fixed = re.sub(r"([A-Za-z]+'s)(?=[A-Za-z])", r"\1 ", fixed)
    fixed = re.sub(r"([A-Za-z]+(?:'re|'ve|'ll|'d|'m|n't))(?=[A-Za-z])", r"\1 ", fixed)
    fixed = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", fixed)
    fixed = re.sub(r"\b([A-Za-z]{8,})\b", lambda m: split_long_english_token(m.group(1)), fixed)
    fixed = re.sub(r"\s{2,}", " ", fixed)
    return fixed.strip()


def normalize_numeric_token(token: str) -> str:
    """Normalize OCR symbol errors in numeric-like tokens."""
    if "@" not in token:
        return token
    if not re.fullmatch(r"[@0-9,.\-+%]+", token):
        return token
    return token.replace("@", "0")


def split_long_english_token(token: str) -> str:
    """Split long glued English tokens into words when possible."""
    if not token or len(token) < 8:
        return token
    if wordninja is None:
        return token

    # Keep short all-caps abbreviations untouched.
    if token.isupper() and len(token) <= 8:
        return token

    parts = wordninja.split(token)
    if len(parts) <= 1:
        return token
    if "".join(parts).lower() != token.lower():
        return token

    # Preserve original case by slicing based on segmented lengths.
    restored: list[str] = []
    pos = 0
    for part in parts:
        end = pos + len(part)
        restored.append(token[pos:end])
        pos = end
    return " ".join(restored)


def maybe_parse_json(value: str) -> Any:
    """Parse a JSON string and return None on failure."""
    text = value.strip()
    if not text:
        return None
    if not ((text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]"))):
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def extract_text_lines(node: Any, output: list[str]) -> None:
    """Recursively extract text entries from OpenOCR output."""
    if node is None:
        return

    if isinstance(node, str):
        text = node.strip()
        if not text:
            return
        parsed = maybe_parse_json(text)
        if parsed is not None:
            extract_text_lines(parsed, output)
            return

        if "\t" in text:
            _, possible_json = text.split("\t", 1)
            parsed = maybe_parse_json(possible_json)
            if parsed is not None:
                extract_text_lines(parsed, output)
                return

        output.append(text)
        return

    if isinstance(node, dict):
        for key in ("text", "rec_text", "transcription"):
            value = node.get(key)
            if isinstance(value, str) and value.strip():
                output.append(value.strip())
        for value in node.values():
            extract_text_lines(value, output)
        return

    if isinstance(node, (list, tuple)):
        if len(node) >= 2:
            second = node[1]
            if isinstance(second, str) and second.strip():
                output.append(second.strip())
            elif isinstance(second, (list, tuple)) and second:
                first = second[0]
                if isinstance(first, str) and first.strip():
                    output.append(first.strip())
        for item in node:
            extract_text_lines(item, output)
        return


def unwrap_result(payload: Any) -> Any:
    """Unwrap task output to the raw OCR result node."""
    if isinstance(payload, tuple) and payload:
        return payload[0]
    return payload


def run_openocr(image_path: Path, task: str, mode: str, backend: str) -> Any:
    """Run OpenOCR and return raw result."""
    try:
        from openocr import OpenOCR  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "openocr-python is not installed. Run: pip install openocr-python==0.1.5"
        ) from exc

    normalized_backend = "onnx" if backend == "onnxruntime" else backend

    engine_kwargs: dict[str, Any] = {"task": task}
    if task == "ocr":
        engine_kwargs["mode"] = mode
        engine_kwargs["backend"] = normalized_backend
    elif task == "unirec":
        # UniRec currently ignores mode/backend.
        pass

    engine = OpenOCR(**engine_kwargs)
    save_dir = image_path.parent / ".tmp" / "openocr_output"

    if task == "ocr":
        return engine(
            image_path=str(image_path),
            save_dir=str(save_dir),
            is_visualize=False,
        )
    if task == "unirec":
        return engine(image_path=str(image_path), max_length=2048)
    raise RuntimeError(f"Unsupported task: {task}")


def main() -> int:
    """Entrypoint."""
    args = parse_args()
    image_path = Path(args.image)
    if not image_path.exists():
        print(
            json.dumps(
                {"error": f"Input image not found: {image_path}"},
                ensure_ascii=True,
            )
        )
        return 2

    try:
        raw_result = run_openocr(
            image_path=image_path,
            task=args.task,
            mode=args.mode,
            backend=args.backend,
        )
        normalized = unwrap_result(raw_result)
        lines: list[str] = []
        extract_text_lines(normalized, lines)
        lines = dedupe_lines(lines)

        merge_lines = args.merge_lines == "1"
        if merge_lines:
            text = " ".join(lines).strip()
        else:
            text = "\n".join(lines).strip()
        text = fix_english_spacing(text)

        payload = {
            "text": text,
            "lines": lines,
            "lang": args.lang,
            "task": args.task,
        }
        print(json.dumps(payload, ensure_ascii=True))
        return 0
    except Exception as exc:  # pylint: disable=broad-except
        print(json.dumps({"error": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
