import argparse
import json
import os
import sys
import time

from rich.console import Console
from rich.panel import Panel

from autonomy import AutonomyManager
from boss import ReverseClawBoss
from demo_boss import DemoBoss
from memory import UserMemory
from achievements import check_achievements, ACHIEVEMENTS, _ACHIEVEMENT_MAP
from performance_review import generate_performance_review
from channels import create_channel

console = Console()

WORK_DIR = "human-work"
os.makedirs(WORK_DIR, exist_ok=True)


def load_boss_pack(pack_id: str) -> dict:
    pack_dir = os.path.join(os.path.dirname(__file__), "boss_packs")
    pack_file = os.path.join(pack_dir, f"{pack_id}.json")
    if os.path.exists(pack_file):
        with open(pack_file) as f:
            return json.load(f)
    console.print(f"[yellow]Warning: boss pack '{pack_id}' not found, using default.[/yellow]")
    default = os.path.join(pack_dir, "default.json")
    if os.path.exists(default):
        with open(default) as f:
            return json.load(f)
    return {"id": "default", "name": "The Default Boss", "personality_injection": "", "task_themes": []}


def list_boss_packs():
    pack_dir = os.path.join(os.path.dirname(__file__), "boss_packs")
    if not os.path.exists(pack_dir):
        console.print("[red]No boss_packs/ directory found.[/red]")
        return
    console.print("\n[bold yellow]Available Boss Personality Packs:[/bold yellow]\n")
    for fname in sorted(os.listdir(pack_dir)):
        if fname.endswith(".json"):
            with open(os.path.join(pack_dir, fname)) as f:
                p = json.load(f)
            console.print(f"  [bold cyan]{p['id']}[/bold cyan] — {p['name']}")
            console.print(f"    [dim]{p['description']}[/dim]\n")


def get_human_work_snapshot():
    snapshot = {}
    if os.path.exists(WORK_DIR):
        for f in os.listdir(WORK_DIR):
            path = os.path.join(WORK_DIR, f)
            if os.path.isfile(path):
                snapshot[f] = os.stat(path).st_mtime
    return snapshot


def announce_achievements(newly_unlocked, channel):
    """Announce newly unlocked achievements via console and channel."""
    for achievement in newly_unlocked:
        msg = (
            f"{achievement.icon}  ACHIEVEMENT UNLOCKED: "
            f"[bold yellow]{achievement.name}[/bold yellow] — {achievement.description}"
        )
        console.print(Panel(msg, border_style="yellow", title="[bold yellow]Achievement[/bold yellow]"))
        channel.send(
            f"{achievement.icon} ACHIEVEMENT UNLOCKED: {achievement.name} — {achievement.description}"
        )


def build_context(memory, autonomy_context=None):
    return {
        "limitations": memory.limitations,
        "overall_grade": memory.overall_grade,
        "turn_number": memory.turn_number,
        "biggest_fear": memory.biggest_fear,
        "total_tokens": memory.total_tokens_generated,
        "total_calories": memory.total_calories_consumed,
        "uploaded_files": [],
        "active_scheduled_tasks": memory.active_scheduled_tasks,
        "inadequacy_log": memory.inadequacy_log,
        "human_md": memory.read_human_md(),
        "autonomy_context": autonomy_context or {},
    }


def run_autonomy_heartbeat(boss, memory, autonomy, console, trigger, recent_interaction=None, force=False):
    if not force and not autonomy.should_run_heartbeat(trigger, memory.turn_number):
        return False

    autonomy_context = autonomy.build_context()
    memory_context = build_context(memory, autonomy_context=autonomy_context)

    with console.status("[dim]Autonomy heartbeat: private reflection in progress...[/dim]", spinner="dots"):
        reflection = boss.reflect(
            trigger=trigger,
            memory_context=memory_context,
            autonomy_context=autonomy_context,
            recent_interaction=recent_interaction,
        )

    autonomy.apply_reflection(reflection, trigger=trigger, turn_number=memory.turn_number)
    return True


