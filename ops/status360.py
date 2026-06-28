#!/usr/bin/env python3
"""AOP Status 360.

Dashboard operacional sem dados inventados:
- fonte de backlog: ops/squad-tasks.json
- fonte de vida/status: herdr pane list
- refresh padrao: 60s
"""

from __future__ import annotations

import sys
import time
from datetime import datetime

from rich import box
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from squad_board import (
    create_fleet_table,
    create_summary,
    create_table,
    herdr_live,
    load_tasks,
)


def render_panel() -> Panel:
    tasks = load_tasks()
    live_data = herdr_live()

    active_tasks = [task for task in tasks if task.get("status") != "done"]
    done_tasks = [task for task in tasks if task.get("status") == "done"]

    active_table = create_table(
        active_tasks,
        live_data,
        "TAREFAS ATIVAS NO JSON (NAO ARQUIVADAS)",
        header_style="bold cyan",
    )
    fleet_table = create_fleet_table(tasks, live_data)
    done_table = create_table(
        done_tasks,
        live_data,
        "TAREFAS CONCLUIDAS (ARQUIVO)",
        header_style="bold green",
        archived=True,
    )

    layout = Layout()
    layout.split(
        Layout(Group(active_table, fleet_table, done_table), name="main"),
        Layout(create_summary(tasks, live_data), name="footer", size=6),
    )

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subtitle = Text(
        f"Atualizado em: {timestamp} | refresh real a cada 60s | fontes: squad-tasks.json + herdr pane list",
        style="dim italic",
    )
    return Panel(
        layout,
        title="[bold white]SQUAD AOP - EXECUTIVE DASHBOARD[/bold white]",
        subtitle=subtitle,
        box=box.DOUBLE,
    )


def main() -> None:
    console = Console()
    if "--watch" in sys.argv:
        try:
            with Live(console=console, screen=True, refresh_per_second=1) as live_view:
                while True:
                    live_view.update(render_panel())
                    time.sleep(60)
        except KeyboardInterrupt:
            console.print("[bold green]Monitoramento encerrado.[/bold green]")
    else:
        console.print(render_panel())


if __name__ == "__main__":
    main()
