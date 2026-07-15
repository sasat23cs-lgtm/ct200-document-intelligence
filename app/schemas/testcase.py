from typing import Literal

from pydantic import BaseModel, Field, field_validator

Priority = Literal["Low", "Medium", "High", "Critical"]


class TestCase(BaseModel):
    """A single QA test case as required by the assignment: Title,
    Requirement Reference, Objective, Preconditions, Test Steps, Expected
    Result, Priority. This is the schema every raw LLM response is validated
    against — nothing generated is trusted until it passes this."""

    title: str = Field(..., min_length=1)
    requirement_reference: str = Field(..., min_length=1)
    objective: str = Field(..., min_length=1)
    preconditions: list[str] = Field(default_factory=list)
    test_steps: list[str] = Field(..., min_length=1)
    expected_result: str = Field(..., min_length=1)
    priority: Priority

    @field_validator("preconditions", "test_steps", mode="before")
    @classmethod
    def _coerce_str_to_single_item_list(cls, v):
        # Models occasionally return a single string instead of a list for
        # these fields; coerce rather than hard-fail on this specific shape,
        # since the information is still usable. Anything else is a real
        # validation failure.
        if isinstance(v, str):
            return [v]
        return v


MIN_TEST_CASES = 3
MAX_TEST_CASES = 5
