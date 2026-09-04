"""AI explanation endpoints.

The assistant explains a stored valuation. It never values a car, and it never
sees anything the server did not load from the database itself.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from echte_auto_waarde.ai.factory import get_ai_provider
from echte_auto_waarde.ai.provider import AIProvider
from echte_auto_waarde.db.session import get_session
from echte_auto_waarde.schemas.valuation import (
    AiChatRead,
    AiChatRequest,
    AiSuggestionsRead,
)
from echte_auto_waarde.services.ai import answer_question, build_context, load_valuation_for_ai

router = APIRouter(prefix="/ai", tags=["ai"])

# An unavailable model is a 200 with available=false; only a missing
# valuation is an error here.
NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"description": "No such valuation."}}


def _require_valuation(session: Session, valuation_id: int):
    valuation = load_valuation_for_ai(session, valuation_id)
    if valuation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Valuation {valuation_id} not found.",
        )
    return valuation


@router.post("/chat", response_model=AiChatRead, responses=NOT_FOUND)
def chat(
    request: AiChatRequest,
    session: Session = Depends(get_session),
    provider: AIProvider = Depends(get_ai_provider),
) -> AiChatRead:
    """Answer one question about one valuation.

    An unavailable model is a normal outcome, not an error: the response says so
    and the valuation page keeps working.
    """
    valuation = _require_valuation(session, request.valuation_id)
    result = answer_question(session, valuation, request.message, provider)

    return AiChatRead(
        available=result.available,
        provider=result.provider,
        model=result.model,
        answer=result.answer,
        grounded=result.grounded,
        grounding_note=result.grounding_note,
        unavailable_reason=result.unavailable_reason,
    )


@router.get(
    "/valuations/{valuation_id}/suggestions",
    response_model=AiSuggestionsRead,
    responses=NOT_FOUND,
)
def suggestions(
    valuation_id: int,
    session: Session = Depends(get_session),
    provider: AIProvider = Depends(get_ai_provider),
) -> AiSuggestionsRead:
    """Example questions this particular valuation can answer.

    Derived from the stored evidence, so the interface never invites a question
    whose honest answer would be that the data does not cover it.
    """
    valuation = _require_valuation(session, valuation_id)
    context = build_context(session, valuation)

    return AiSuggestionsRead(
        available=provider.is_available(),
        provider=provider.name,
        model=provider.model,
        questions=context.supported_questions(),
    )
