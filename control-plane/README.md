## DorothyDeploy MVP

This MVP creates a local `kind` Kubernetes cluster, deploys a small Python agent inside the cluster, and lets you send arbitrary messages to that agent. The in-cluster agent can only run one tool: a Kubernetes API health check against its own cluster.

Requirements:

- Python project dependencies installed
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

Initialize the cluster and agent:

```sh
python main.py init
```

Startup is idempotent. If the `kind` cluster already exists, the control plane reuses it, exports kubeconfig, and reapplies the agent manifest. To force a clean startup from scratch:

```sh
python main.py --recreate-cluster init
```

Send a message to the in-cluster agent:

```sh
python main.py chat "Is the cluster healthy?"
```

Or use the dedicated chat CLI:

```sh
python -m control_plane.cli "Is the cluster healthy?"
```

Force a fresh cluster before sending the message:

```sh
python -m control_plane.cli --recreate-cluster "Is the cluster healthy?"
```

If the package is installed, the same CLI is available as:

```sh
dorothy-chat "Is the cluster healthy?"
```

Print the full agent response instead of only the reply:

```sh
python -m control_plane.cli --json "Is the cluster healthy?"
```

Python usage:

```python
from control_plane import DorothyControlPlane

control_plane = DorothyControlPlane(openrouter_api_key="...", recreate_cluster=True)
response = control_plane.send_message("Is the cluster healthy?")
print(response.data)
```

The host-side Python process uses `kind` and `kubectl` to create the cluster, deploy the agent, and temporarily port-forward to the in-cluster service for chat requests.

The agent is intentionally constrained. It receives your message, runs its internal cluster health check, and sends only that health result plus your message to OpenRouter.
