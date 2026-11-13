/**
 * useSocket.js — Real-Time Socket.IO Hook for Network Event Subscriptions.
 */

import { useEffect, useState, useRef, useCallback } from "react";
import { io } from "socket.io-client";

export function useSocket() {
  const [isConnected, setIsConnected] = useState(false);
  const [events, setEvents] = useState([]);
  const [lastEvent, setLastEvent] = useState(null);
  const socketRef = useRef(null);

  useEffect(() => {
    const socket = io("/", {
      transports: ["websocket", "polling"],
      reconnectionAttempts: 10,
      reconnectionDelay: 1000,
    });

    socketRef.current = socket;

    socket.on("connect", () => {
      setIsConnected(true);
      console.log("[Socket.IO] Connected to streaming gateway");
    });

    socket.on("disconnect", () => {
      setIsConnected(false);
      console.log("[Socket.IO] Disconnected from gateway");
    });

    socket.on("connection:ready", (payload) => {
      console.log("[Socket.IO] Handshake ready:", payload);
    });

    const handleIncomingEvent = (eventName) => (envelope) => {
      const eventObj = {
        id: `evt-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`,
        event: eventName,
        timestamp: envelope.timestamp || new Date().toISOString(),
        payload: envelope.payload || envelope,
      };
      setLastEvent(eventObj);
      setEvents((prev) => [eventObj, ...prev].slice(0, 200));
    };

    const subscribedEvents = [
      "incident:created",
      "incident:alert",
      "diagnosis:completed",
      "remediation:approved",
      "remediation:rejected",
      "execution:completed",
      "execution:rolled_back",
      "verification:completed",
      "kill_switch:changed",
    ];

    subscribedEvents.forEach((ev) => {
      socket.on(ev, handleIncomingEvent(ev));
    });

    return () => {
      socket.disconnect();
    };
  }, []);

  const subscribe = useCallback((topic) => {
    if (socketRef.current) {
      socketRef.current.emit("subscribe", { topic });
    }
  }, []);

  const clearEvents = useCallback(() => {
    setEvents([]);
  }, []);

  return {
    isConnected,
    events,
    lastEvent,
    subscribe,
    clearEvents,
  };
}

