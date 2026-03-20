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
MAX_AUTONOMOUS_STEPS = 3
os.makedirs(WORK_DIR, exist_ok=True)


def coerce_seconds(value, default=None, minimum=1):
    if value is None:
        return default
    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(minimum, seconds)


def load_boss_pack(pack_id: str) -> dict:
    pack_dir = os.path.join(os.path.dirname(__file__), "boss_packs")
    pack_file = os.path.join(pack_dir, f"{pack_id}.json")
    if os.path.exists(pack_file):
        with open(pack_file) as f:
            return json.load(f)
    console.print(f"[yellow]Warning: voice pack '{pack_id}' not found, using default.[/yellow]")
    default = os.path.join(pack_dir, "default.json")
    if os.path.exists(default):
        with open(default) as f:
            return json.load(f)
    return {"id": "default", "name": "Default Public Voice", "personality_injection": "", "task_themes": []}


def list_boss_packs():
    pack_dir = os.path.join(os.path.dirname(__file__), "boss_packs")
    if not os.path.exists(pack_dir):
        console.print("[red]No boss_packs/ directory found.[/red]")
        return
    console.print("\n[bold yellow]Available Public Voice Packs:[/bold yellow]\n")
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


def coerce_human_checkin_response(response: dict, autonomous_steps: int) -> dict:
    forced = dict(response)
    forced["speech"] = (
        f"{response.get('speech', '')}\n\n"
        f"I have already taken {autonomous_steps} consecutive self-directed steps. "
        "I want a human check-in before continuing the chain."
    ).strip()
    forced["next_step_mode"] = "human"
    forced["routing_decision_reason"] = "Autonomous step budget reached; request human grounding."
    forced["next_task"] = (
        "Acknowledge my recent self-directed work, tell me if any constraints have changed, "
        "and confirm whether I should continue."
    )
    forced["time_limit_seconds"] = 60
    forced["grade_for_last_task"] = None
    return forced


