"""Evaluation-related endpoints."""

import logging
import time

from fastapi import APIRouter, Depends, HTTPException

from app.deps import verify_api_key

router = APIRouter(prefix="/evaluation")
logger = logging.getLogger(__name__)


@router.post("/force/{session_id}")
async def force_evaluate_conversation(
    session_id: str,
    supabase_token: str = Depends(verify_api_key),
):
    """Force evaluation of a specific conversation."""
    try:
        from app.services.evaluations import evaluation_manager

        report = evaluation_manager.force_evaluate_conversation(session_id)

        if report is None:
            raise HTTPException(
                status_code=404,
                detail=f"No active conversation found for session {session_id}",
            )

        return {
            "message": "Conversation evaluation completed",
            "session_id": session_id,
            "evaluation_report": {
                "total_messages": report.total_messages,
                "conversation_duration_minutes": round(
                    report.conversation_duration / 60, 2
                ),
                "ragas_average": report.ragas_metrics.average_score
                if report.ragas_metrics
                else None,
                "phoenix_evaluations": len(report.phoenix_metrics),
                "drift_alert": report.drift_alert,
                "confidence_change": f"{report.baseline_confidence:.2f} -> {report.current_confidence:.2f}",
            },
            "timestamp": time.time(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to force evaluate conversation {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to evaluate conversation")


@router.get("/status")
async def get_evaluation_status(
    supabase_token: str = Depends(verify_api_key),
):
    """Get current evaluation system status."""
    try:
        from app.services.evaluations import evaluation_manager

        active_count = evaluation_manager.get_active_conversation_count()

        # Get status of all active conversations
        active_conversations = []
        for session_id in evaluation_manager.active_conversations.keys():
            status = evaluation_manager.get_conversation_status(session_id)
            if status:
                active_conversations.append(status)

        return {
            "active_conversations_count": active_count,
            "active_conversations": active_conversations,
            "conversation_timeout_minutes": evaluation_manager.conversation_timeout
            / 60,
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"Failed to get evaluation status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get evaluation status")


@router.post("/check-finished")
async def check_finished_conversations(
    supabase_token: str = Depends(verify_api_key),
):
    """Manually check for and evaluate finished conversations."""
    try:
        from app.services.evaluations import evaluation_manager

        reports = evaluation_manager.check_and_evaluate_finished_conversations()

        evaluation_summaries = []
        for report in reports:
            evaluation_summaries.append(
                {
                    "session_id": report.session_id,
                    "total_messages": report.total_messages,
                    "conversation_duration_minutes": round(
                        report.conversation_duration / 60, 2
                    ),
                    "ragas_average": report.ragas_metrics.average_score
                    if report.ragas_metrics
                    else None,
                    "phoenix_evaluations": len(report.phoenix_metrics),
                    "drift_alert": report.drift_alert,
                }
            )

        return {
            "message": f"Evaluated {len(reports)} finished conversations",
            "evaluations_completed": len(reports),
            "evaluation_summaries": evaluation_summaries,
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"Failed to check finished conversations: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to check finished conversations"
        )
