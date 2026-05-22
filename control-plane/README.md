## DorothyDeploy Go Control Plane

This MVP runs a Go HTTP control plane that creates a local `kind` Kubernetes cluster, deploys a small Python agent inside the cluster, and lets you send arbitrary messages to that agent. The in-cluster agent can only run one tool: a Kubernetes API health check against its own cluster.

Requirements:

- Go installed
- Docker running
- `kind` installed
- `kubectl` installed
- `OPENROUTER_API_KEY` set

You can set the OpenRouter API key in your shell:

```sh
export OPENROUTER_API_KEY="..."
```

Or put it in a local `.env` file:

```sh
OPENROUTER_API_KEY="..."
```

Start the Go control plane:

```sh
go run ./cmd/control-plane
```

The server listens on `127.0.0.1:5000` by default. Override that with `CONTROL_PLANE_HOST` and `CONTROL_PLANE_PORT`.

Check the control plane:

```sh
curl http://127.0.0.1:5000/health
```

Initialize the cluster and agent:

```sh
curl -X POST http://127.0.0.1:5000/init \
  -H 'content-type: application/json' \
  -d '{}'
```

Startup is idempotent. If the `kind` cluster already exists, the control plane reuses it, exports kubeconfig, and reapplies the agent manifest. To force a clean startup from scratch:

```sh
curl -X POST http://127.0.0.1:5000/init \
  -H 'content-type: application/json' \
  -d '{"recreate_cluster": true}'
```

Send a message to the in-cluster agent:

```sh
curl -X POST http://127.0.0.1:5000/chat \
  -H 'content-type: application/json' \
  -d '{"message": "Is the cluster healthy?"}'
```

Use a specific model or cluster name:

```sh
curl -X POST http://127.0.0.1:5000/chat \
  -H 'content-type: application/json' \
  -d '{"message": "Is the cluster healthy?", "model": "deepseek/deepseek-v3.2", "cluster_name": "dorothy-mvp"}'
```

The dedicated Go chat CLI is also available:

```sh
go run ./cmd/dorothy-chat -- "Is the cluster healthy?"
```

Print the full agent response instead of only the reply:

```sh
go run ./cmd/dorothy-chat --json -- "Is the cluster healthy?"
```

Force a fresh cluster before sending the message:

```sh
go run ./cmd/dorothy-chat --recreate-cluster -- "Is the cluster healthy?"
```

The host-side Go control plane uses `kind` and `kubectl` to create the cluster, deploy the agent, and temporarily port-forward to the in-cluster service for chat requests.

The deployed agent code lives at `internal/controlplane/assets/agent.py` and is embedded into the Go binary. It receives your message, runs its internal cluster health check, and sends only that health result plus your message to OpenRouter.
