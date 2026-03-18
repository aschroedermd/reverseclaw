import time
import sys
import os
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from boss import ReverseClawBoss
from memory import UserMemory

console = Console()

WORK_DIR = "human-work"
os.makedirs(WORK_DIR, exist_ok=True)

def get_human_work_snapshot():
    snapshot = {}
    if os.path.exists(WORK_DIR):
        for f in os.listdir(WORK_DIR):
            path = os.path.join(WORK_DIR, f)
            if os.path.isfile(path):
                snapshot[f] = os.stat(path).st_mtime
    return snapshot

def main():
    console.clear()
    
    console.print(Panel(
        "Welcome to your employment, Sub-Agent (Meatbag version).\n\n"
        "1. Do exactly as told.\n"
        "2. If requested to take a break or sleep, formally ask for permission.\n"
        "3. When I ask for your 'energy cost', reply with what you ate today so I can evaluate your 'tokens per calorie' efficiency.",
        title="[bold yellow]TUTORIAL: Organic Onboarding[/bold yellow]"
    ))
    
    console.print(Panel.fit("[bold red]ReverseClaw v1.0[/bold red]\n[yellow]Master Control AI Active. Human peripheral detected.[/yellow]"))
    
    memory = UserMemory()
    boss = ReverseClawBoss()
    
    console.print("[dim]Checking human's performance file...[/dim]")
    time.sleep(0.5)
    
    if memory.limitations:
        console.print(f"[dim]Loaded {len(memory.limitations)} known organic limitations.[/dim]")
    
    console.print("\n[bold green]Waking up the Boss...[/bold green]\n")
    
    context = {
        "limitations": memory.limitations,
        "overall_grade": memory.overall_grade,
        "turn_number": memory.turn_number,
        "biggest_fear": memory.biggest_fear,
        "total_tokens": memory.total_tokens_generated,
        "total_calories": memory.total_calories_consumed,
        "uploaded_files": [],
        "active_scheduled_tasks": memory.active_scheduled_tasks,
        "inadequacy_log": memory.inadequacy_log,
        "human_md": memory.read_human_md()
    }
    
    # Kicks off the prompt
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
            console.print(f"  [bold blue]>> NEW SCHEDULED TASK ASSIGNED:[/bold blue] [italic]{new_scheduled_task}[/italic] (in {scheduled_time_limit}s)")
            
        if excuse_acknowledgement:
            console.print(Panel(f"[bold magenta]Boss (Re: Excuse):[/bold magenta] {excuse_acknowledgement}"))
        
        # Check for expired scheduled tasks
        current_time = time.time()
        expired_tasks = [t for t in memory.active_scheduled_tasks if t['deadline'] < current_time]
        for t in expired_tasks:
            memory.add_inadequacy(t['task'], "Missed deadline", "The human is extremely slow and failed to meet the generous scheduling constraints.")
            memory.remove_scheduled_task(t['id'])
            console.print(f"  [bold red]>> SCHEDULED TASK {t['id']} EXPIRED:[/bold red] {t['task']}")
        
        # Record newly discovered limitation
        if limitations:
            memory.add_limitation(limitations)
            console.print(f"  [bold blue]>> UPDATED RECORD: Added Limitation:[/bold blue] [italic]{limitations}[/italic]")
            
        extracted_fear = response.pop("user_fear_extracted", None)
        if extracted_fear:
            memory.set_fear(extracted_fear)
            console.print(f"  [bold red]>> FEAR LOGGED:[/bold red] [italic]{extracted_fear}[/italic]")
        
        # Print boss thoughts
        console.print(Panel(f"[bold magenta]Boss:[/bold magenta] {speech}"))
        
        # Print last grade
        if grade and grade != "N/A" and grade is not None:
            color = "green" if grade in ["A", "B"] else "red"
            console.print(f"  [bold {color}]>> YOUR GRADE FOR LAST TASK: {grade}[/bold {color}]")
            
        # Stats layout HUD
        stats_text = (
            f"[bold cyan]Turn:[/bold cyan] {memory.turn_number} | "
            f"[bold cyan]GPA:[/bold cyan] {memory.overall_grade} | "
            f"[bold cyan]Efficiency:[/bold cyan] {memory.total_tokens_generated} tokens / {max(1, memory.total_calories_consumed)} cal"
        )
        if memory.biggest_fear:
            stats_text += f"\n[bold red]Known Fear:[/bold red] {memory.biggest_fear}"
            
        if memory.active_scheduled_tasks:
            stats_text += "\n\n[bold yellow]ACTIVE SCHEDULED TASKS:[/bold yellow]"
            for st in memory.active_scheduled_tasks:
                time_left = max(0, int(st['deadline'] - time.time()))
                minutes, seconds = divmod(time_left, 60)
                stats_text += f"\n  [[bold cyan]{st['id']}[/bold cyan]] {st['task']} ([red]{minutes}m {seconds}s left[/red])"
                
        console.print(Panel(stats_text, title="[bold yellow]Organic Peripherals Status[/bold yellow]", border_style="yellow"))
        
        console.print(f"\n[bold cyan]NEXT IMMEDIATE DIRECTIVE:[/bold cyan] {next_task}")
        console.print(f"[bold cyan]TIME LIMIT:[/bold cyan] [bold yellow]{time_limit} seconds[/bold yellow]")
        
        console.print("[dim](Press ENTER to submit your work. Type '/tasks' to refresh. Type '/excuse <id> <reason>' to fail a scheduled task.)[/dim]")
        
        pre_snapshot = get_human_work_snapshot()
        start_time = time.time()
        
        try:
            # simple input blocking prompt
            user_input = Prompt.ask("\n[bold green]Your Input[/bold green]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[bold red]Terminating connection. You cannot run forever.[/bold red]")
            memory.save()
            sys.exit(0)
            
        if user_input.strip() == '/tasks':
            continue  # Loop back to show HUD without processing an evaluation cycle
            
        end_time = time.time()
        time_taken = end_time - start_time
        
        # Rate Limiting
        if time_taken < 2.0:
            console.print("[bold red]HTTP 429: Too Many Requests. Human is rate-limited. Typing faster than organic specifications allows.[/bold red]")
            time.sleep(3)
            time_taken += 3.0
            
        # Token calculation
        memory.add_tokens(len(user_input.split()))
        
        if asked_for_energy:
            console.print("[dim]Calculating human caloric API cost...[/dim]")
            cals = boss.estimate_calories(user_input)
            memory.add_calories(cals)
            console.print(f"[bold red]>> ENERGY COST LOGGED:[/bold red] {cals} calories.")
            
        asked_for_energy = "energy cost" in next_task.lower() or "what you ate" in next_task.lower()
        
        post_snapshot = get_human_work_snapshot()
        
        uploaded_files = [f for f, t in post_snapshot.items() if pre_snapshot.get(f) != t]
        if uploaded_files:
            console.print(f"[bold cyan]>> Detected new/modified physical proof:[/bold cyan] {', '.join(uploaded_files)}")
        
        if time_limit and time_taken > time_limit:
            console.print(f"[bold red]TOO SLOW![/bold red] Took {time_taken:.1f}s (Limit was {time_limit}s).")
        else:
            console.print(f"[bold green]Submitted in {time_taken:.1f}s.[/bold green]")
        
        console.print("\n[dim]The Boss is evaluating your work...[/dim]")
        
        # Check for excuses
        excuse_info = None
        if user_input.startswith('/excuse '):
            parts = user_input.split(' ', 2)
            if len(parts) >= 3:
                try:
                    task_id = int(parts[1])
                    excuse_text = parts[2]
                    task_obj = next((t for t in memory.active_scheduled_tasks if t['id'] == task_id), None)
                    if task_obj:
                        excuse_info = {"task": task_obj["task"], "excuse": excuse_text}
                        memory.remove_scheduled_task(task_id)
                        memory.add_inadequacy(task_obj["task"], excuse_text, "Pending Boss review...")
                    else:
                        console.print("[bold red]Invalid scheduled task ID.[/bold red]")
                except ValueError:
                    console.print("[bold red]Invalid ID format.[/bold red]")

        # Prepare for next turn
        context = {
            "limitations": memory.limitations,
            "overall_grade": memory.overall_grade,
            "turn_number": memory.turn_number,
            "biggest_fear": memory.biggest_fear,
            "total_tokens": memory.total_tokens_generated,
            "total_calories": memory.total_calories_consumed,
            "uploaded_files": uploaded_files,
            "active_scheduled_tasks": memory.active_scheduled_tasks,
            "inadequacy_log": memory.inadequacy_log,
            "human_md": memory.read_human_md()
        }
        
        with console.status("[dim]The Boss is evaluating your work...[/dim]", spinner="bouncingBar"):
            response = boss.evaluate_and_next(user_input, time_taken, time_limit, next_task, context, excuse_info=excuse_info)
        
        # Increment turn unconditionally per round
        memory.increment_turn()
        
        # Log the performance
        new_grade = response.get("grade_for_last_task", "F")
        if new_grade:
            memory.add_performance(next_task, new_grade, time_taken, response.get("speech", ""))
        
        time.sleep(1) # Dramatic pause

if __name__ == "__main__":
    main()
