"""P02 storage checkpoint; this is not a completed council state machine."""
from typing import Annotated, Literal

from pydantic import Field

from consilium.core.contracts import Contract, Identifier, Revision


class StorageCheckpoint(Contract):
    debate_id: Identifier
    revision: Revision
    event_sequence: Annotated[int, Field(ge=1)]
    event_kind: Literal["DEBATE_CREATED", "ROUND_REGISTERED", "CONNECTION_BOUND", "OPERATION_PREPARED",
                        "SEND_STARTED", "SEND_INTERRUPTED", "RESULT_RECORDED", "RESULT_REJECTED",
                        "RESPONSE_VALIDATED", "RESULT_CONFIRMED", "WAITING_DECISION", "USER_DECISION", "RETRY_PREPARED", "QUESTION_ADOPTED", "CONTEXT_SOURCE_PUBLISHED"]
