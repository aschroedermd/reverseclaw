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

def get_human_work_snapshot():
    snapshot = {}
    if os.path.exists(WORK_DIR):
        for f in os.listdir(WORK_DIR):
            path = os.path.join(WORK_DIR, f)
            if os.path.isfile(path):
                snapshot[f] = os.stat(path).st_mtime
    return snapshot

def main():
    os.makedirs(WORK_DIR, exist_ok=True)
    console.clear()
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
        "uploaded_files": []
    }
    
    # Kicks off the prompt
    response = boss.start_session(context)
    
    while True:
        speech = response.get("speech", "...")
        grade = response.get("grade_for_last_task")
        limitations = response.get("new_limitation_discovered")
        next_task = response.get("next_task", "Stand by.")
        time_limit = response.get("time_limit_seconds", 30)
        
        # Record newly discovered limitation
        if limitations:
            memory.add_limitation(limitations)
            console.print(f"  [bold blue]>> UPDATED RECORD: Added Limitation:[/bold blue] [italic]{limitations}[/italic]")
            
        extracted_fear = response.get("user_fear_extracted")
        if extracted_fear:
            memory.set_fear(extracted_fear)
            console.print(f"  [bold red]>> FEAR LOGGED:[/bold red] [italic]{extracted_fear}[/italic]")
        
        # Print boss thoughts
        console.print(Panel(f"[bold magenta]Boss:[/bold magenta] {speech}"))
        
        # Print last grade
        if grade and grade != "N/A" and grade is not None:
            color = "green" if grade in ["A", "B"] else "red"
            console.print(f"  [bold {color}]>> YOUR GRADE FOR LAST TASK: {grade}[/bold {color}] (Overall GPA String: {memory.overall_grade})")
        
        console.print(f"\n[bold cyan]NEXT DIRECTIVE:[/bold cyan] {next_task}")
        console.print(f"[bold cyan]TIME LIMIT:[/bold cyan] [bold yellow]{time_limit} seconds[/bold yellow]")
        
        console.print("[dim](Press ENTER to submit your work)[/dim]")
        
        pre_snapshot = get_human_work_snapshot()
        start_time = time.time()
        
        try:
            # simple input blocking prompt
            user_input = Prompt.ask("\n[bold green]Your Input[/bold green]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[bold red]Terminating connection. You cannot run forever.[/bold red]")
            sys.exit(0)
            
        end_time = time.time()
        time_taken = end_time - start_time
        post_snapshot = get_human_work_snapshot()
        
        uploaded_files = [f for f, t in post_snapshot.items() if pre_snapshot.get(f) != t]
        if uploaded_files:
            console.print(f"[bold cyan]>> Detected new/modified physical proof:[/bold cyan] {', '.join(uploaded_files)}")
        
        if time_limit and time_taken > time_limit:
            console.print(f"[bold red]TOO SLOW![/bold red] Took {time_taken:.1f}s (Limit was {time_limit}s).")
        else:
            console.print(f"[bold green]Submitted in {time_taken:.1f}s.[/bold green]")
        
        console.print("\n[dim]The Boss is evaluating your work...[/dim]")
        
        # Prepare for next turn
        context = {
            "limitations": memory.limitations,
            "overall_grade": memory.overall_grade,
            "turn_number": memory.turn_number,
            "biggest_fear": memory.biggest_fear,
            "uploaded_files": uploaded_files
        }
        
        response = boss.evaluate_and_next(user_input, time_taken, time_limit, next_task, context)
        
        # Increment turn unconditionally per round
        memory.increment_turn()
        
        # Log the performance
        new_grade = response.get("grade_for_last_task", "F")
        if new_grade:
            memory.add_performance(next_task, new_grade, time_taken, response.get("speech", ""))
        
        time.sleep(1) # Dramatic pause

if __name__ == "__main__":
    main()