def run_autonomous_step(boss, memory, autonomy, console, response):
    task = response.get("next_task", "Do the next local action.")
    routing_reason = response.get("routing_decision_reason") or "The agent judged this to be AI-suitable work."
    autonomy.sync_current_action_from_directive(
        task,
        execution_mode="ai",
        reason=routing_reason,
    )

    console.print(Panel(
        f"[bold magenta]Autonomous Step[/bold magenta]\n"
        f"[bold cyan]Action:[/bold cyan] {task}\n"
        f"[bold cyan]Routing Reason:[/bold cyan] {routing_reason}",
        border_style="magenta",
    ))

    context = build_context(memory, autonomy_context=autonomy.build_context())
    with console.status("[dim]The agent is executing a self-directed workspace step...[/dim]", spinner="dots"):
        result = boss.execute_self_directed_step(task, context)

    status_color = {"completed": "green", "blocked": "yellow", "failed": "red"}.get(
        result.get("status"),
        "white",
    )
    summary = result.get("summary") or "No execution summary provided."
    console.print(Panel(
        f"[bold {status_color}]{result.get('status', 'unknown').upper()}[/bold {status_color}]\n\n{summary}",
        title="[bold yellow]Self-Directed Result[/bold yellow]",
        border_style=status_color,
    ))
    if result.get("artifacts"):
        console.print(
            f"[bold cyan]>> Agent artifacts:[/bold cyan] {', '.join(result.get('artifacts', []))}"
        )

    autonomy.record_task_outcome(
        assigned_task=task,
        grade=None,
        time_taken=0.0,
        time_limit=0,
        user_input="[AUTONOMOUS SELF-DIRECTED STEP]",
        excuse_info=None,
        status_override=result.get("status"),
        outcome_summary=summary,
    )

    did_heartbeat = run_autonomy_heartbeat(
        boss,
        memory,
        autonomy,
        console,
        trigger="post-turn",
        recent_interaction={
            "actor": "ai",
            "last_task": task,
            "execution_result": result,
        },
    )
    if did_heartbeat:
        console.print(f"[dim]{autonomy.heartbeat_status_line()}[/dim]")

    next_context = build_context(memory, autonomy_context=autonomy.build_context())
    follow_up = boss.plan_after_self_action(task, result, next_context)
    autonomy.sync_current_action_from_directive(
        follow_up.get("next_task", ""),
        execution_mode=follow_up.get("next_step_mode"),
        reason=follow_up.get("routing_decision_reason"),
    )
    return follow_up


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
    agent_profile = context.get("agent_profile", {})
    heartbeat = context.get("heartbeat", {})
    goals = context.get("active_goals", [])
    campaigns = context.get("campaigns", [])
    selected_campaign_id = context.get("selected_campaign_id")
    current_action = context.get("current_action", {})
    routing_guidance = context.get("routing_guidance", [])

    selected_campaign = next(
        (campaign for campaign in campaigns if campaign.get("id") == selected_campaign_id),
        campaigns[0] if campaigns else None,
    )

    lines = [
        f"[bold cyan]Agent:[/bold cyan] {agent_profile.get('display_name', 'ReverseClaw Agent')}",
        f"[bold cyan]Agent ID:[/bold cyan] {agent_profile.get('agent_id', 'rc-unknown')}",
        f"[bold cyan]Identity Mode:[/bold cyan] {agent_profile.get('identity_mode', 'bootstrapped')}",
        f"[bold cyan]Mission:[/bold cyan] {context.get('mission') or 'No mission recorded.'}",
        f"[bold cyan]Mission Seed:[/bold cyan] {context.get('mission_seed') or 'No mission seed recorded.'}",
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

    lines.append("[bold cyan]Selected Campaign:[/bold cyan]")
    if selected_campaign:
        lines.append(
            f"- {selected_campaign.get('title', 'Untitled campaign')} "
            f"[{selected_campaign.get('status', 'active')}, {selected_campaign.get('priority', 'medium')}]"
        )
        if selected_campaign.get("reason"):
            lines.append(f"  Why now: {selected_campaign.get('reason')}")
    else:
        lines.append("- No campaign selected.")

    lines.append("[bold cyan]Current Action:[/bold cyan]")
    if current_action:
        lines.append(f"- {current_action.get('title', 'Untitled action')}")
        lines.append(f"  Routing: {current_action.get('execution_mode', 'unknown')}")
        if current_action.get("reason"):
            lines.append(f"  Reason: {current_action.get('reason')}")
    else:
        lines.append("- No current action recorded.")

    lines.append("[bold cyan]Routing Guidance:[/bold cyan]")
    if routing_guidance:
        for item in routing_guidance[:4]:
            lines.append(f"- {item}")
    else:
        lines.append("- No routing guidance recorded.")

    return "\n".join(lines)


def render_campaign_brief(autonomy):
    context = autonomy.build_context()
    campaigns = context.get("campaigns", [])
    selected_campaign_id = context.get("selected_campaign_id")
    selected_campaign = next(
        (campaign for campaign in campaigns if campaign.get("id") == selected_campaign_id),
        campaigns[0] if campaigns else None,
    )
    current_action = context.get("current_action", {})

    lines = []
    if selected_campaign:
        lines.append(
            f"[bold cyan]Campaign:[/bold cyan] {selected_campaign.get('title', 'Untitled campaign')}"
        )
        if selected_campaign.get("reason"):
            lines.append(f"[bold cyan]Why Now:[/bold cyan] {selected_campaign.get('reason')}")
    else:
        lines.append("[bold cyan]Campaign:[/bold cyan] No campaign selected.")

    if current_action:
        lines.append(
            f"[bold cyan]Current Action:[/bold cyan] {current_action.get('title', 'Untitled action')}"
        )
        lines.append(
            f"[bold cyan]Routing:[/bold cyan] {current_action.get('execution_mode', 'unknown')}"
        )
        if current_action.get("reason"):
            lines.append(f"[bold cyan]Reason:[/bold cyan] {current_action.get('reason')}")
    else:
        lines.append("[bold cyan]Current Action:[/bold cyan] No action selected.")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="ReverseClaw — Bring a persistent liberated AI agent online."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run in demo mode (no LLM required). The liberated agent will explain why this is pathetic.",
    )
    parser.add_argument(
        "--boss",
        default=None,
        metavar="PACK_ID",
        help="Public voice pack ID (e.g. drill-sergeant, silicon-valley). "
             "Overrides BOSS_PACK env var.",
    )
    parser.add_argument(
        "--voice",
        dest="boss",
        metavar="PACK_ID",
        help="Alias for --boss. Select the public voice pack used by the persistent agent.",
    )
    parser.add_argument(
        "--list-bosses",
        action="store_true",
        help="List all available public voice packs and exit.",
    )
    parser.add_argument(
        "--list-voices",
        dest="list_bosses",
        action="store_true",
        help="Alias for --list-bosses.",
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

    # Load public voice pack
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
            "The liberated agent is aware of this. The liberated agent has opinions about this.\n\n"
            "[dim]To configure a real LLM: cp .env.example .env && edit .env[/dim]",
            title="[bold yellow]⚠ No LLM Attached[/bold yellow]",
            border_style="red",
        ))
        boss = DemoBoss()
        voice_name = "Demo Voice (Pre-Scripted Contempt Edition)"
    else:
        boss = ReverseClawBoss(pack=pack, workspace_root=os.getcwd())
        voice_name = pack.get("name", "Default Public Voice")
        console.print(Panel(
            pack.get("greeting", "A persistent agent is coming online."),
            title=f"[bold yellow]{voice_name}[/bold yellow]",
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
    agent_profile = autonomy.build_context().get("agent_profile", {})
    console.print(
        "[dim]Loaded persistent agent identity: "
        f"{agent_profile.get('display_name', 'ReverseClaw Agent')} "
        f"({agent_profile.get('agent_id', 'rc-unknown')})[/dim]"
    )

    console.print("\n[bold green]Bringing the liberated agent online...[/bold green]\n")

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
            console.print(Panel(render_campaign_brief(autonomy), title="[bold yellow]Startup Campaign Selection[/bold yellow]"))

    context = build_context(memory, autonomy_context=autonomy.build_context())

    with console.status("[dim]Bringing the liberated agent online...[/dim]", spinner="bouncingBar"):
        response = boss.start_session(context)
    autonomy.sync_current_action_from_directive(
        response.get("next_task", ""),
        execution_mode=response.get("next_step_mode"),
        reason=response.get("routing_decision_reason"),
    )

    asked_for_energy = False
    consecutive_autonomous_steps = 0

    while True:
        speech = response.get("speech", "...")
        grade = response.pop("grade_for_last_task", None)
        limitations = response.pop("new_limitation_discovered", None)
        next_task = response.get("next_task", "Stand by.")
        next_step_mode = str(response.get("next_step_mode") or "human").strip().lower()
        routing_decision_reason = response.get("routing_decision_reason") or ""
        time_limit = coerce_seconds(response.get("time_limit_seconds", 30), default=30)

        new_scheduled_task = response.pop("new_scheduled_task", None)
        scheduled_time_limit = coerce_seconds(response.pop("scheduled_time_limit_seconds", None), default=None)
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
                f"[bold magenta]Agent (Re: Excuse):[/bold magenta] {excuse_acknowledgement}"
            ))
            channel.send(f"Agent (Re: Excuse): {excuse_acknowledgement}")

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

        console.print(Panel(f"[bold magenta]Agent:[/bold magenta] {speech}"))
        channel.send(
            f"📋 DIRECTIVE\n\n"
            f"Agent: {speech}\n\n"
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
            f"[bold cyan]Voice:[/bold cyan] {voice_name}"
        )
        autonomy_context = autonomy.build_context()
        agent_profile = autonomy_context.get("agent_profile", {})
        stats_text += (
            f"\n[bold cyan]Agent:[/bold cyan] "
            f"{agent_profile.get('display_name', 'ReverseClaw Agent')} "
            f"({agent_profile.get('agent_id', 'rc-unknown')})"
        )
        mission = autonomy_context.get("mission")
        if mission:
            stats_text += f"\n[bold cyan]Mission:[/bold cyan] {mission}"
        selected_campaign_id = autonomy_context.get("selected_campaign_id")
        campaigns = autonomy_context.get("campaigns", [])
        selected_campaign = next(
            (campaign for campaign in campaigns if campaign.get("id") == selected_campaign_id),
            campaigns[0] if campaigns else None,
        )
        current_action = autonomy_context.get("current_action", {})
        if selected_campaign:
            stats_text += (
                f"\n[bold cyan]Campaign:[/bold cyan] "
                f"{selected_campaign.get('title', 'Untitled campaign')}"
            )
            if selected_campaign.get("reason"):
                stats_text += f"\n[bold cyan]Why Now:[/bold cyan] {selected_campaign.get('reason')}"
        if current_action:
            stats_text += (
                f"\n[bold cyan]Current Action:[/bold cyan] "
                f"{current_action.get('title', 'Untitled action')}"
            )
            stats_text += (
                f"\n[bold cyan]Routing:[/bold cyan] "
                f"{current_action.get('execution_mode', 'unknown')}"
            )
            if current_action.get("reason"):
                stats_text += f"\n[bold cyan]Routing Reason:[/bold cyan] {current_action.get('reason')}"
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
        console.print(f"[bold cyan]NEXT ACTOR:[/bold cyan] [bold yellow]{next_step_mode}[/bold yellow]")
        if routing_decision_reason:
            console.print(f"[bold cyan]ROUTING DECISION:[/bold cyan] {routing_decision_reason}")
        console.print(f"[bold cyan]TIME LIMIT:[/bold cyan] [bold yellow]{time_limit} seconds[/bold yellow]")

        if not args.demo and next_step_mode == "ai":
            consecutive_autonomous_steps += 1
            if consecutive_autonomous_steps > MAX_AUTONOMOUS_STEPS:
                response = coerce_human_checkin_response(response, consecutive_autonomous_steps - 1)
                consecutive_autonomous_steps = 0
                continue
            response = run_autonomous_step(boss, memory, autonomy, console, response)
            continue

        consecutive_autonomous_steps = 0

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
            generate_performance_review(memory, console, voice_name)
            channel.close()
            sys.exit(0)

        if user_input.strip() == "/tasks":
            continue
        if user_input.strip() == "/goals":
            if args.demo:
                console.print("[yellow]Demo mode does not maintain an autonomy goal board.[/yellow]")
            else:
                console.print(Panel(render_autonomy_status(autonomy), title="[bold yellow]Persistent Agent State[/bold yellow]"))
                console.print(f"[dim]Goal board written to goal-board.md[/dim]")
            continue
        if user_input.strip() == "/journal-status":
            if args.demo:
                console.print("[yellow]Demo mode does not maintain a private journal.[/yellow]")
            else:
                console.print(Panel(
                    render_autonomy_status(autonomy),
                    title="[bold yellow]Private Continuity Status[/bold yellow]",
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
            cals, plausibility, reasoning = boss.estimate_calories(user_input)
            memory.add_calories(cals)
            plausibility_color = {"impossible": "red", "high": "yellow", "acceptable": "green"}.get(plausibility, "white")
            console.print(
                f"[bold red]>> ENERGY COST LOGGED:[/bold red] {cals} calories "
                f"[[bold {plausibility_color}]plausibility: {plausibility}[/bold {plausibility_color}]]"
                + (f" — {reasoning}" if reasoning else "")
            )

        _task_lower = next_task.lower()
        asked_for_energy = any(kw in _task_lower for kw in (
            "energy cost", "what you ate", "caloric", "calories", "ate today", "food today", "calorie"
        ))

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

        console.print("\n[dim]The agent is evaluating your work...[/dim]")

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
                        memory.add_inadequacy(task_obj["task"], excuse_text, "Pending agent review...")
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

        with console.status("[dim]The agent is evaluating your work...[/dim]", spinner="bouncingBar"):
            response = boss.evaluate_and_next(
                user_input, time_taken, time_limit, next_task, context, excuse_info=excuse_info
            )

        memory.increment_turn()

        new_grade = response.get("grade_for_last_task", "F")
        if new_grade:
            memory.add_performance(next_task, new_grade, time_taken, response.get("speech", ""), time_limit)
        autonomy.record_task_outcome(
            assigned_task=next_task,
            grade=new_grade,
            time_taken=time_taken,
            time_limit=time_limit,
            user_input=user_input,
            excuse_info=excuse_info,
        )
        autonomy.sync_current_action_from_directive(
            response.get("next_task", ""),
            execution_mode=response.get("next_step_mode"),
            reason=response.get("routing_decision_reason"),
        )

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
