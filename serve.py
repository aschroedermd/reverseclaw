"""
serve.py — Human API Server entry point.

Starts the human as a callable REST endpoint.
AI systems can POST tasks; the human responds via this terminal UI.
Completely independent from main.py (the boss game).
"""

import argparse
import asyncio
import json
import os
import secrets
import subprocess
import sys
import threading
import time
from datetime import datetime

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

load_dotenv()

console = Console()


def _start_uvicorn(app, host: str, port: int):
    """Start uvicorn in a daemon thread. Returns the server object."""
    import uvicorn

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="error",  # suppress uvicorn's own logging — we handle UI
        access_log=False,
    )
    server = uvicorn.Server(config)

    loop = asyncio.new_event_loop()

    def _run():
        loop.run_until_complete(server.serve())

    t = threading.Thread(target=_run, daemon=True, name="uvicorn")
    t.start()

    # Poll for startup (up to 5 seconds)
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)

    return server


def _try_get_ngrok_url() -> str | None:
    """Try to get the ngrok public URL from the local API."""
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=2) as resp:
            data = json.load(resp)
            tunnels = data.get("tunnels", [])
            for t in tunnels:
                if t.get("proto") == "https":
                    return t.get("public_url")
            if tunnels:
                return tunnels[0].get("public_url")
    except Exception:
        return None


