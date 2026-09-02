from __future__ import annotations

import asyncio
import json
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from control_plane.queue import job_log_channel
from app.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# Global event loop reference for thread-safe broadcasting
_main_event_loop: asyncio.AbstractEventLoop | None = None


def set_main_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Set the main event loop reference for thread-safe broadcasting."""
    global _main_event_loop
    _main_event_loop = loop
    logger.info("Main event loop reference set for WebSocket broadcasting")


def get_main_event_loop() -> asyncio.AbstractEventLoop | None:
    """Get the main event loop reference."""
    return _main_event_loop


import os

@router.websocket("/jobs/{job_id}")
async def job_logs_ws(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    log_path = os.path.join(settings.workspaces_dir, ".queue", "logs", f"{job_id}.log")
    done_marker = f"{log_path}.done"

    # Wait up to 30s for the job log file to be created
    wait_count = 0
    try:
        while not os.path.exists(log_path) and wait_count < 300:
            if os.path.exists(done_marker):
                break
            await asyncio.sleep(0.1)
            wait_count += 1

        if not os.path.exists(log_path):
            await websocket.send_text(f"[api] Job {job_id} is queued or has no logs yet...")
            while not os.path.exists(log_path):
                if os.path.exists(done_marker):
                    break
                await asyncio.sleep(0.5)

        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                idle_ticks = 0
                while True:
                    line = f.readline()
                    if line:
                        idle_ticks = 0
                        await websocket.send_text(line.rstrip("\r\n"))
                    else:
                        if os.path.exists(done_marker):
                            # Drain any remaining lines written before done marker
                            tail_line = f.readline()
                            while tail_line:
                                await websocket.send_text(tail_line.rstrip("\r\n"))
                                tail_line = f.readline()
                            break
                        await asyncio.sleep(0.1)
                        idle_ticks += 1
                        if idle_ticks > 6000:  # 10 minutes timeout on idle
                            break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"WebSocket error for job {job_id}: {e}")


class ConnectionManager:
    def __init__(self):
        # strategy_id -> list[WebSocket]
        self.active_connections: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, strategy_id: str):
        await websocket.accept()
        async with self._lock:
            if strategy_id not in self.active_connections:
                self.active_connections[strategy_id] = []
            self.active_connections[strategy_id].append(websocket)
            logger.info(
                f"WebSocket connected for strategy {strategy_id}. "
                f"Total connections: {len(self.active_connections[strategy_id])}"
            )

    async def disconnect(self, websocket: WebSocket, strategy_id: str):
        async with self._lock:
            if strategy_id in self.active_connections:
                if websocket in self.active_connections[strategy_id]:
                    self.active_connections[strategy_id].remove(websocket)
                if not self.active_connections[strategy_id]:
                    del self.active_connections[strategy_id]
                logger.info(f"WebSocket disconnected for strategy {strategy_id}")

    async def broadcast(self, strategy_id: str, message: dict):
        """Broadcast message to all connections for a strategy."""
        async with self._lock:
            if strategy_id not in self.active_connections:
                logger.debug(f"No active connections for strategy {strategy_id}")
                return
            # Create a copy to avoid modification during iteration
            connections = self.active_connections[strategy_id].copy()

        # Send messages outside the lock
        disconnected = []
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to connection: {e}")
                disconnected.append(connection)

        # Clean up disconnected connections
        if disconnected:
            async with self._lock:
                for connection in disconnected:
                    if strategy_id in self.active_connections:
                        if connection in self.active_connections[strategy_id]:
                            self.active_connections[strategy_id].remove(connection)

    def broadcast_from_thread(self, strategy_id: str, message: dict) -> None:
        """
        Thread-safe broadcast function for use from background threads.

        Args:
            strategy_id: Strategy ID
            message: Message to broadcast
        """
        loop = get_main_event_loop()
        if loop is None or loop.is_closed():
            logger.error("Main event loop not available for broadcasting")
            return

        try:
            future = asyncio.run_coroutine_threadsafe(
                self.broadcast(strategy_id, message),
                loop
            )
            # Wait for result with timeout
            future.result(timeout=1.0)
        except Exception as e:
            logger.error(f"Failed to broadcast from thread: {e}", exc_info=True)


manager = ConnectionManager()


@router.websocket("/strategies/{strategy_id}")
async def strategy_ws(websocket: WebSocket, strategy_id: str):
    await manager.connect(websocket, strategy_id)

    try:
        while True:
            try:
                # Wait for client messages (30 second timeout)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)

                # Handle client messages (like pong reply)
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "pong":
                        logger.debug(f"Received pong from strategy {strategy_id}")
                    else:
                        logger.debug(f"Received message from client: {msg}")
                except json.JSONDecodeError:
                    pass

            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception as e:
                    logger.error(f"Failed to send ping: {e}")
                    break
            except Exception as e:
                logger.error(f"Error receiving WebSocket message: {e}")
                break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for strategy {strategy_id}")
    except Exception as e:
        logger.error(f"Unexpected WebSocket error for strategy {strategy_id}: {e}")
    finally:
        await manager.disconnect(websocket, strategy_id)
