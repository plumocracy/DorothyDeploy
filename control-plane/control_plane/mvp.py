from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv


load_dotenv()


AGENT_SCRIPT = r'''
import json
import os
import ssl
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")
TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
KUBERNETES_HOST = os.environ["KUBERNETES_SERVICE_HOST"]
KUBERNETES_PORT = os.environ["KUBERNETES_SERVICE_PORT"]


def read_json_body(handler):
    length = int(handler.headers.get("content-length", "0"))
    if length == 0:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def write_json(handler, status, payload):
    encoded = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json")
    handler.send_header("content-length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


def cluster_health_check():
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


def ask_openrouter(message, health):
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
            "authorization": f"Bearer {OPENROUTER_API_KEY}",
            "content-type": "application/json",
            "http-referer": "https://dorothydeploy.local",
            "x-title": "DorothyDeploy MVP Agent",
        },
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        if self.path == "/health":
            write_json(self, 200, {"ok": True, "cluster": cluster_health_check()})
            return
        write_json(self, 404, {"ok": False, "error": "not found"})

    def do_POST(self):
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
            write_json(self, 502, {"ok": False, "error": f"openrouter error: {error.code}", "detail": detail})
        except Exception as error:
            write_json(self, 500, {"ok": False, "error": str(error)})


ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
'''


@dataclass(frozen=True)
class AgentResponse:
    ok: bool
    data: dict[str, Any]


class DorothyControlPlane:
    def __init__(
        self,
        openrouter_api_key: str | None = None,
        cluster_name: str = "dorothy-mvp",
        model: str = "openai/gpt-4o-mini",
        recreate_cluster: bool = False,
    ) -> None:
        self.openrouter_api_key = openrouter_api_key or os.environ.get("OPENROUTER_API_KEY")
        self.cluster_name = cluster_name
        self.model = model
        self.recreate_cluster = recreate_cluster

        if not self.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY is required")

        self.initialize()

    def initialize(self) -> None:
        self._ensure_command("kind")
        self._ensure_command("kubectl")
        self._ensure_cluster()
        self._deploy_agent()

    def send_message(self, message: str, local_port: int = 18080) -> AgentResponse:
        if not message.strip():
            raise ValueError("message is required")

        with self._port_forward(local_port):
            payload = json.dumps({"message": message}).encode("utf-8")
            request = urllib.request.Request(
                f"http://127.0.0.1:{local_port}/chat",
                data=payload,
                method="POST",
                headers={"content-type": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    return AgentResponse(ok=bool(data.get("ok")), data=data)
            except urllib.error.HTTPError as error:
                data = json.loads(error.read().decode("utf-8"))
                return AgentResponse(ok=False, data=data)

    def _ensure_cluster(self) -> None:
        result = subprocess.run(
            ["kind", "get", "clusters"],
            check=True,
            capture_output=True,
            text=True,
        )
        clusters = set(result.stdout.splitlines())
        if self.recreate_cluster and self.cluster_name in clusters:
            subprocess.run(["kind", "delete", "cluster", "--name", self.cluster_name], check=True)
            clusters.remove(self.cluster_name)

        if self.cluster_name not in clusters:
            subprocess.run(["kind", "create", "cluster", "--name", self.cluster_name], check=True)

        subprocess.run(["kind", "export", "kubeconfig", "--name", self.cluster_name], check=True)

    def _deploy_agent(self) -> None:
        subprocess.run(
            ["kubectl", "--context", self._context_name, "apply", "-f", "-"],
            input=self._agent_manifest(),
            text=True,
            check=True,
        )

        subprocess.run(
            [
                "kubectl",
                "--context",
                self._context_name,
                "-n",
                "dorothy-system",
                "rollout",
                "status",
                "deployment/dorothy-agent",
                "--timeout=180s",
            ],
            check=True,
        )

    def _agent_manifest(self) -> str:
        escaped_script = "\n".join(f"    {line}" for line in AGENT_SCRIPT.splitlines())
        return f"""
apiVersion: v1
kind: Namespace
metadata:
  name: dorothy-system
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: dorothy-agent
  namespace: dorothy-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: dorothy-agent-health
rules:
  - nonResourceURLs:
      - /version
    verbs:
      - get
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: dorothy-agent-health
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: dorothy-agent-health
subjects:
  - kind: ServiceAccount
    name: dorothy-agent
    namespace: dorothy-system
---
apiVersion: v1
kind: Secret
metadata:
  name: dorothy-agent-openrouter
  namespace: dorothy-system
type: Opaque
stringData:
  OPENROUTER_API_KEY: {json.dumps(self.openrouter_api_key)}
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: dorothy-agent-code
  namespace: dorothy-system
data:
  agent.py: |
{escaped_script}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dorothy-agent
  namespace: dorothy-system
spec:
  replicas: 1
  selector:
    matchLabels:
      app: dorothy-agent
  template:
    metadata:
      labels:
        app: dorothy-agent
    spec:
      serviceAccountName: dorothy-agent
      containers:
        - name: agent
          image: python:3.12-slim
          imagePullPolicy: IfNotPresent
          command:
            - python
            - /app/agent.py
          env:
            - name: OPENROUTER_API_KEY
              valueFrom:
                secretKeyRef:
                  name: dorothy-agent-openrouter
                  key: OPENROUTER_API_KEY
            - name: OPENROUTER_MODEL
              value: {json.dumps(self.model)}
          ports:
            - name: http
              containerPort: 8080
          volumeMounts:
            - name: code
              mountPath: /app
      volumes:
        - name: code
          configMap:
            name: dorothy-agent-code
---
apiVersion: v1
kind: Service
metadata:
  name: dorothy-agent
  namespace: dorothy-system
spec:
  selector:
    app: dorothy-agent
  ports:
    - name: http
      port: 8080
      targetPort: http
""".strip()

    @property
    def _context_name(self) -> str:
        return f"kind-{self.cluster_name}"

    def _port_forward(self, local_port: int):
        return PortForward(
            [
                "kubectl",
                "--context",
                self._context_name,
                "-n",
                "dorothy-system",
                "port-forward",
                "service/dorothy-agent",
                f"{local_port}:8080",
            ],
            local_port,
        )

    @staticmethod
    def _ensure_command(command: str) -> None:
        if shutil.which(command) is None:
            raise RuntimeError(f"required command not found: {command}")


class PortForward:
    def __init__(self, command: list[str], local_port: int) -> None:
        self.command = command
        self.local_port = local_port
        self.process: subprocess.Popen[str] | None = None

    def __enter__(self):
        self.process = subprocess.Popen(
            self.command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        deadline = time.time() + 15
        while time.time() < deadline:
            if self.process.poll() is not None:
                output = self.process.stdout.read() if self.process.stdout else ""
                raise RuntimeError(f"port-forward exited early: {output}")

            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.local_port}/health", timeout=1):
                    return self
            except Exception:
                time.sleep(0.25)

        raise RuntimeError("timed out waiting for port-forward")

    def __exit__(self, exc_type, exc, tb):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