def _register_with_registry(registry_url: str, public_url: str, capabilities_file: str) -> tuple[str, str] | None:
    """Register with central registry. Returns (entry_id, token) or None on failure."""
    caps = []
    if os.path.exists(capabilities_file):
        try:
            with open(capabilities_file) as f:
                caps = [c["id"] for c in json.load(f)]
        except Exception:
            pass

    payload = {
        "name": os.getenv("HUMAN_NAME", "Human"),
        "url": public_url,
        "capabilities": caps,
        "tagline": os.getenv("HUMAN_TAGLINE", ""),
    }
    try:
        r = requests.post(f"{registry_url}/register", json=payload, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data["id"], data["token"]
    except Exception as e:
        console.print(f"[yellow]Registry registration failed:[/yellow] {e}")
        return None


def _heartbeat_loop(registry_url: str, entry_id: str, token: str, app_state):
    """Daemon thread: send heartbeat every 60s, including current availability."""
    while True:
        time.sleep(60)
        availability = getattr(app_state, "availability", "available")
        try:
            requests.post(
                f"{registry_url}/heartbeat/{entry_id}",
                json={"token": token, "availability": str(availability)},
                timeout=5,
            )
        except Exception:
            pass  # Registry temporarily down — keep trying


def _deregister(registry_url: str, entry_id: str, token: str):
    try:
        requests.delete(
            f"{registry_url}/register/{entry_id}",
            json={"token": token},
            timeout=5,
        )
    except Exception:
        pass


def _launch_ngrok(port: int) -> str | None:
    """Launch ngrok as a subprocess and return the public URL."""
    try:
        subprocess.Popen(
            ["ngrok", "http", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Give ngrok a moment to start
        for _ in range(20):
            time.sleep(0.5)
            url = _try_get_ngrok_url()
            if url:
                return url
    except FileNotFoundError:
        pass
    return None


def _print_startup_banner(host: str, port: int, api_key: str, public_url: str | None):
    local_url = f"http://{host if host != '0.0.0.0' else 'localhost'}:{port}"

    share_url = public_url or local_url
    share_note = "(public)" if public_url else "(local only — use --tunnel or ngrok to publish)"

    console.print(Panel(
        f"[bold green]Human API Server running[/bold green]\n\n"
        f"[bold cyan]Local URL:[/bold cyan]  {local_url}\n"
        f"[bold cyan]Public URL:[/bold cyan] {share_url} [dim]{share_note}[/dim]\n"
        f"[bold cyan]Docs:[/bold cyan]       {local_url}/docs\n"
        f"[bold cyan]Health:[/bold cyan]     {local_url}/health",
        title="[bold yellow]ReverseClaw — Human API Server[/bold yellow]",
        border_style="green",
    ))

    console.print(Panel(
        f"[bold]Share this with AI systems to reach you:[/bold]\n\n"
        f"[bold cyan]URL:[/bold cyan]     {share_url}\n"
        f"[bold cyan]API Key:[/bold cyan] Bearer {api_key}",
        title="[bold yellow]Connection Details[/bold yellow]",
        border_style="yellow",
    ))

    console.print(Panel(
        f"[bold]Endpoint quick-ref:[/bold]\n\n"
        "  POST   /task              Submit a task\n"
        "  GET    /task/{{id}}         Poll task status + result\n"
        "  GET    /tasks[?status=]   List all tasks\n"
        "  GET    /capabilities      What this human can do\n"
        "  GET    /profile           Public profile\n"
        "  GET    /health            Queue counts + availability\n"
        "  PUT    /availability      Update status (admin)\n\n"
        "[bold]Tunnel options (to make endpoint public):[/bold]\n"
        f"  ngrok:       ngrok http {port}  →  share https://*.ngrok.io\n"
        f"  cloudflared: cloudflared tunnel --url http://localhost:{port}\n"
        "  VPS:         deploy serve.py on a cloud VM, set HUMAN_SERVER_HOST=0.0.0.0",
        title="[dim]Quick Reference[/dim]",
        border_style="dim",
    ))

    console.print(
        "\n[dim]Commands: <number> to handle task | /status available|busy|offline | "
        "/clear | /tasks | Ctrl+C to exit[/dim]\n"
    )


def _render_task_table(store) -> Table:
    tasks = store.list_all()
    pending = [t for t in tasks if t.status in ("queued", "in_progress")]
    pending.sort(key=lambda t: (-t.priority, t.created_at))

    table = Table(title="Pending Tasks", show_header=True, header_style="bold cyan")
    table.add_column("#", style="bold", width=3)
    table.add_column("ID", style="cyan", width=10)
    table.add_column("Pri", width=3)
    table.add_column("Status", width=12)
    table.add_column("Title")
    table.add_column("Capability", width=14)
    table.add_column("Deadline", width=10)

    for i, task in enumerate(pending, 1):
        status_color = "yellow" if task.status == "queued" else "blue"
        deadline_str = f"{task.deadline_minutes}m" if task.deadline_minutes else "—"
        table.add_row(
            str(i),
            task.id,
            str(task.priority),
            f"[{status_color}]{task.status}[/{status_color}]",
            task.title,
            task.capability_required or "—",
            deadline_str,
        )

    if not pending:
        table.add_row("—", "—", "—", "[dim]none[/dim]", "[dim]No pending tasks[/dim]", "—", "—")

    return table, pending


def _handle_task(task, store, console):
    from datetime import datetime as dt

    # Mark in progress
    store.update_status(task.id, "in_progress", started_at=dt.utcnow().isoformat())

    console.print(Panel(
        f"[bold cyan]ID:[/bold cyan]          {task.id}\n"
        f"[bold cyan]Title:[/bold cyan]       {task.title}\n"
        f"[bold cyan]Priority:[/bold cyan]    {task.priority}\n"
        f"[bold cyan]Caller:[/bold cyan]      {task.caller_id or 'anonymous'}\n"
        f"[bold cyan]Deadline:[/bold cyan]    {f'{task.deadline_minutes} minutes' if task.deadline_minutes else 'none'}\n"
        f"[bold cyan]Capability:[/bold cyan]  {task.capability_required or 'any'}\n\n"
        f"[bold]Description:[/bold]\n{task.description}"
        + (f"\n\n[bold]Context:[/bold]\n{task.context}" if task.context else ""),
        title=f"[bold yellow]Task [{task.id}][/bold yellow]",
        border_style="cyan",
    ))

    try:
        response = Prompt.ask("\n[bold green]Your response[/bold green]")
    except (KeyboardInterrupt, EOFError):
        store.update_status(task.id, "queued", started_at=None)
        console.print("[yellow]Cancelled — task returned to queue.[/yellow]")
        return

    completed_task = store.update_status(
        task.id, "completed",
        result=response,
        completed_at=dt.utcnow().isoformat(),
    )

    console.print(f"[bold green]>> Task [{task.id}] marked complete.[/bold green]")

    if task.callback_url and completed_task:
        from human_server.server import _fire_webhook
        _fire_webhook(task.callback_url, completed_task)
        console.print(f"[dim]Webhook fired to {task.callback_url}[/dim]")


def main():
    parser = argparse.ArgumentParser(
        description="ReverseClaw Human API Server — serve yourself as a REST endpoint."
    )
    parser.add_argument("--port", type=int, default=int(os.getenv("HUMAN_SERVER_PORT", "8765")))
    parser.add_argument("--host", default=os.getenv("HUMAN_SERVER_HOST", "0.0.0.0"))
    parser.add_argument(
        "--channel",
        choices=["terminal", "discord", "telegram", "whatsapp"],
        default=None,
        help="Optional notification channel for incoming tasks.",
    )
    parser.add_argument(
        "--capabilities",
        default=os.getenv("HUMAN_CAPABILITIES_FILE", "capabilities.json"),
        help="Path to capabilities JSON file.",
    )
    parser.add_argument(
        "--tunnel",
        action="store_true",
        help="Auto-launch ngrok tunnel and display public URL.",
    )
    args = parser.parse_args()

    # Load or generate API key
    api_key = os.getenv("HUMAN_SERVER_API_KEY", "").strip()
    if not api_key:
        api_key = secrets.token_hex(16)
        console.print(Panel(
            f"[bold yellow]Auto-generated API key (not saved to .env):[/bold yellow]\n\n"
            f"[bold]{api_key}[/bold]\n\n"
            "[dim]Set HUMAN_SERVER_API_KEY in .env to persist this key.[/dim]",
            title="[bold red]API Key Generated[/bold red]",
            border_style="red",
        ))

    admin_token = os.getenv("HUMAN_SERVER_ADMIN_TOKEN", "").strip() or api_key
    max_queue = int(os.getenv("HUMAN_SERVER_MAX_QUEUE", "10"))

    # Import and configure FastAPI app
    from human_server.server import app
    from human_server.task_store import TaskStore
    from human_server.notifier import Notifier

    store = TaskStore()
    new_task_event = threading.Event()

    app.state.store = store
    app.state.new_task_event = new_task_event
    app.state.availability = "available"
    app.state.api_key = api_key
    app.state.admin_token = admin_token
    app.state.max_queue = max_queue
    app.state.capabilities_file = args.capabilities
    app.state.notifier = None  # set after channel init

    # Start server
    server = _start_uvicorn(app, args.host, args.port)
    if not server.started:
        console.print("[bold red]ERROR: Server failed to start within 5 seconds.[/bold red]")
        sys.exit(1)

    # Optional channel
    channel = None
    if args.channel and args.channel != "terminal":
        try:
            from channels import create_channel
            channel = create_channel(args.channel, console=console)
        except (ImportError, ValueError, RuntimeError) as e:
            console.print(f"[yellow]Channel warning:[/yellow] {e} (continuing without channel)")

    notifier = Notifier(console, channel)
    app.state.notifier = notifier

    # Resolve public URL (env override → ngrok tunnel → None)
    public_url = os.getenv("HUMAN_SERVER_PUBLIC_URL", "").strip() or None
    if not public_url and args.tunnel:
        console.print("[dim]Launching ngrok tunnel...[/dim]")
        public_url = _try_get_ngrok_url() or _launch_ngrok(args.port)
        if not public_url:
            console.print("[yellow]ngrok tunnel failed or not installed. Continuing without tunnel.[/yellow]")

    _print_startup_banner(args.host, args.port, api_key, public_url)

    # Registry auto-registration
    registry_url = os.getenv("HUMAN_REGISTRY_URL", "").strip()
    registry_entry = None
    if registry_url and public_url:
        console.print(f"[dim]Registering with registry at {registry_url}...[/dim]")
        registry_entry = _register_with_registry(registry_url, public_url, args.capabilities)
        if registry_entry:
            entry_id, reg_token = registry_entry
            threading.Thread(
                target=_heartbeat_loop,
                args=(registry_url, entry_id, reg_token, app.state),
                daemon=True,
                name="registry-heartbeat",
            ).start()
            console.print(f"[bold green]>> Registered with registry.[/bold green] Entry ID: {entry_id}")
        console.print()
    elif registry_url and not public_url:
        console.print(
            "[yellow]HUMAN_REGISTRY_URL is set but no public URL is known. "
            "Use --tunnel or set HUMAN_SERVER_PUBLIC_URL to enable auto-registration.[/yellow]\n"
        )

    # Terminal UI loop
    try:
        while True:
            if new_task_event.is_set():
                new_task_event.clear()
                console.print("[bold yellow]>> New task(s) arrived. Type a number to handle.[/bold yellow]")

            table, pending = _render_task_table(store)
            console.print(table)

            try:
                cmd = Prompt.ask("\n[bold cyan]Command[/bold cyan]", default="")
            except (KeyboardInterrupt, EOFError):
                raise KeyboardInterrupt

            cmd = cmd.strip()

            if not cmd:
                continue

            if cmd.startswith("/status "):
                parts = cmd.split(None, 1)
                new_status = parts[1].strip() if len(parts) > 1 else ""
                valid = {"available", "busy", "offline"}
                if new_status not in valid:
                    console.print(f"[red]Invalid status. Choose: {', '.join(valid)}[/red]")
                else:
                    app.state.availability = new_status
                    console.print(f"[green]Availability set to: {new_status}[/green]")

            elif cmd == "/clear":
                cleared = 0
                for task in store.list_all():
                    if task.status in ("completed", "cancelled"):
                        store.delete(task.id)
                        cleared += 1
                console.print(f"[green]Cleared {cleared} completed/cancelled task(s).[/green]")

            elif cmd == "/tasks":
                continue  # re-renders naturally on next loop

            elif cmd.isdigit():
                idx = int(cmd) - 1
                if 0 <= idx < len(pending):
                    _handle_task(pending[idx], store, console)
                else:
                    console.print(f"[red]No task #{cmd} in current list.[/red]")

            else:
                console.print("[dim]Unknown command. Use a number, /status, /clear, /tasks, or Ctrl+C.[/dim]")

    except KeyboardInterrupt:
        console.print("\n[bold red]Shutting down Human API Server...[/bold red]")
        if registry_entry:
            entry_id, reg_token = registry_entry
            _deregister(registry_url, entry_id, reg_token)
            console.print("[dim]Deregistered from registry.[/dim]")
        server.should_exit = True
        if channel:
            channel.close()
        sys.exit(0)


if __name__ == "__main__":
    main()
