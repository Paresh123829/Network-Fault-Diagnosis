"""
events.py — Real-time event publisher and WebSocket manager for AI service.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["streaming"])


class EventPublisher:
    """
    Central event publisher managing connected WebSocket clients and event distribution.
    Maintains a rolling in-memory buffer of recent events for catch-up/replay.
    """

    def __init__(self, max_history: int = 500) -> None:
        self._active_connections: Set[WebSocket] = set()
        self._client_subscriptions: Dict[WebSocket, Set[str]] = {}
        self._event_history: deque[Dict[str, Any]] = deque(maxlen=max_history)
        self._lock = asyncio.Lock() if asyncio.get_event_loop_policy() else None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._active_connections.add(websocket)
        self._client_subscriptions[websocket] = {"all"}
        logger.info(f"WebSocket client connected. Active connections: {len(self._active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        self._active_connections.discard(websocket)
        self._client_subscriptions.pop(websocket, None)
        logger.info(f"WebSocket client disconnected. Active connections: {len(self._active_connections)}")

    def subscribe(self, websocket: WebSocket, topics: List[str]) -> None:
        if websocket in self._client_subscriptions:
            self._client_subscriptions[websocket].update(topics)

    async def broadcast(self, event_type: str, payload: Dict[str, Any], topic: str = "general") -> Dict[str, Any]:
        """
        Broadcasts an event to all eligible connected WebSocket clients.
        Returns the formatted event dict.
        """
        event = {
            "type": event_type,
            "topic": topic,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }

        self._event_history.append(event)

        stale_connections = []
        for connection in list(self._active_connections):
            subs = self._client_subscriptions.get(connection, set())
            if "all" in subs or topic in subs or event_type in subs:
                try:
                    await connection.send_text(json.dumps(event))
                except Exception as exc:
                    logger.debug(f"Failed to send event to client: {exc}")
                    stale_connections.append(connection)

        for stale in stale_connections:
            self.disconnect(stale)

        return event

    def get_history(self, limit: int = 50, topic: Optional[str] = None) -> List[Dict[str, Any]]:
        events = list(self._event_history)
        if topic and topic != "all":
            events = [e for e in events if e.get("topic") == topic or e.get("type") == topic]
        return events[-limit:]


# Global singleton publisher instance
event_publisher = EventPublisher()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for real-time frontend streaming.
    Supports subscriptions and initial replay.
    """
    await event_publisher.connect(websocket)
    try:
        # Send connection confirmation and initial status
        welcome_event = {
            "type": "connection:ready",
            "topic": "system",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "message": "Connected to CNT AI Streaming Gateway",
                "available_topics": ["incidents", "diagnosis", "remediation", "topology", "kill_switch", "audit"],
            },
        }
        await websocket.send_text(json.dumps(welcome_event))

        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                action = message.get("action")
                if action == "subscribe":
                    topics = message.get("topics", ["all"])
                    event_publisher.subscribe(websocket, topics)
                    await websocket.send_text(json.dumps({
                        "type": "subscription:acknowledged",
                        "topics": topics,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }))
                elif action == "ping":
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }))
                elif action == "get_history":
                    limit = int(message.get("limit", 20))
                    topic = message.get("topic")
                    history = event_publisher.get_history(limit=limit, topic=topic)
                    await websocket.send_text(json.dumps({
                        "type": "history:response",
                        "events": history,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }))
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "error", "message": "Invalid JSON format"}))

    except WebSocketDisconnect:
        event_publisher.disconnect(websocket)
    except Exception as exc:
        logger.warning(f"WebSocket session error: {exc}")
        event_publisher.disconnect(websocket)


@router.get("/events/history", tags=["streaming"])
async def get_recent_events(limit: int = 50, topic: Optional[str] = None) -> Dict[str, Any]:
    """HTTP endpoint to retrieve recent streaming event history."""
    events = event_publisher.get_history(limit=limit, topic=topic)
    return {
        "count": len(events),
        "events": events,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

