import re
from typing import TypeVar, Generic, Type

from pydantic import BaseModel, ValidationError

from ai_review.libs.json import sanitize_json_string
from ai_review.libs.logger import get_logger

logger = get_logger("LLM_JSON_PARSER")

T = TypeVar("T", bound=BaseModel)

CLEAN_JSON_BLOCK_RE = re.compile(r"```(?:json)?(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_first_json_object(raw: str) -> str | None:
    """
    Extract the first balanced JSON object from mixed LLM output.

    This handles responses like:
        I will inspect the repo. {"action":"TOOL_CALL","command":"ls"}

    It is intentionally conservative:
    - starts at the first "{"
    - tracks nested braces
    - ignores braces inside JSON strings
    - respects escaped quotes
    """
    text = (raw or "").strip()
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False

    for index in range(start, len(text)):
        char = text[index]

        if escape:
            escape = False
            continue

        if char == "\\" and in_string:
            escape = True
            continue

        if char == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]

    return None


class LLMOutputJSONParser(Generic[T]):
    """Reusable JSON parser for LLM responses."""

    def __init__(self, model: Type[T]):
        self.model = model
        self.model_name = self.model.__name__

    def try_parse(self, raw: str) -> T | None:
        logger.debug(f"[{self.model_name}] Attempting JSON parse (len={len(raw)})")

        try:
            return self.model.model_validate_json(raw)
        except ValidationError as error:
            logger.warning(f"[{self.model_name}] Raw JSON parse failed: {error}")
            cleaned = sanitize_json_string(raw)

            if cleaned != raw:
                logger.debug(f"[{self.model_name}] Sanitized JSON differs, retrying parse...")
                try:
                    return self.model.model_validate_json(cleaned)
                except ValidationError as error:
                    logger.warning(f"[{self.model_name}] Sanitized JSON still invalid: {error}")
                    return None
            else:
                logger.debug(f"[{self.model_name}] Sanitized JSON identical — skipping retry")
                return None

    def parse_output(self, output: str) -> T | None:
        output = (output or "").strip()
        if not output:
            logger.warning(f"[{self.model_name}] Empty LLM output")
            return None

        logger.debug(f"[{self.model_name}] Parsing output (len={len(output)})")

        if match := CLEAN_JSON_BLOCK_RE.search(output):
            logger.debug(f"[{self.model_name}] Found fenced JSON block, extracting...")
            output = match.group(1).strip()

        if parsed := self.try_parse(output):
            logger.info(f"[{self.model_name}] Successfully parsed")
            return parsed

        if object_candidate := extract_first_json_object(output):
            logger.debug(
                f"[{self.model_name}] Found JSON object candidate, retrying parse..."
            )
            if parsed := self.try_parse(object_candidate):
                logger.info(f"[{self.model_name}] Successfully parsed extracted JSON object")
                return parsed

        logger.error(f"[{self.model_name}] No valid JSON found in output")
        return None
