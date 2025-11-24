"""Administrative and diagnostic endpoints."""

import logging
import time
from pathlib import Path

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.deps import verify_api_key
from app.services.memory import memory_manager

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/api")
def api_root():
    """API status endpoint"""
    return {"message": "Sophia AI Backend with DeFi Agent is running."}


@router.get("/status")
def status_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": int(time.time())}


@router.get("/memory/{session_id}")
async def get_memory(
    session_id: str,
    supabase_token: str = Depends(verify_api_key),
):
    """Get conversation memory for a session"""
    try:
        context = memory_manager.get_context_for_llm(
            session_id, access_token=supabase_token
        )

        return {"session_id": session_id, "context": context, "timestamp": time.time()}

    except Exception as e:
        logger.error(f"Failed to get memory for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve memory")


@router.post("/admin/reload-prompts")
async def reload_prompts(
    supabase_token: str = Depends(verify_api_key),
):
    """Hot reload system prompts from disk (Task #42597)"""
    try:
        from app.services.prompt_composer import prompt_composer

        success = prompt_composer.reload_prompts()
        status = prompt_composer.get_reload_status()

        if success:
            return {
                "message": "Prompts reloaded successfully",
                "status": status,
                "timestamp": time.time(),
            }
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "message": "Prompts reload failed or incomplete",
                    "status": status,
                    "timestamp": time.time(),
                },
            )

    except Exception as e:
        logger.error(f"Failed to reload prompts: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to reload prompts: {str(e)}"
        )


@router.get("/admin/memo-metrics")
async def get_memo_metrics(
    supabase_token: str = Depends(verify_api_key),
):
    """Get MemO performance metrics (Task #42597)"""
    try:
        from app.services.memo import memo_client

        metrics = memo_client.get_metrics()

        return {
            "memo_enabled": memo_client.enabled,
            "metrics": metrics,
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"Failed to get MemO metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")


@router.post("/admin/run-migration")
async def run_migration(
    supabase_token: str = Depends(verify_api_key),
):
    """Run user_memories table migration (Task #42597)"""
    try:
        migration_file = Path("user_memories_migration.sql")
        if not migration_file.exists():
            raise HTTPException(status_code=404, detail="Migration file not found")

        # Read migration SQL
        with open(migration_file, "r") as f:
            migration_sql = f.read()

        # Get DB connection string from settings
        settings = get_settings()
        db_dsn = settings.SUPABASE_DB_DSN

        if not db_dsn:
            raise HTTPException(
                status_code=500, detail="SUPABASE_DB_DSN not configured"
            )

        # Execute migration
        conn = psycopg.connect(db_dsn)
        cursor = conn.cursor()

        try:
            cursor.execute(migration_sql)
            conn.commit()

            # Verify table exists
            cursor.execute(
                "SELECT tablename FROM pg_tables WHERE tablename = 'user_memories'"
            )
            result = cursor.fetchone()

            if result:
                # Get table structure
                cursor.execute(
                    """
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = 'user_memories'
                    ORDER BY ordinal_position
                """
                )
                columns = cursor.fetchall()

                return {
                    "message": "Migration executed successfully",
                    "table_exists": True,
                    "columns": [{"name": col[0], "type": col[1]} for col in columns],
                    "timestamp": time.time(),
                }
            else:
                return {
                    "message": "Migration executed but table not found",
                    "table_exists": False,
                    "timestamp": time.time(),
                }

        except Exception as e:
            conn.rollback()
            error_str = str(e).lower()
            if "already exists" in error_str:
                return {
                    "message": "Migration already applied (table exists)",
                    "table_exists": True,
                    "timestamp": time.time(),
                }
            else:
                raise

        finally:
            cursor.close()
            conn.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to run migration: {e}")
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")
