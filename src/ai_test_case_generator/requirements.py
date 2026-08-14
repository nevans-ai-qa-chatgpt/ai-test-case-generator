"""Stable identifiers for requirements exposed to generation models."""

from ai_test_case_generator.models import GenerationRequest


def requirement_text_by_id(request: GenerationRequest) -> dict[str, str]:
    """Map stable model-facing IDs to authoritative request text."""

    criteria = request.story.acceptance_criteria
    if not criteria:
        return {"NARRATIVE": request.story.narrative}
    return {
        f"AC-{index:03d}": criterion
        for index, criterion in enumerate(criteria, start=1)
    }


def requirement_prompt_data(request: GenerationRequest) -> list[dict[str, str]]:
    """Return ordered ID/text pairs for the model prompt."""

    return [
        {"id": requirement_id, "text": text}
        for requirement_id, text in requirement_text_by_id(request).items()
    ]
