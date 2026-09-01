import { useEffect, useRef, useState, useCallback } from 'react';
import { apiBaseUrl } from '../lib/api';

type WebSocketStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

interface UseWebSocketOptions {
    onMessage?: (data: any) => void;
    onConnect?: () => void;
    onDisconnect?: () => void;
    reconnectInterval?: number;
    enabled?: boolean;
}

export function useWebSocket(
    endpoint: string,
    {
        onMessage,
        onConnect,
        onDisconnect,
        reconnectInterval = 5000,
        enabled = true
    }: UseWebSocketOptions = {}
) {
    const [status, setStatus] = useState<WebSocketStatus>('disconnected');
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimeoutRef = useRef<NodeJS.Timeout>();
    const reconnectAttemptsRef = useRef(0);
    const isConnectingRef = useRef(false);  // Prevent concurrent connections
    const maxReconnectAttempts = 5;  // Maximum reconnection attempts

    const connect = useCallback(() => {
        if (!enabled || !endpoint) return;

        // Prevent concurrent connections
        if (isConnectingRef.current) {
            console.log('[WebSocket] Already connecting, skipping...');
            return;
        }

        // Prevent exceeding max reconnect attempts
        if (reconnectAttemptsRef.current >= maxReconnectAttempts) {
            console.error('[WebSocket] Max reconnect attempts reached');
            setStatus('error');
            return;
        }

        // Cleanup existing connection
        if (wsRef.current) {
            wsRef.current.close();
        }

        const baseUrl = apiBaseUrl().replace(/^http/, 'ws');
        const url = `${baseUrl}${endpoint}`;

        console.log('[WebSocket] Connecting to:', url, 'Attempt:', reconnectAttemptsRef.current + 1);
        setStatus('connecting');
        isConnectingRef.current = true;

        try {
            const ws = new WebSocket(url);
            wsRef.current = ws;

            ws.onopen = () => {
                console.log('[WebSocket] Connected to:', url);
                setStatus('connected');
                reconnectAttemptsRef.current = 0;  // Reset on successful connection
                isConnectingRef.current = false;
                onConnect?.();
            };

            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);

                    // Reply to ping messages
                    if (data.type === 'ping') {
                        ws.send(JSON.stringify({ type: 'pong' }));
                        return;
                    }

                    console.log('[WebSocket] Received message:', data);
                    onMessage?.(data);
                } catch (e) {
                    console.error('[WebSocket] Failed to parse message:', e, 'Raw:', event.data);
                }
            };

            ws.onclose = (event) => {
                console.log('[WebSocket] Disconnected. Code:', event.code, 'Reason:', event.reason);
                setStatus('disconnected');
                isConnectingRef.current = false;
                onDisconnect?.();
                wsRef.current = null;

                // Smart reconnection: only reconnect on abnormal closure
                if (enabled && event.code !== 1000) {  // 1000 = normal closure
                    if (reconnectAttemptsRef.current < maxReconnectAttempts) {
                        reconnectAttemptsRef.current += 1;
                        // Exponential backoff: 5s, 10s, 20s, 40s, 60s
                        const delay = Math.min(
                            reconnectInterval * Math.pow(2, reconnectAttemptsRef.current - 1),
                            60000  // Max 60 seconds
                        );
                        console.log('[WebSocket] Reconnecting in', delay, 'ms (attempt', reconnectAttemptsRef.current, ')');
                        reconnectTimeoutRef.current = setTimeout(() => {
                            connect();
                        }, delay);
                    } else {
                        console.error('[WebSocket] Max reconnect attempts reached');
                        setStatus('error');
                    }
                }
            };

            ws.onerror = (error) => {
                console.error('[WebSocket] Error:', error);
                setStatus('error');
                isConnectingRef.current = false;
            };

        } catch (error) {
            console.error('WebSocket connection failed:', error);
            setStatus('error');
            isConnectingRef.current = false;
        }
    }, [endpoint, enabled, reconnectInterval]);  // Removed callback dependencies

    useEffect(() => {
        if (enabled) {
            connect();
        }

        return () => {
            // Normal closure when component unmounts
            if (wsRef.current) {
                wsRef.current.close(1000, 'Component unmounting');
            }
            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
            }
            isConnectingRef.current = false;
            reconnectAttemptsRef.current = 0;
        };
    }, [endpoint, enabled]);  // Only depend on stable values

    const sendMessage = (data: any) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify(data));
        } else {
            console.warn('WebSocket not connected, cannot send message');
        }
    };

    return { status, sendMessage };
}
