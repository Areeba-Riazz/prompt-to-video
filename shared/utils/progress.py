import asyncio
from shared.utils.logger import get_logger

logger = get_logger("ProgressUtil")

def report_progress(phase: str, step: str, status: str, details: str = ""):
    """
    Synchronous helper to report progress via the WebSocket manager.
    Uses asyncio.run_coroutine_threadsafe if a loop is running.
    """
    from backend.websocket.manager import progress_manager
    
    # Try to find a loop to use
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # We are in a sync thread, try to get the loop from the manager
        loop = getattr(progress_manager, 'loop', None)

    if loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(
            progress_manager.send_progress(phase, step, status, details),
            loop
        )
    else:
        logger.warning(f"⚠️ [Progress] No running event loop found to report: {step}")
