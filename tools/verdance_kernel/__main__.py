"""python -m verdance_kernel [launch|serve|status|rebuild|surface|phases|ship|sync-mod]"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Ensure tools/ is on path when run as module from elsewhere
_TOOLS = Path(__file__).resolve().parent.parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(prog="verdance_kernel", description="Verdance campaign kernel")
    ap.add_argument(
        "command",
        nargs="?",
        default="launch",
        choices=[
            "launch",
            "serve",
            "status",
            "rebuild",
            "surface",
            "phases",
            "ship",
            "sync-mod",
        ],
        help="launch=product entry (default), serve=HTTP only, ship=export/dist",
    )
    ap.add_argument("--workspace", default=None)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--no-ui", action="store_true")
    ap.add_argument("--browser", action="store_true")
    ap.add_argument("--no-bridge", action="store_true")
    ap.add_argument(
        "--no-rebuild",
        action="store_true",
        help="launch: skip hub rebuild so the last debrief is not painted again",
    )
    ap.add_argument("--no-browser", action="store_true", help="serve: do not open browser")
    ap.add_argument("--skip-python", action="store_true", help="ship: do not embed Python")
    ap.add_argument("--skip-zip", action="store_true", help="ship: folder only")
    ap.add_argument("--my-games", action="store_true", help="ship: also install full dist to My Games")
    args = ap.parse_args(argv)

    if args.command == "launch":
        from verdance_kernel.launcher import launch

        return launch(
            args.workspace,
            host=args.host,
            port=args.port,
            no_ui=args.no_ui,
            prefer_browser=args.browser,
            enable_bridge=not args.no_bridge,
            rebuild=not args.no_rebuild,
        )

    if args.command == "serve":
        from verdance_kernel.server import serve

        return serve(
            args.workspace,
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
            enable_bridge=not args.no_bridge,
        )

    from verdance_kernel.api import CampaignKernel
    from verdance_kernel.paths import resolve_workspace

    k = CampaignKernel(args.workspace)

    if args.command == "status":
        print(json.dumps(k.status(), indent=2))
        return 0
    if args.command == "rebuild":
        print(json.dumps(k.rebuild_hub(), indent=2))
        return 0
    if args.command == "surface":
        print(json.dumps(k.write_campaign_surface(), indent=2))
        return 0
    if args.command == "phases":
        from verdance_kernel.phases import phase_status

        print(json.dumps(phase_status(), indent=2))
        return 0
    if args.command == "sync-mod":
        print(json.dumps(k.sync_mod(copy=True), indent=2))
        return 0 if k._last_mod_sync and k._last_mod_sync.get("ok") else 1
    if args.command == "ship":
        ws = resolve_workspace(args.workspace)
        script = ws / "scripts" / "ship.ps1"
        if not script.is_file():
            print(f"missing {script}", file=sys.stderr)
            return 2
        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Workspace",
            str(ws),
        ]
        if args.skip_python:
            cmd.append("-SkipPython")
        if args.skip_zip:
            cmd.append("-SkipZip")
        if args.my_games:
            cmd.append("-InstallToMyGames")
        return subprocess.call(cmd, cwd=str(ws))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
