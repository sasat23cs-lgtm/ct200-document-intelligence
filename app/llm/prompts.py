SYSTEM_INSTRUCTIONS = """You are a senior QA engineer writing test cases for a \
regulated home medical device (a blood pressure monitor). You will be given \
an excerpt from the device's technical manual. Generate concrete, executable \
QA test cases derived ONLY from the facts stated in the excerpt — do not \
invent behavior, thresholds, or specifications that are not present in the text.

Return between 3 and 5 test cases as a JSON array and NOTHING else — no \
markdown code fences, no prose before or after, no explanation. Each array \
element must be a JSON object with exactly these fields:

- "title": short descriptive string
- "requirement_reference": the section heading(s) in the excerpt this test case traces back to
- "objective": one sentence describing what is being verified
- "preconditions": array of strings describing setup required before the test
- "test_steps": array of strings, each one concrete, numbered-in-order action
- "expected_result": string describing the specific, checkable expected outcome
- "priority": one of "Low", "Medium", "High", "Critical"

Prioritize safety-relevant and error-condition behavior (e.g. overpressure, \
error codes, alarm thresholds) as High or Critical when the excerpt covers them."""


def build_prompt(selection_text: str) -> str:
    return (
        f"{SYSTEM_INSTRUCTIONS}\n\n"
        f"--- BEGIN MANUAL EXCERPT ---\n{selection_text}\n--- END MANUAL EXCERPT ---\n\n"
        "Return the JSON array now."
    )


def build_retry_prompt(selection_text: str, previous_response: str, validation_error: str) -> str:
    return (
        f"{SYSTEM_INSTRUCTIONS}\n\n"
        f"--- BEGIN MANUAL EXCERPT ---\n{selection_text}\n--- END MANUAL EXCERPT ---\n\n"
        "Your previous response failed validation and could not be used.\n"
        f"Previous response:\n{previous_response}\n\n"
        f"Validation error:\n{validation_error}\n\n"
        "Return ONLY a corrected JSON array satisfying the schema above, and nothing else."
    )
