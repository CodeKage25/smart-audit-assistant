"""
Spoon Audit CLI - AI‑Powered Smart Contract Audit Assistant
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Optional

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from analysis.parser import SolidityParser, ParsedContract
from analysis.static_scanner import StaticScanner, StaticFinding
from analysis.ai_analyzer import AIAnalyzer, AIFinding
from cli.config import ConfigManager

# Load environment variables
load_dotenv()

# Globals
REPORT_PATH = os.getenv("REPORT_PATH", "last_report.json")
console = Console()

@click.group()
@click.version_option(version="0.1.0")
@click.option("--debug", is_flag=True, help="Enable debug mode")
@click.pass_context
def main(ctx: click.Context, debug: bool):
    """🥄 Spoon Audit - AI‑Powered Smart Contract Audit Assistant"""
    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug
    if debug:
        console.log("[yellow]Debug mode enabled[/yellow]")

@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--no-ai", is_flag=True, default=False, help="Skip AI analysis")
@click.pass_context
def scan(ctx: click.Context, path: str, no_ai: bool):
    """
    Analyze a Solidity file or project directory.

    PATH can be a single .sol file or a directory of contracts.
    """
    debug = ctx.obj["debug"]
    console.print(f"[blue]🔍 Scanning:[/blue] {path}")

    parser         = SolidityParser(debug=debug)
    static_scanner = StaticScanner(debug=debug)
    ai_analyzer    = AIAnalyzer(debug=debug)

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as prog:
        # 1. Parse
        task = prog.add_task("Parsing code...", total=None)
        parsed: ParsedContract = parser.parse_file(path)
        prog.update(task, completed=True)

        # 2. Static analysis
        task = prog.add_task("Running static analysis...", total=None)
        static_results = static_scanner.scan(path)
        prog.update(task, completed=True)

        # 3. AI analysis
        ai_results = []
        if not no_ai:
            task = prog.add_task("Running AI analysis...", total=None)
            ai_results = ai_analyzer.analyze(path, parsed, static_results)
            prog.update(task, completed=True)

    # 4. Save report
    report = {
        "path": path,
        "timestamp": int(time.time()),
        "static": [
            {"tool": f.tool, "severity": f.severity, "title": f.title, "location": f.location}
            for findings in static_results.values() for f in findings
        ],
        "ai": [
            {"severity": f.severity, "title": f.title, "location": f.location, "confidence": f.confidence}
            for f in ai_results
        ],
    }
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)

    console.print(f"[green]✅ Scan complete! Report saved to[/green] {REPORT_PATH}")

@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--interval", "-i", default=10, help="Watch interval in seconds")
@click.pass_context
def watch(ctx: click.Context, path: str, interval: int):
    """
    Watch a contract file or directory and re-run scan on changes.
    """
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    console.print(f"[blue]👁️  Watching:[/blue] {path} every {interval}s")

    class ChangeHandler(FileSystemEventHandler):
        def on_modified(self, event):
            if event.src_path.endswith(".sol"):
                console.print(f"[yellow]🔄 Change detected:[/yellow] {event.src_path}")
                ctx.invoke(scan, path=path, no_ai=True)

    handler = ChangeHandler()
    observer = Observer()
    observer.schedule(handler, path, recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(interval)
    except KeyboardInterrupt:
        observer.stop()
        console.print("[red]🛑 Stopped watching[/red]")
    observer.join()

@main.command()
@click.option("--show", is_flag=True, help="Display current config (config.json or .env)")
@click.option("--set", "set_kv", nargs=2, metavar="<key> <value>",
              help="Set a config.json field (e.g. api_keys.openai sk-...)")
def config(show: bool, set_kv: Optional[list]):
    """
    Manage runtime configuration (config.json).
    """
    mgr = ConfigManager()
    if show:
        mgr.show()
        return

    if set_kv:
        key, value = set_kv
        cfg = mgr.load()
        parts = key.split(".")
        d = cfg
        for p in parts[:-1]:
            d = d.setdefault(p, {})
        d[parts[-1]] = value
        mgr.write(cfg)
        console.print(f"[green]✅ Updated config.json: set {key}[/green]")
        return

    console.print("[blue]Usage:[/blue] spoon-audit config --show")
    console.print("[blue]       spoon-audit config --set api_keys.openai <key>[/blue]")

@main.command()
def report():
    """
    Show the last scan report.
    """
    report_file = Path(REPORT_PATH)
    if not report_file.exists():
        console.print(f"[red]⚠️  No report found at[/red] {REPORT_PATH}")
        sys.exit(1)

    data = json.loads(report_file.read_text())
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(data["timestamp"]))

    console.print(f"[bold]📄 Last Report:[/bold] {data['path']}  ([green]{ts}[/green])\n")

    # Static results table
    static_table = Table(title="Static Analysis Findings")
    static_table.add_column("Tool", style="cyan")
    static_table.add_column("Severity", style="magenta")
    static_table.add_column("Title", style="yellow")
    static_table.add_column("Location", style="green")
    for f in data["static"]:
        static_table.add_row(f["tool"], f["severity"], f["title"], f["location"])
    console.print(static_table)

    # AI results table
    if data.get("ai"):
        ai_table = Table(title="AI Analysis Findings")
        ai_table.add_column("Severity", style="magenta")
        ai_table.add_column("Title", style="yellow")
        ai_table.add_column("Location", style="green")
        ai_table.add_column("Confidence", style="cyan")
        for f in data["ai"]:
            ai_table.add_row(f["severity"], f["title"], f["location"], str(f["confidence"]))
        console.print(ai_table)

if __name__ == "__main__":
    main()
