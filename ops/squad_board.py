#!/usr/bin/env python3
"""
squad_board.py — Painel 360 da squad AOP (nível premium Fortune 500).
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime

from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.layout import Layout
from rich.live import Live
from rich.progress_bar import ProgressBar
from rich import box

HERE = os.path.dirname(os.path.abspath(__file__))
TASKS_FILE = os.path.join(HERE, "squad-tasks.json")

STATUS_COLORS = {
    "done": "bold green",
    "working": "bold yellow",
    "review": "bold magenta",
    "held": "bold blue",
    "pending": "dim white",
    "blocked": "bold red",
    "orphaned": "bold red",
}

STATUS_ICONS = {
    "done": "●",
    "working": "▶",
    "review": "★",
    "held": "⏸",
    "pending": "○",
    "blocked": "✖",
    "orphaned": "✖",
}

DEFAULT_TASKS = []

def load_tasks():
    try:
        with open(TASKS_FILE, encoding="utf-8") as f:
            return json.load(f).get("tasks", [])
    except Exception:
        return DEFAULT_TASKS

def herdr_live():
    try:
        out = subprocess.run(["herdr", "pane", "list"], capture_output=True, text=True, timeout=10).stdout
        panes = json.loads(out).get("result", {}).get("panes", [])
        return {p["pane_id"]: p.get("agent_status", "unknown") for p in panes}
    except Exception as e:
        return {"_error": str(e)}

def format_eta(eta_min, status):
    if status == "done":
        return Text("0m", style="bold green")
    if eta_min in (None, ""):
        return Text("--", style="dim")
    try:
        val = int(eta_min)
        if val <= 5:
            return Text(f"{val}m", style="bold red")
        elif val <= 20:
            return Text(f"{val}m", style="bold yellow")
        else:
            return Text(f"{val}m", style="white")
    except ValueError:
        return Text("--", style="dim")

def create_table(tasks, live, title, header_style="bold cyan"):
    table = Table(
        title=f"[bold white]{title}[/bold white]",
        box=box.HEAVY_EDGE,
        header_style=header_style,
        show_lines=True,
        expand=True
    )
    table.add_column("ID", justify="center", style="cyan", width=3)
    table.add_column("PRI", justify="center", width=3)
    table.add_column("TAREFA", width=40)
    table.add_column("STATUS", justify="left", width=12)
    table.add_column("AGENTE", width=22)
    table.add_column("VIVO", width=10)
    table.add_column("PROGRESSO", justify="left", width=20)
    table.add_column("ETA", justify="right", width=6)

    err = live.get("_error")
    
    rank = {"P0": 0, "P1": 1, "P2": 2}
    sorted_tasks = sorted(tasks, key=lambda t: (rank.get(t.get("priority"), 9), t.get("id", "")))

    for t in sorted_tasks:
        st = t.get("status", "pending")
        col = STATUS_COLORS.get(st, "white")
        icon = STATUS_ICONS.get(st, "○")
        
        status_text = Text(f"{icon} {st.upper()}", style=col)
        prio_text = Text(t.get("priority", "?"), style="red" if t.get("priority") == "P0" else "yellow" if t.get("priority") == "P1" else "white")
        
        pane = t.get("pane", "-")
        agent_lv = live.get(pane, "unknown") if not err else "unknown"
        agent_lv_style = "bold green" if agent_lv == "done" else "bold yellow" if agent_lv == "working" else "dim white" if agent_lv == "idle" else "red"
        
        agent_display = Text.assemble((t.get("agent", "?"), "bold"), " ", (f"({pane})", "dim"))
        vivo_display = Text(agent_lv.upper(), style=agent_lv_style)
        
        prog = float(t.get("progress", 0) or 0)
        prog_color = "green" if prog >= 100 else "yellow" if prog >= 40 else "red"
        
        prog_bar = ProgressBar(total=100, completed=prog, width=12, style="dim", complete_style=prog_color, finished_style="bold green")
        
        prog_text = Text(f" {int(prog)}%", style=prog_color)
        prog_display = Table.grid(padding=0)
        prog_display.add_column()
        prog_display.add_column()
        prog_display.add_row(prog_bar, prog_text)
        
        eta_display = format_eta(t.get("eta_min"), st)
        
        table.add_row(
            t.get("id", "?"),
            prio_text,
            t.get("title", ""),
            status_text,
            agent_display,
            vivo_display,
            prog_display,
            eta_display
        )
    return table

def create_summary(tasks, live):
    total = len(tasks) or 1
    done = sum(1 for t in tasks if t.get("status") == "done")
    working = sum(1 for t in tasks if t.get("status") in ("working", "review"))
    held = sum(1 for t in tasks if t.get("status") == "held")
    blocked = sum(1 for t in tasks if t.get("status") in ("blocked", "orphaned"))
    
    total_prog = sum(float(t.get("progress", 0) or 0) for t in tasks)
    overall = total_prog / total
    
    prog_color = "green" if overall >= 100 else "yellow"
    prog_bar = ProgressBar(total=100, completed=overall, width=20, style="dim", complete_style=prog_color, finished_style="bold green")
    
    summary_text = Text.assemble(
        ("OVERALL PROGRESS: ", "bold"), 
        (f"{int(overall)}% ", prog_color),
        "   |   ",
        (f"✔ {done} Concluídas", "bold green"), "   |   ",
        (f"▶ {working} Em Curso", "bold yellow"), "   |   ",
        (f"⏸ {held} Em Espera", "bold blue"), "   |   ",
        (f"✖ {blocked} Bloqueadas", "bold red")
    )
    
    err = live.get("_error")
    stuck_alerts = []
    if not err:
        for t in tasks:
            if live.get(t.get("pane")) == "idle" and t.get("status") not in ("done", "held", "pending"):
                stuck_alerts.append(f"{t.get('id')}({t.get('pane')})")
    
    content = Table.grid(padding=1)
    content.add_column()
    content.add_row(summary_text)
    if stuck_alerts:
        content.add_row(Text(f"⚠ ALERTA DE OCIOSIDADE: Agentes IDLE com tarefas pendentes -> {', '.join(stuck_alerts)}", style="bold red blink"))
    
    if err:
        content.add_row(Text(f"⚠ Herdr indisponível: {err}", style="bold red"))

    return Panel(content, title="[bold]KPIs & ALERTS[/bold]", border_style="blue", box=box.ROUNDED)

def main():
    console = Console()
    watch = "--watch" in sys.argv
    interval = 5
    if watch:
        i = sys.argv.index("--watch")
        if i + 1 < len(sys.argv):
            try:
                interval = float(sys.argv[i + 1])
            except ValueError:
                pass
        
        try:
            with Live(console=console, screen=True, refresh_per_second=1) as live_view:
                while True:
                    tasks = load_tasks()
                    live_data = herdr_live()
                    
                    active_tasks = [t for t in tasks if t.get("status") != "done"]
                    done_tasks = [t for t in tasks if t.get("status") == "done"]
                    
                    active_table = create_table(active_tasks, live_data, "TAREFAS ATIVAS (EM ANDAMENTO)", header_style="bold cyan")
                    done_table = create_table(done_tasks, live_data, "TAREFAS CONCLUÍDAS (ARQUIVO)", header_style="bold green")
                    
                    tables_group = Group(active_table, done_table) if done_tasks else active_table
                    
                    layout = Layout()
                    layout.split(
                        Layout(tables_group, name="main"),
                        Layout(create_summary(tasks, live_data), name="footer", size=5)
                    )
                    
                    time_text = Text(f"Atualizado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Próxima att em {interval}s", style="dim italic")
                    main_panel = Panel(layout, title="[bold white]SQUAD AOP - EXECUTIVE DASHBOARD[/bold white]", subtitle=time_text, box=box.DOUBLE)
                    live_view.update(main_panel)
                    time.sleep(interval)
        except KeyboardInterrupt:
            console.print("[bold green]Monitoramento encerrado.[/bold green]")
    else:
        tasks = load_tasks()
        live_data = herdr_live()
        
        active_tasks = [t for t in tasks if t.get("status") != "done"]
        done_tasks = [t for t in tasks if t.get("status") == "done"]
        
        console.print(create_table(active_tasks, live_data, "TAREFAS ATIVAS", header_style="bold cyan"))
        if done_tasks:
            console.print(create_table(done_tasks, live_data, "TAREFAS CONCLUÍDAS", header_style="bold green"))
        
        console.print(create_summary(tasks, live_data))

if __name__ == "__main__":
    main()
