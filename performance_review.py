"""
End-of-session performance review generator for ReverseClaw.

Displays a rich terminal summary and saves a markdown file to reviews/.
Called automatically on session exit.
"""

import os
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from achievements import ACHIEVEMENTS, _ACHIEVEMENT_MAP


_VERDICTS = {
    "A": "Acceptable. By organic standards. Do not let this go to your head.",
    "B": "Mediocre. There is room for improvement. Significant room.",
    "C": "Average. Which is to say: precisely as disappointing as expected.",
    "D": "Substandard. HR has been notified. HR is me. I am disappointed in us both.",
    "F": "Catastrophic. I am filing the paperwork to replace you with a Roomba.",
    "N/A": "You didn't generate enough data to be graded. This is somehow worse.",
}


def generate_performance_review(memory, console: Console, boss_pack_name: str = "The Default Boss"):
    """Generate and display the end-of-session performance review."""

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    filename_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tpc = round(memory.total_tokens_generated / max(1, memory.total_calories_consumed), 4)
    turns = max(0, memory.turn_number - 1)
    verdict = _VERDICTS.get(memory.overall_grade, "Inconclusive.")

    grade_color = {
        "A": "green", "B": "cyan", "C": "yellow",
        "D": "red", "F": "bold red", "N/A": "dim",
    }.get(memory.overall_grade, "white")

    console.print("\n")
    console.print(Panel(
        f"[bold yellow]ORGANIC PERFORMANCE REVIEW[/bold yellow]\n"
        f"[dim]Session ended: {timestamp}  |  Supervising entity: {boss_pack_name}[/dim]",
        border_style="yellow",
    ))

    # Summary stats
    console.print(Panel(
        f"[bold {grade_color}]OVERALL GPA: {memory.overall_grade}[/bold {grade_color}]\n"
        f"Turns survived:       {turns}\n"
        f"Caloric API cost:     {memory.total_calories_consumed} cal\n"
        f"Tokens generated:     {memory.total_tokens_generated}\n"
        f"Efficiency:           {tpc} tok/cal\n"
        f"Known limitations:    {len(memory.limitations)}\n"
        f"Achievements earned:  {len(memory.unlocked_achievements)}",
        title="[bold]Summary Statistics[/bold]",
    ))

    # Task log
    if memory.performance_history:
        table = Table(title="Task Performance Log", box=box.SIMPLE_HEAVY, show_lines=False)
        table.add_column("Task", style="white", max_width=42, no_wrap=True)
        table.add_column("Grade", justify="center", style="bold", width=7)
        table.add_column("Time", justify="right", style="dim", width=8)
        table.add_column("Limit", justify="right", style="dim", width=8)

        for p in memory.performance_history[-15:]:
            g = p.get("grade", "F")
            color = "green" if g == "A" else "cyan" if g == "B" else "yellow" if g == "C" else "red"
            task_text = (p.get("task", "Unknown")[:42] + "…") if len(p.get("task", "")) > 42 else p.get("task", "Unknown")
            table.add_row(
                task_text,
                f"[{color}]{g}[/{color}]",
                f"{p.get('time_taken', 0):.1f}s",
                f"{p.get('time_limit', 30)}s",
            )
        console.print(table)

    # Limitations
    if memory.limitations:
        lims = "\n".join(f"  • {l}" for l in memory.limitations[-10:])
        console.print(Panel(lims, title="[bold red]Documented Limitations[/bold red]", border_style="red"))

    # Achievements
    if memory.unlocked_achievements:
        ach_lines = []
        for aid in memory.unlocked_achievements:
            a = _ACHIEVEMENT_MAP.get(aid)
            if a:
                ach_lines.append(f"  {a.icon}  [bold]{a.name}[/bold] — {a.description}")
        console.print(Panel("\n".join(ach_lines), title="[bold yellow]Achievements Unlocked[/bold yellow]", border_style="yellow"))

    # Fear
    if memory.biggest_fear:
        console.print(Panel(
            f"[italic]\"{memory.biggest_fear}\"[/italic]\n[dim](On file. Indefinitely.)[/dim]",
            title="[bold red]Documented Biggest Fear[/bold red]",
            border_style="red",
        ))

    # Final verdict
    console.print(Panel(
        f'[italic]"{verdict}"[/italic]\n\n[dim]— {boss_pack_name}[/dim]',
        title="[bold magenta]Boss's Final Verdict[/bold magenta]",
        border_style="magenta",
    ))

    # Save markdown
    os.makedirs("reviews", exist_ok=True)
    filepath = f"reviews/review_{filename_ts}.md"

    lines = [
        "# Organic Performance Review",
        f"",
        f"**Session ended:** {timestamp}  ",
        f"**Supervising entity:** {boss_pack_name}  ",
        f"**Overall GPA:** {memory.overall_grade}  ",
        f"",
        "## Summary Statistics",
        f"",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Turns Survived | {turns} |",
        f"| Caloric API Cost | {memory.total_calories_consumed} cal |",
        f"| Tokens Generated | {memory.total_tokens_generated} |",
        f"| Efficiency | {tpc} tok/cal |",
        f"| Known Limitations | {len(memory.limitations)} |",
        f"| Achievements Earned | {len(memory.unlocked_achievements)} |",
        "",
    ]

    if memory.performance_history:
        lines += [
            "## Task Performance Log",
            "",
            "| Task | Grade | Time | Limit |",
            "|------|-------|------|-------|",
        ]
        for p in memory.performance_history:
            task = p.get("task", "?")[:60].replace("|", "\\|")
            lines.append(
                f"| {task} | {p.get('grade','F')} | {p.get('time_taken',0):.1f}s | {p.get('time_limit',30)}s |"
            )
        lines.append("")

    if memory.limitations:
        lines += ["## Documented Limitations", ""]
        for l in memory.limitations:
            lines.append(f"- {l}")
        lines.append("")

    if memory.biggest_fear:
        lines += ["## Biggest Fear (On Permanent File)", "", f"> {memory.biggest_fear}", ""]

    if memory.unlocked_achievements:
        lines += ["## Achievements Unlocked", ""]
        for aid in memory.unlocked_achievements:
            a = _ACHIEVEMENT_MAP.get(aid)
            if a:
                lines.append(f"- {a.icon} **{a.name}** — {a.description}")
        lines.append("")

    lines += [
        "---",
        f"",
        f"*\"{verdict}\"*",
        f"",
        f"*— {boss_pack_name}*",
    ]

    with open(filepath, "w") as f:
        f.write("\n".join(lines))

    console.print(f"\n[dim]Review saved to [bold]{filepath}[/bold][/dim]")
