from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")
TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
KUBERNETES_HOST = os.environ["KUBERNETES_SERVICE_HOST"]
KUBERNETES_PORT = os.environ["KUBERNETES_SERVICE_PORT"]


def read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("content-length", "0"))
    if length == 0:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def write_json(
    handler: BaseHTTPRequestHandler,
    status: int,
    payload: dict[str, Any],
) -> None:
    encoded = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json")
    handler.send_header("content-length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


def cluster_health_check() -> dict[str, Any]:
    with open(TOKEN_PATH, "r", encoding="utf-8") as token_file:
        token = token_file.read().strip()

    url = f"https://{KUBERNETES_HOST}:{KUBERNETES_PORT}/version"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    context = ssl.create_default_context(cafile=CA_PATH)

    try:
        with urllib.request.urlopen(request, context=context, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            return {
                "ok": True,
                "api_reachable": True,
                "version": data.get("gitVersion"),
            }
    except Exception as error:
        return {
            "ok": False,
            "api_reachable": False,
            "error": str(error),
        }


def ask_openrouter(message: str, health: dict[str, Any]) -> str:
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an agent running inside a Kubernetes cluster. "
                    "The only tool result you are allowed to use is cluster_health_check. "
                    "Do not claim to inspect, modify, deploy, delete, scale, or access anything else. "
                    "If the user asks for anything outside cluster health, explain that this MVP only supports cluster health checks."
                ),
            },
            {
                "role": "user",
                "content": f"Cluster health tool result: {json.dumps(health)}\n\nUser message: {message}",
            },
        ],
    }
    encoded = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=encoded,
        method="POST",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "content-type": "application/json",
            "http-referer": "https://dorothydeploy.local",
            "x-title": "DorothyDeploy MVP Agent",
        },
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/health":
            write_json(self, 200, {"ok": True, "cluster": cluster_health_check()})
            return
        write_json(self, 404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/chat":
            write_json(self, 404, {"ok": False, "error": "not found"})
            return

        try:
            body = read_json_body(self)
            message = body.get("message")
            if not isinstance(message, str) or not message.strip():
                write_json(self, 400, {"ok": False, "error": "message is required"})
                return

            health = cluster_health_check()
            reply = ask_openrouter(message, health)
            write_json(self, 200, {"ok": True, "reply": reply, "cluster_health": health})
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            write_json(
                self,
                502,
                {
                    "ok": False,
                    "error": f"openrouter error: {error.code}",
                    "detail": detail,
                },
            )
        except Exception as error:
            write_json(self, 500, {"ok": False, "error": str(error)})


def main() -> None:
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()


if __name__ == "__main__":
    main()
