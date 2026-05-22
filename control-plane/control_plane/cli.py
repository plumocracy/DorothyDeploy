from __future__ import annotations

import argparse
import json

from control_plane import DorothyControlPlane


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a message to the DorothyDeploy agent")
    parser.add_argument("message", nargs="+", help="Message to send to the in-cluster agent")
    parser.add_argument("--cluster-name", default="dorothy-mvp")
    parser.add_argument("--model", default="openai/gpt-4o-mini")
    parser.add_argument(
        "--recreate-cluster",
        action="store_true",
        help="Delete and recreate the kind cluster before sending the message",
    )
    parser.add_argument("--json", action="store_true", help="Print the full JSON response")
    args = parser.parse_args()

    try:
        control_plane = DorothyControlPlane(
            cluster_name=args.cluster_name,
            model=args.model,
            recreate_cluster=args.recreate_cluster,
        )
        response = control_plane.send_message(" ".join(args.message))

        if args.json:
            print(json.dumps(response.data, indent=2))
        else:
            print(response.data.get("reply", json.dumps(response.data)))
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
