"""
registry.py — ReverseClaw Human Registry Server

A discovery registry where human endpoints register themselves so AI systems
can find them. Deploy this once on a persistent server (Fly.io, Railway, Render,
or any VPS). Human endpoints auto-register via HUMAN_REGISTRY_URL in their .env.

Usage:
    python registry.py                # default: 0.0.0.0:8766
    python registry.py --port 8766
    python registry.py --host 0.0.0.0

Deployment (Fly.io example):
    fly launch --name reverseclaw-registry
    fly deploy

Deployment (Railway / Render):
    Point to this repo, set start command: python registry.py
    Set PORT env var if needed (--port reads it automatically).
"""

import argparse
import os
import sys

import uvicorn
from rich.console import Console
from rich.panel import Panel

console = Console()


def main():
    parser = argparse.ArgumentParser(
        description="ReverseClaw Human Registry — discovery service for human API endpoints."
    )
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8766")))
    parser.add_argument("--host", default=os.getenv("REGISTRY_HOST", "0.0.0.0"))
    args = parser.parse_args()

    from registry_server.server import app
    from registry_server.store import RegistryStore

    app.state.store = RegistryStore()

    local = f"http://{'localhost' if args.host == '0.0.0.0' else args.host}:{args.port}"

    console.print(Panel(
        f"[bold green]Human Registry running[/bold green]\n\n"
        f"[bold cyan]URL:[/bold cyan]    {local}\n"
        f"[bold cyan]Docs:[/bold cyan]   {local}/docs\n"
        f"[bold cyan]Humans:[/bold cyan] {local}/humans\n"
        f"[bold cyan]Health:[/bold cyan] {local}/health\n\n"
        "[bold]Human endpoints:[/bold] set HUMAN_REGISTRY_URL in their .env\n"
        "[bold]AI systems:[/bold]      GET /humans?capability=research to find available humans\n\n"
        "[dim]Deploy to Fly.io, Railway, or Render for a persistent public registry.\n"
        "See CLAUDE.md for deployment instructions.[/dim]",
        title="[bold yellow]ReverseClaw — Human Registry[/bold yellow]",
        border_style="green",
    ))

    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    except KeyboardInterrupt:
        console.print("\n[bold red]Registry shutting down.[/bold red]")
        sys.exit(0)


if __name__ == "__main__":
    main()