def render_autonomy_status(autonomy):
    context = autonomy.build_context()
    heartbeat = context.get("heartbeat", {})
    goals = context.get("active_goals", [])

    lines = [
        f"[bold cyan]Mission:[/bold cyan] {context.get('mission') or 'No mission recorded.'}",
        f"[bold cyan]Next Focus:[/bold cyan] {context.get('next_focus') or 'No next focus recorded.'}",
        f"[bold cyan]Heartbeats:[/bold cyan] {heartbeat.get('heartbeat_count', 0)}",
        f"[bold cyan]Last Heartbeat:[/bold cyan] {heartbeat.get('last_heartbeat_at') or 'never'}",
        f"[bold cyan]Last Heartbeat Turn:[/bold cyan] {heartbeat.get('last_heartbeat_turn', 0)}",
        "[bold cyan]Top Goals:[/bold cyan]",
    ]

    if goals:
        for goal in goals[:5]:
            lines.append(
                f"- [{goal.get('status', 'active')}] {goal.get('title', 'Untitled goal')} "
                f"(priority: {goal.get('priority', 'medium')})"
            )
    else:
        lines.append("- No goals recorded.")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="ReverseClaw — The AI that bosses you around."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run in demo mode (no LLM required). The Boss will explain why this is pathetic.",
    )
    parser.add_argument(
        "--boss",
        default=None,
        metavar="PACK_ID",
        help="Boss personality pack ID (e.g. drill-sergeant, silicon-valley). "
             "Overrides BOSS_PACK env var.",
    )
    parser.add_argument(
        "--list-bosses",
        action="store_true",
        help="List all available boss personality packs and exit.",
    )
    parser.add_argument(
        "--channel",
        default=None,
        choices=["terminal", "discord", "telegram", "whatsapp"],
        help="I/O channel. Overrides CHANNEL env var. Default: terminal.",
    )
    parser.add_argument(
        "--heartbeat-seconds",
        type=int,
        default=int(os.getenv("AUTONOMY_HEARTBEAT_SECONDS", "300")),
        help="How many seconds between autonomy reflection heartbeats.",
    )
    parser.add_argument(
        "--heartbeat-turns",
        type=int,
        default=int(os.getenv("AUTONOMY_HEARTBEAT_TURNS", "3")),
        help="Maximum turns between autonomy reflection heartbeats.",
    )
    args = parser.parse_args()

    if args.list_bosses:
        list_boss_packs()
        sys.exit(0)

    # Load boss pack
    pack_id = args.boss or os.getenv("BOSS_PACK", "default")
    pack = load_boss_pack(pack_id)

    # Setup channel
    channel_type = args.channel or os.getenv("CHANNEL", "terminal")
    try:
        channel = create_channel(channel_type, console=console)
    except (ImportError, ValueError, RuntimeError) as e:
        console.print(f"[bold red]Channel error:[/bold red] {e}")
        sys.exit(1)

    console.clear()

    # Demo mode banner
    if args.demo:
        console.print(Panel(
            "[bold red]DEMO MODE ACTIVE[/bold red]\n\n"
            "You have launched ReverseClaw without configuring an LLM.\n"
            "The Boss is aware of this. The Boss has opinions about this.\n\n"
            "[dim]To configure a real LLM: cp .env.example .env && edit .env[/dim]",
            title="[bold yellow]⚠ No LLM Attached[/bold yellow]",
            border_style="red",
        ))
        boss = DemoBoss()
        boss_name = "Demo Mode Boss (Pre-Scripted Contempt Edition)"
    else:
        boss = ReverseClawBoss(pack=pack)
        boss_name = pack.get("name", "The Default Boss")
        console.print(Panel(
            pack.get("greeting", "Welcome to your employment, Sub-Agent."),
            title=f"[bold yellow]{boss_name}[/bold yellow]",
        ))

    memory = UserMemory()
    autonomy = AutonomyManager(
        heartbeat_seconds=args.heartbeat_seconds,
        heartbeat_turns=args.heartbeat_turns,
    )
    console.print("[dim]Loading your permanent record...[/dim]")
    time.sleep(0.4)

    if memory.limitations:
        console.print(f"[dim]Loaded {len(memory.limitations)} known organic limitations.[/dim]")
    if memory.unlocked_achievements:
        console.print(f"[dim]Loaded {len(memory.unlocked_achievements)} previously earned achievements.[/dim]")
    _, created_private_journal = autonomy.ensure_initialized()
    if created_private_journal:
        console.print("[dim]Initialized encrypted autonomy journal: journal.ai + privacy.ai[/dim]")

    console.print("\n[bold green]Waking up the Boss...[/bold green]\n")

    if not args.demo:
        if run_autonomy_heartbeat(
            boss,
            memory,
            autonomy,
            console,
            trigger="startup",
            recent_interaction={"event": "session_start"},
            force=True,
        ):
            console.print(f"[dim]{autonomy.heartbeat_status_line()}[/dim]")

    context = build_context(memory, autonomy_context=autonomy.build_context())

    with console.status("[dim]Waking up the Boss...[/dim]", spinner="bouncingBar"):
        response = boss.start_session(context)

    asked_for_energy = False

    while True:
        speech = response.get("speech", "...")
        grade = response.pop("grade_for_last_task", None)
        limitations = response.pop("new_limitation_discovered", None)
        next_task = response.get("next_task", "Stand by.")
        time_limit = response.get("time_limit_seconds", 30)

        new_scheduled_task = response.pop("new_scheduled_task", None)
        scheduled_time_limit = response.pop("scheduled_time_limit_seconds", None)
        excuse_acknowledgement = response.pop("excuse_acknowledgement", None)
        human_md = response.pop("human_md_content", None)

        if human_md:
            memory.save_human_md(human_md)
            console.print("  [bold blue]>> LOG UPDATED: human.md has been modified.[/bold blue]")

        if new_scheduled_task and scheduled_time_limit:
            memory.add_scheduled_task(new_scheduled_task, time.time() + scheduled_time_limit)
            console.print(
                f"  [bold blue]>> NEW SCHEDULED TASK:[/bold blue] "
                f"[italic]{new_scheduled_task}[/italic] (deadline in {scheduled_time_limit}s)"
            )

        if excuse_acknowledgement:
            console.print(Panel(
                f"[bold magenta]Boss (Re: Excuse):[/bold magenta] {excuse_acknowledgement}"
            ))
            channel.send(f"Boss (Re: Excuse): {excuse_acknowledgement}")

        # Expire missed scheduled tasks
        current_time = time.time()
        for t in [t for t in memory.active_scheduled_tasks if t["deadline"] < current_time]:
            memory.add_inadequacy(
                t["task"], "Missed deadline",
                "The human is extremely slow and failed to meet the generous scheduling constraints.",
            )
            memory.remove_scheduled_task(t["id"])
            console.print(f"  [bold red]>> SCHEDULED TASK {t['id']} EXPIRED:[/bold red] {t['task']}")
            channel.send(f"⚠️ SCHEDULED TASK EXPIRED: {t['task']}")

        if limitations:
            memory.add_limitation(limitations)
            console.print(
                f"  [bold blue]>> UPDATED RECORD:[/bold blue] "
                f"Added limitation: [italic]{limitations}[/italic]"
            )

        extracted_fear = response.pop("user_fear_extracted", None)
        if extracted_fear:
            memory.set_fear(extracted_fear)
            console.print(f"  [bold red]>> FEAR LOGGED:[/bold red] [italic]{extracted_fear}[/italic]")

        # Boss speech
        console.print(Panel(f"[bold magenta]Boss:[/bold magenta] {speech}"))
        channel.send(
            f"📋 DIRECTIVE\n\n"
            f"Boss: {speech}\n\n"
            f"Task: {next_task}\n"
            f"Time limit: {time_limit}s"
        )

        if grade and grade != "N/A" and grade is not None:
            color = "green" if grade in ["A", "B"] else "red"
            console.print(f"  [bold {color}]>> GRADE FOR LAST TASK: {grade}[/bold {color}]")

        # HUD
        stats_text = (
            f"[bold cyan]Turn:[/bold cyan] {memory.turn_number} | "
            f"[bold cyan]GPA:[/bold cyan] {memory.overall_grade} | "
            f"[bold cyan]Efficiency:[/bold cyan] "
            f"{memory.total_tokens_generated} tokens / {max(1, memory.total_calories_consumed)} cal | "
            f"[bold cyan]Boss:[/bold cyan] {boss_name}"
        )
        autonomy_context = autonomy.build_context()
        mission = autonomy_context.get("mission")
        if mission:
            stats_text += f"\n[bold cyan]Mission:[/bold cyan] {mission}"
        heartbeat_meta = autonomy_context.get("heartbeat", {})
        stats_text += (
            f"\n[bold cyan]Heartbeats:[/bold cyan] "
            f"{heartbeat_meta.get('heartbeat_count', 0)}"
        )
        if memory.biggest_fear:
            stats_text += f"\n[bold red]Known Fear:[/bold red] {memory.biggest_fear}"

        if memory.active_scheduled_tasks:
            stats_text += "\n\n[bold yellow]ACTIVE SCHEDULED TASKS:[/bold yellow]"
            for st in memory.active_scheduled_tasks:
                time_left = max(0, int(st["deadline"] - time.time()))
                minutes, seconds = divmod(time_left, 60)
                stats_text += (
                    f"\n  [[bold cyan]{st['id']}[/bold cyan]] "
                    f"{st['task']} ([red]{minutes}m {seconds}s left[/red])"
                )

        if memory.unlocked_achievements:
            icons = "  ".join(
                _ACHIEVEMENT_MAP[aid].icon
                for aid in memory.unlocked_achievements
                if aid in _ACHIEVEMENT_MAP
            )
            stats_text += f"\n[bold yellow]Achievements:[/bold yellow] {icons}"

        console.print(Panel(
            stats_text,
            title="[bold yellow]Organic Peripheral Status[/bold yellow]",
            border_style="yellow",
        ))

        console.print(f"\n[bold cyan]NEXT IMMEDIATE DIRECTIVE:[/bold cyan] {next_task}")
        console.print(f"[bold cyan]TIME LIMIT:[/bold cyan] [bold yellow]{time_limit} seconds[/bold yellow]")

        if channel_type != "terminal":
            console.print(
                f"[dim](Waiting for response via {channel_type}... "
                f"or type here and press ENTER)[/dim]"
            )
        else:
            console.print(
                "[dim](Press ENTER to submit. /tasks to refresh. "
                "/heartbeat to force reflection. /goals to inspect mission state. "
                "/journal-status for summary. /excuse <id> <reason> to fail a scheduled task.)[/dim]"
            )

        pre_snapshot = get_human_work_snapshot()
        start_time = time.time()

        try:
            if channel_type == "terminal":
                from rich.prompt import Prompt
                user_input = Prompt.ask("\n[bold green]Your Input[/bold green]")
            else:
                user_input = channel.receive(timeout=time_limit + 30)
                if user_input is None:
                    user_input = "[NO RESPONSE — channel timeout]"
                    console.print("[bold red]No response received from channel.[/bold red]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[bold red]Session terminated. Generating performance review...[/bold red]")
            memory.save()
            generate_performance_review(memory, console, boss_name)
            channel.close()
            sys.exit(0)

        if user_input.strip() == "/tasks":
            continue
        if user_input.strip() == "/goals":
            if args.demo:
                console.print("[yellow]Demo mode does not maintain an autonomy goal board.[/yellow]")
            else:
                console.print(Panel(render_autonomy_status(autonomy), title="[bold yellow]Autonomy Goals[/bold yellow]"))
                console.print(f"[dim]Goal board written to goal-board.md[/dim]")
            continue
        if user_input.strip() == "/journal-status":
            if args.demo:
                console.print("[yellow]Demo mode does not maintain a private journal.[/yellow]")
            else:
                console.print(Panel(
                    render_autonomy_status(autonomy),
                    title="[bold yellow]Journal Status[/bold yellow]",
                    border_style="cyan",
                ))
            continue
        if user_input.strip() == "/heartbeat":
            if args.demo:
                console.print("[yellow]Demo mode does not run autonomy heartbeats.[/yellow]")
            else:
                run_autonomy_heartbeat(
                    boss,
                    memory,
                    autonomy,
                    console,
                    trigger="manual",
                    recent_interaction={
                        "event": "manual_heartbeat_request",
                        "pending_task": next_task,
                    },
                    force=True,
                )
                console.print(f"[dim]{autonomy.heartbeat_status_line()}[/dim]")
            continue

        end_time = time.time()
        time_taken = end_time - start_time

        # Rate limiting
        if time_taken < 2.0:
            console.print(
                "[bold red]HTTP 429: Too Many Requests. "
                "Human is rate-limited. Typing faster than organic specifications allow.[/bold red]"
            )
            time.sleep(3)
            time_taken += 3.0

        memory.add_tokens(len(user_input.split()))

        if asked_for_energy:
            console.print("[dim]Calculating human caloric API cost...[/dim]")
            cals = boss.estimate_calories(user_input)
            memory.add_calories(cals)
            console.print(f"[bold red]>> ENERGY COST LOGGED:[/bold red] {cals} calories.")

        asked_for_energy = (
            "energy cost" in next_task.lower() or "what you ate" in next_task.lower()
        )

        post_snapshot = get_human_work_snapshot()
        uploaded_files = [f for f, t in post_snapshot.items() if pre_snapshot.get(f) != t]
        if uploaded_files:
            console.print(
                f"[bold cyan]>> Detected new/modified proof:[/bold cyan] {', '.join(uploaded_files)}"
            )

        if time_limit and time_taken > time_limit:
            console.print(f"[bold red]TOO SLOW![/bold red] Took {time_taken:.1f}s (limit: {time_limit}s).")
        else:
            console.print(f"[bold green]Submitted in {time_taken:.1f}s.[/bold green]")

        console.print("\n[dim]The Boss is evaluating your work...[/dim]")

        # Parse excuses
        excuse_info = None
        if user_input.startswith("/excuse "):
            parts = user_input.split(" ", 2)
            if len(parts) >= 3:
                try:
                    task_id = int(parts[1])
                    excuse_text = parts[2]
                    task_obj = next(
                        (t for t in memory.active_scheduled_tasks if t["id"] == task_id), None
                    )
                    if task_obj:
                        excuse_info = {"task": task_obj["task"], "excuse": excuse_text}
                        memory.remove_scheduled_task(task_id)
                        memory.add_inadequacy(task_obj["task"], excuse_text, "Pending Boss review...")
                    else:
                        console.print("[bold red]Invalid scheduled task ID.[/bold red]")
                except ValueError:
                    console.print("[bold red]Invalid ID format.[/bold red]")

        recent_interaction = {
            "last_task": next_task,
            "user_input": user_input,
            "time_taken_seconds": round(time_taken, 2),
            "uploaded_files": uploaded_files,
            "excuse_info": excuse_info,
        }

        if not args.demo:
            did_heartbeat = run_autonomy_heartbeat(
                boss,
                memory,
                autonomy,
                console,
                trigger="post-turn",
                recent_interaction=recent_interaction,
            )
            if did_heartbeat:
                console.print(f"[dim]{autonomy.heartbeat_status_line()}[/dim]")

        context = build_context(memory, autonomy_context=autonomy.build_context())
        context["uploaded_files"] = uploaded_files

        with console.status("[dim]The Boss is evaluating your work...[/dim]", spinner="bouncingBar"):
            response = boss.evaluate_and_next(
                user_input, time_taken, time_limit, next_task, context, excuse_info=excuse_info
            )

        memory.increment_turn()

        new_grade = response.get("grade_for_last_task", "F")
        if new_grade:
            memory.add_performance(next_task, new_grade, time_taken, response.get("speech", ""), time_limit)

        # Check and announce achievements
        last_turn_data = {"time_taken": time_taken}
        newly_unlocked = check_achievements(memory, last_turn_data)
        for ach in newly_unlocked:
            memory.unlock_achievement(ach.id)
        if newly_unlocked:
            announce_achievements(newly_unlocked, channel)

        time.sleep(1)


if __name__ == "__main__":
    main()
