import argparse
import json

from control_plane import DorothyControlPlane


def main():
    parser = argparse.ArgumentParser(description="DorothyDeploy MVP control plane")
    parser.add_argument("--cluster-name", default="dorothy-mvp")
    parser.add_argument("--model", default="deepseek/deepseek-v3.2")
    parser.add_argument(
        "--recreate-cluster",
        action="store_true",
        help="Delete and recreate the kind cluster before deploying the agent",
    )

    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser(
        "init", help="Create the cluster and deploy the in-cluster agent"
    )

    chat = subcommands.add_parser("chat", help="Send a message to the in-cluster agent")
    chat.add_argument("message")

    args = parser.parse_args()

    try:
        control_plane = DorothyControlPlane(
            cluster_name=args.cluster_name,
            model=args.model,
            recreate_cluster=args.recreate_cluster,
        )

        if args.command == "init":
            print(json.dumps({"ok": True, "cluster": args.cluster_name}, indent=2))
        elif args.command == "chat":
            response = control_plane.send_message(args.message)
            print(json.dumps(response.data, indent=2))
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
