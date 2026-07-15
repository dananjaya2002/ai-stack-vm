from typing import Optional


UTILITY_PROMPT_MARKERS = {
    "title": ("generate a concise, 3-5 word title", '"title"'),
    "follow_ups": ("suggest 3-5 relevant follow-up", '"follow_ups"'),
    "tags": ("generate 1-3 broad tags", '"tags"'),
}
def classify_utility_prompt(question: str) -> Optional[str]:
    normalized = question.lower()
    for prompt_type, markers in UTILITY_PROMPT_MARKERS.items():
        if all(marker in normalized for marker in markers):
            return prompt_type
    return None
