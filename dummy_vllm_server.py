#!/usr/bin/env python3
"""Tiny OpenAI-compatible dummy VLM server for local UI testing."""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


STYLE_JSON = {
    "video_type": "local UI test",
    "narrative": "A short creator-style video with simple camera movement and a clear before/after structure.",
    "clothing": "casual outfit with good contrast against the background",
    "setting": "well-lit indoor space",
    "camera_angle": "medium shot, subject centered",
    "key_transition": "none",
    "recreation_tips": "Keep the subject in frame, match the reference timing, and use steady lighting.",
}


def _flatten_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif "text" in item:
                    parts.append(str(item.get("text", "")))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return "" if value is None else str(value)


def _payload_text(payload: dict[str, Any]) -> str:
    messages = payload.get("messages", [])
    if not isinstance(messages, list):
        return ""
    return "\n".join(_flatten_content(msg.get("content")) for msg in messages if isinstance(msg, dict))


def _dummy_completion(payload: dict[str, Any]) -> str:
    text = _payload_text(payload).lower()
    if "merged json" in text or "provide the merged json" in text:
        return json.dumps(STYLE_JSON)
    if "json" in text and any(term in text for term in ("video_type", "clothing", "camera_angle", "style profile")):
        return json.dumps(STYLE_JSON)
    if "pre-flight" in text or "preflight" in text:
        return "Lighting is usable. Keep the subject centered and make the background cleaner."
    if "score" in text or "judge" in text or "critique" in text:
        return "Score: 7/10. Timing and framing are test-ready. Improve lighting and make the ending pose more decisive."
    if "caption" in text or "script" in text:
        return "Hook: Watch the change land on the beat.\nCaption: Testing the TrendFlow edit flow with a clean local mock."
    if "perfect" in text or "directing" in text or "framing" in text:
        return "Hold center, keep the camera steady, and match the reference timing."
    return "Dummy VLM response: local UI test server is reachable."


class DummyVLLMHandler(BaseHTTPRequestHandler):
    server_version = "TrendFlowDummyVLLM/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[dummy-vllm:{self.server.server_port}] {self.address_string()} - {fmt % args}")

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path in ("/", "/health", "/healthz"):
            self._send_json(200, {"status": "ok", "server": "dummy-vllm"})
            return
        if self.path == "/v1/models":
            model = getattr(self.server, "model_name", "dummy-vlm")
            self._send_json(
                200,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": model,
                            "object": "model",
                            "created": int(time.time()),
                            "owned_by": "trendflow-local",
                        }
                    ],
                },
            )
            return
        self._send_json(404, {"error": {"message": f"Unknown path: {self.path}"}})

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self._send_json(404, {"error": {"message": f"Unknown path: {self.path}"}})
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            self._send_json(400, {"error": {"message": f"Invalid JSON: {exc}"}})
            return

        model = payload.get("model") or getattr(self.server, "model_name", "dummy-vlm")
        content = _dummy_completion(payload)
        created = int(time.time())
        self._send_json(
            200,
            {
                "id": f"chatcmpl-dummy-{created}",
                "object": "chat.completion",
                "created": created,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": max(1, len(content.split())),
                    "total_tokens": max(2, len(content.split()) + 1),
                },
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a local dummy vLLM/OpenAI-compatible server.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    parser.add_argument("--model", default="dummy-vlm", help="Served model name")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), DummyVLLMHandler)
    server.model_name = args.model
    print(f"Dummy VLM server listening on http://{args.host}:{args.port}")
    print("OpenAI-compatible endpoint: /v1/chat/completions")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dummy VLM server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
