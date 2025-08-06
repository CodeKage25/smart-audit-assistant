"""
Spoon Audit CLI - AI‑Powered Smart Contract Audit Assistant
Enhanced version with complete AI analysis details and multi-contract support
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Optional, List

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich.markdown import Markdown

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
@click.option("--detailed", is_flag=True, default=False, help="Show detailed findings immediately")
@click.option("--spoon-agent", "spoon_agent",
              type=click.Choice(["react", "spoon_react_mcp", "custom"]),
              default=None,
              help="Use Spoon agent (requires spoon_ai & deps)")
@click.pass_context
def scan(ctx: click.Context, path: str, no_ai: bool, detailed: bool, spoon_agent: Optional[str]):
    """
    Analyze a Solidity file or project directory.

    PATH can be a single .sol file or a directory of contracts.
    """
    debug = ctx.obj["debug"]
    console.print(f"[blue]🔍 Scanning:[/blue] {path}")

    parser         = SolidityParser(debug=debug)
    static_scanner = StaticScanner(debug=debug)
    ai_analyzer = AIAnalyzer(
    debug=debug,
    use_spoon_agent=bool(spoon_agent),
    spoon_agent_type=(spoon_agent or "react")
)


    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as prog:
        # 1. Parse - Now returns a list of contracts
        task = prog.add_task("Parsing code...", total=None)
        parsed_contracts: List[ParsedContract] = parser.parse_file(path)
        prog.update(task, completed=True)
        
        # Show parsing results
        if len(parsed_contracts) > 1:
            console.print(f"[cyan]📄 Found {len(parsed_contracts)} contracts:[/cyan]")
            for contract in parsed_contracts:
                console.print(f"  • {contract.name}")

        # 2. Static analysis
        task = prog.add_task("Running static analysis...", total=None)
        static_results = static_scanner.scan(path)
        prog.update(task, completed=True)

        # 3. AI analysis - Pass all contracts
        ai_results = []
        if not no_ai:
            task = prog.add_task("Running AI analysis...", total=None)
            # Run AI analysis for each contract
            for contract in parsed_contracts:
                contract_ai_results = ai_analyzer.analyze(path, contract, static_results)
                ai_results.extend(contract_ai_results)
            prog.update(task, completed=True)

    # 4. Save detailed report with contract information
    report = {
        "path": path,
        "timestamp": int(time.time()),
        "contracts": [
            {
                "name": contract.name,
                "functions_count": len(contract.functions),
                "events_count": len(contract.events),
                "modifiers_count": len(contract.modifiers),
                "has_bytecode": contract.bytecode is not None,
                "has_abi": contract.abi is not None
            }
            for contract in parsed_contracts
        ],
        "static": [
            {
                "tool": f.tool, 
                "severity": f.severity, 
                "title": f.title, 
                "location": f.location,
                "description": getattr(f, 'description', ''),
                "suggestion": getattr(f, 'suggestion', ''),
                "contract": getattr(f, 'contract', '')  # Add contract context if available
            }
            for findings in static_results.values() for f in findings
        ],
        "ai": [
            {
                "severity": f.severity, 
                "title": f.title, 
                "description": f.description,
                "location": f.location, 
                "confidence": f.confidence,
                "reasoning": f.reasoning,
                "suggested_fix": f.suggested_fix,
                "contract": getattr(f, 'contract', '')  # Add contract context if available
            }
            for f in ai_results
        ],
    }
    
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)

    console.print(f"[green]✅ Scan complete! Report saved to[/green] {REPORT_PATH}")
    
    # Show summary with contract info
    contract_count = len(parsed_contracts)
    static_count = len(report["static"])
    ai_count = len(report["ai"])
    
    console.print(f"[cyan]📊 Analyzed {contract_count} contract(s), found {static_count} static findings and {ai_count} AI findings[/cyan]")
    
    # Show contract summary
    if contract_count > 1:
        contract_table = Table(title="Contract Summary")
        contract_table.add_column("Contract", style="cyan")
        contract_table.add_column("Functions", style="green")
        contract_table.add_column("Events", style="yellow")
        contract_table.add_column("Modifiers", style="magenta")
        
        for contract in parsed_contracts:
            contract_table.add_row(
                contract.name,
                str(len(contract.functions)),
                str(len(contract.events)),
                str(len(contract.modifiers))
            )
        console.print(contract_table)
        console.print()
    
    # Show detailed results if requested
    if detailed:
        show_detailed_report(report)

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
@click.option("--detailed", "-d", is_flag=True, default=False, help="Show detailed findings with reasoning")
@click.option("--ai-only", is_flag=True, default=False, help="Show only AI findings")
@click.option("--static-only", is_flag=True, default=False, help="Show only static findings")
@click.option("--severity", type=click.Choice(['critical', 'high', 'medium', 'low', 'info']), 
              help="Filter by severity level")
@click.option("--contract", help="Filter by contract name")
def report(detailed: bool, ai_only: bool, static_only: bool, severity: Optional[str], contract: Optional[str]):
    """
    Show the last scan report.
    """
    report_file = Path(REPORT_PATH)
    if not report_file.exists():
        console.print(f"[red]⚠️  No report found at[/red] {REPORT_PATH}")
        sys.exit(1)

    data = json.loads(report_file.read_text())
    
    if detailed:
        show_detailed_report(data, ai_only=ai_only, static_only=static_only, 
                           severity_filter=severity, contract_filter=contract)
    else:
        show_summary_report(data, ai_only=ai_only, static_only=static_only, 
                          severity_filter=severity, contract_filter=contract)

def show_summary_report(data: dict, ai_only: bool = False, static_only: bool = False, 
                       severity_filter: Optional[str] = None, contract_filter: Optional[str] = None):
    """Show a summary report in table format"""
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(data["timestamp"]))
    console.print(f"[bold]📄 Last Report:[/bold] {data['path']}  ([green]{ts}[/green])\n")

    # Show contract summary if multiple contracts
    if len(data.get("contracts", [])) > 1:
        contracts_table = Table(title="Analyzed Contracts")
        contracts_table.add_column("Contract", style="cyan")
        contracts_table.add_column("Functions", style="green")
        contracts_table.add_column("Events", style="yellow")
        contracts_table.add_column("Modifiers", style="magenta")
        
        for contract_info in data["contracts"]:
            contracts_table.add_row(
                contract_info["name"],
                str(contract_info["functions_count"]),
                str(contract_info["events_count"]),
                str(contract_info["modifiers_count"])
            )
        console.print(contracts_table)
        console.print()

    # Apply filters
    def should_include(finding):
        if severity_filter and finding.get("severity", "").lower() != severity_filter.lower():
            return False
        if contract_filter and finding.get("contract", "").lower() != contract_filter.lower():
            return False
        return True

    # Static results table
    if not ai_only and data.get("static"):
        static_findings = [f for f in data["static"] if should_include(f)]
        if static_findings:
            static_table = Table(title="Static Analysis Findings")
            static_table.add_column("Tool", style="cyan")
            static_table.add_column("Severity", style="magenta")
            static_table.add_column("Title", style="yellow")
            static_table.add_column("Location", style="green")
            if len(data.get("contracts", [])) > 1:
                static_table.add_column("Contract", style="blue")
            
            for f in static_findings:
                row = [f["tool"], f["severity"], f["title"], f["location"]]
                if len(data.get("contracts", [])) > 1:
                    row.append(f.get("contract", "N/A"))
                static_table.add_row(*row)
            console.print(static_table)
            console.print()

    # AI results table
    if not static_only and data.get("ai"):
        ai_findings = [f for f in data["ai"] if should_include(f)]
        if ai_findings:
            ai_table = Table(title="AI Analysis Findings")
            ai_table.add_column("Severity", style="magenta")
            ai_table.add_column("Title", style="yellow")
            ai_table.add_column("Location", style="green")
            ai_table.add_column("Confidence", style="cyan")
            if len(data.get("contracts", [])) > 1:
                ai_table.add_column("Contract", style="blue")
            
            for f in ai_findings:
                confidence_str = f"{f['confidence']:.1f}" if isinstance(f['confidence'], (int, float)) else str(f['confidence'])
                row = [f["severity"], f["title"], f["location"], confidence_str]
                if len(data.get("contracts", [])) > 1:
                    row.append(f.get("contract", "N/A"))
                ai_table.add_row(*row)
            console.print(ai_table)
            console.print()

    # Show filter help
    filter_help = []
    if len(data.get("contracts", [])) > 1:
        filter_help.append("--contract <name> to filter by contract")
    filter_help.append("--severity <level> to filter by severity")
    filter_help.append("--detailed flag to see reasoning and suggested fixes")
    
    console.print(f"[dim]💡 Use {' | '.join(filter_help)}[/dim]")

def show_detailed_report(data: dict, ai_only: bool = False, static_only: bool = False, 
                        severity_filter: Optional[str] = None, contract_filter: Optional[str] = None):
    """Show detailed report with full finding information"""
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(data["timestamp"]))
    console.print(f"[bold]📄 Detailed Report:[/bold] {data['path']}  ([green]{ts}[/green])\n")

    # Show contract summary if multiple contracts
    if len(data.get("contracts", [])) > 1:
        console.print("[bold blue]📋 Contract Summary[/bold blue]\n")
        for contract_info in data["contracts"]:
            console.print(f"[cyan]• {contract_info['name']}:[/cyan] "
                         f"{contract_info['functions_count']} functions, "
                         f"{contract_info['events_count']} events, "
                         f"{contract_info['modifiers_count']} modifiers")
        console.print()

    # Apply filters
    def should_include(finding):
        if severity_filter and finding.get("severity", "").lower() != severity_filter.lower():
            return False
        if contract_filter and finding.get("contract", "").lower() != contract_filter.lower():
            return False
        return True

    # Static Analysis Details
    if not ai_only and data.get("static"):
        static_findings = [f for f in data["static"] if should_include(f)]
        if static_findings:
            console.print("[bold blue]🔧 Static Analysis Findings[/bold blue]\n")
            for i, finding in enumerate(static_findings, 1):
                show_detailed_static_finding(finding, i, show_contract=len(data.get("contracts", [])) > 1)
            console.print()

    # AI Analysis Details  
    if not static_only and data.get("ai"):
        ai_findings = [f for f in data["ai"] if should_include(f)]
        if ai_findings:
            console.print("[bold magenta]🤖 AI Analysis Findings[/bold magenta]\n")
            for i, finding in enumerate(ai_findings, 1):
                show_detailed_ai_finding(finding, i, show_contract=len(data.get("contracts", [])) > 1)

def show_detailed_static_finding(finding: dict, index: int, show_contract: bool = False):
    """Show detailed view of a static analysis finding"""
    severity_colors = {
        "critical": "red",
        "high": "red", 
        "medium": "yellow",
        "low": "green",
        "info": "blue"
    }
    
    severity_color = severity_colors.get(finding["severity"].lower(), "white")
    
    # Create header
    header = f"[bold]{index}. {finding['title']}[/bold]"
    
    # Create content
    content_lines = [
        f"[{severity_color}]Severity:[/{severity_color}] {finding['severity'].upper()}",
        f"[cyan]Tool:[/cyan] {finding['tool']}",
        f"[green]Location:[/green] {finding['location']}"
    ]
    
    if show_contract and finding.get("contract"):
        content_lines.append(f"[blue]Contract:[/blue] {finding['contract']}")
    
    if finding.get("description"):
        content_lines.append(f"[white]Description:[/white] {finding['description']}")
    
    if finding.get("suggestion"):
        content_lines.append(f"[yellow]Suggestion:[/yellow] {finding['suggestion']}")
    
    content = "\n".join(content_lines)
    
    # Create panel
    panel = Panel(
        content,
        title=header,
        border_style=severity_color,
        padding=(0, 1)
    )
    
    console.print(panel)
    console.print()

def show_detailed_ai_finding(finding: dict, index: int, show_contract: bool = False):
    """Show detailed view of an AI analysis finding"""
    severity_colors = {
        "critical": "red",
        "high": "red",
        "medium": "yellow", 
        "low": "green",
        "info": "blue"
    }
    
    severity_color = severity_colors.get(finding["severity"].lower(), "white")
    confidence = finding.get('confidence', 0)
    confidence_str = f"{confidence:.1f}" if isinstance(confidence, (int, float)) else str(confidence)
    
    # Create header with confidence indicator
    confidence_indicator = "🔴" if confidence >= 0.9 else "🟡" if confidence >= 0.7 else "🟢"
    header = f"[bold]{index}. {finding['title']} {confidence_indicator}[/bold]"
    
    # Create content sections
    content_lines = [
        f"[{severity_color}]Severity:[/{severity_color}] {finding['severity'].upper()}",
        f"[cyan]Confidence:[/cyan] {confidence_str}",
        f"[green]Location:[/green] {finding['location']}"
    ]
    
    if show_contract and finding.get("contract"):
        content_lines.append(f"[blue]Contract:[/blue] {finding['contract']}")
    
    if finding.get("description"):
        content_lines.append(f"\n[white]Description:[/white]")
        content_lines.append(f"{finding['description']}")
    
    if finding.get("reasoning"):
        content_lines.append(f"\n[blue]Reasoning:[/blue]")
        content_lines.append(f"{finding['reasoning']}")
    
    if finding.get("suggested_fix"):
        content_lines.append(f"\n[yellow]Suggested Fix:[/yellow]")
        content_lines.append(f"{finding['suggested_fix']}")
    elif finding.get("suggestion"):  # Fallback for legacy format
        content_lines.append(f"\n[yellow]Suggestion:[/yellow]")
        content_lines.append(f"{finding['suggestion']}")
    
    content = "\n".join(content_lines)
    
    # Create panel
    panel = Panel(
        content,
        title=header,
        border_style=severity_color,
        padding=(0, 1)
    )
    
    console.print(panel)
    console.print()

@main.command()
@click.option("--format", "output_format", type=click.Choice(['json', 'markdown', 'html', 'pdf']), 
              default='json', help="Export format")
@click.option("--output", "-o", help="Output file path")
@click.option("--open-browser", is_flag=True, help="Open HTML report in browser")
@click.option("--contract", help="Filter export by contract name")
def export(output_format: str, output: Optional[str], open_browser: bool, contract: Optional[str]):
    """
    Export the last report to different formats.
    """
    report_file = Path(REPORT_PATH)
    if not report_file.exists():
        console.print(f"[red]⚠️  No report found at[/red] {REPORT_PATH}")
        sys.exit(1)

    data = json.loads(report_file.read_text())
    
    # Apply contract filter if specified
    if contract:
        data = filter_report_by_contract(data, contract)
        if not data["static"] and not data["ai"]:
            console.print(f"[yellow]⚠️  No findings found for contract: {contract}[/yellow]")
            return
    
    if not output:
        timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(data["timestamp"]))
        contract_suffix = f"_{contract}" if contract else ""
        output = f"spoon_audit_report{contract_suffix}_{timestamp}.{output_format}"
    
    if output_format == 'json':
        export_json(data, output)
        console.print(f"[green]✅ JSON report exported to[/green] {output}")
    elif output_format == 'markdown':
        export_markdown(data, output)
        console.print(f"[green]✅ Markdown report exported to[/green] {output}")
    elif output_format == 'html':
        export_html(data, output, open_browser)
        console.print(f"[green]✅ HTML report exported to[/green] {output}")
    elif output_format == 'pdf':
        export_pdf(data, output)  # This function handles its own success/failure messages

def filter_report_by_contract(data: dict, contract: str) -> dict:
    """Filter report data by contract name"""
    filtered_data = data.copy()
    
    # Filter static findings
    filtered_data["static"] = [
        f for f in data.get("static", []) 
        if f.get("contract", "").lower() == contract.lower()
    ]
    
    # Filter AI findings
    filtered_data["ai"] = [
        f for f in data.get("ai", []) 
        if f.get("contract", "").lower() == contract.lower()
    ]
    
    # Filter contracts list
    filtered_data["contracts"] = [
        c for c in data.get("contracts", []) 
        if c["name"].lower() == contract.lower()
    ]
    
    return filtered_data

def export_json(data: dict, output_file: str):
    """Export report as JSON"""
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)

def export_markdown(data: dict, output_file: str):
    """Export report as Markdown"""
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(data["timestamp"]))
    
    md_content = f"""# Spoon Audit Report

**Contract Path:** {data['path']}  
**Date:** {ts}

## Summary

- Contracts Analyzed: {len(data.get('contracts', []))}
- Static Analysis Findings: {len(data.get('static', []))}
- AI Analysis Findings: {len(data.get('ai', []))}

"""
    
    # Contract Summary
    if len(data.get('contracts', [])) > 1:
        md_content += "## Contract Summary\n\n"
        for contract in data['contracts']:
            md_content += f"- **{contract['name']}**: {contract['functions_count']} functions, {contract['events_count']} events, {contract['modifiers_count']} modifiers\n"
        md_content += "\n"
    
    md_content += "## Static Analysis Findings\n\n"
    
    for finding in data.get('static', []):
        md_content += f"""### {finding['title']}

- **Severity:** {finding['severity'].upper()}
- **Tool:** {finding['tool']}
- **Location:** {finding['location']}
"""
        if finding.get('contract'):
            md_content += f"- **Contract:** {finding['contract']}\n"
        
        if finding.get('description'):
            md_content += f"\n**Description:** {finding['description']}\n\n"
        if finding.get('suggestion'):
            md_content += f"**Suggestion:** {finding['suggestion']}\n\n"
    
    md_content += "## AI Analysis Findings\n\n"
    
    for finding in data.get('ai', []):
        confidence = finding.get('confidence', 0)
        confidence_str = f"{confidence:.1f}" if isinstance(confidence, (int, float)) else str(confidence)
        
        md_content += f"""### {finding['title']}

- **Severity:** {finding['severity'].upper()}
- **Confidence:** {confidence_str}
- **Location:** {finding['location']}
"""
        if finding.get('contract'):
            md_content += f"- **Contract:** {finding['contract']}\n"
        
        if finding.get('description'):
            md_content += f"\n**Description:** {finding['description']}\n\n"
        if finding.get('reasoning'):
            md_content += f"**Reasoning:** {finding['reasoning']}\n\n"
        if finding.get('suggested_fix'):
            md_content += f"**Suggested Fix:** {finding['suggested_fix']}\n\n"
    
    with open(output_file, 'w') as f:
        f.write(md_content)

def export_html(data: dict, output_file: str, open_browser: bool = False):
    """Export report as enhanced HTML"""
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(data["timestamp"]))
    contract_count = len(data.get('contracts', []))
    
    # Enhanced CSS with modern styling
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Spoon Audit Report</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            font-weight: 300;
        }}
        
        .header .subtitle {{
            opacity: 0.8;
            font-size: 1.1em;
        }}
        
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            padding: 30px;
            background: #f8f9fa;
        }}
        
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        
        .stat-number {{
            font-size: 2em;
            font-weight: bold;
            color: #3498db;
        }}
        
        .stat-label {{
            color: #666;
            margin-top: 5px;
        }}
        
        .content {{
            padding: 40px;
        }}
        
        .section-title {{
            font-size: 1.8em;
            margin: 40px 0 20px 0;
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        
        .contract-summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }}
        
        .contract-card {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #3498db;
        }}
        
        .contract-name {{
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 8px;
        }}
        
        .contract-stats {{
            font-size: 0.9em;
            color: #666;
        }}
        
        .finding {{
            margin: 20px 0;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            transition: transform 0.2s ease;
        }}
        
        .finding:hover {{
            transform: translateY(-2px);
        }}
        
        .finding-header {{
            padding: 20px;
            font-weight: bold;
            color: white;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .finding-body {{
            padding: 20px;
            background: white;
        }}
        
        .finding-meta {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 6px;
        }}
        
        .meta-item {{
            display: flex;
            flex-direction: column;
        }}
        
        .meta-label {{
            font-weight: bold;
            color: #666;
            font-size: 0.9em;
            margin-bottom: 5px;
        }}
        
        .meta-value {{
            color: #2c3e50;
        }}
        
        .description, .reasoning, .suggestion {{
            margin: 15px 0;
            padding: 15px;
            border-radius: 6px;
        }}
        
        .description {{
            background: #e8f4f8;
            border-left: 4px solid #3498db;
        }}
        
        .reasoning {{
            background: #f0f7ff;
            border-left: 4px solid #5dade2;
        }}
        
        .suggestion {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
        }}
        
        .section-label {{
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 8px;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        /* Severity-specific colors */
        .critical .finding-header {{ background: #e74c3c; }}
        .high .finding-header {{ background: #e67e22; }}
        .medium .finding-header {{ background: #f39c12; }}
        .low .finding-header {{ background: #27ae60; }}
        .info .finding-header {{ background: #3498db; }}
        
        .confidence-badge {{
            background: rgba(255,255,255,0.2);
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.9em;
        }}
        
        .toc {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
        }}
        
        .toc h3 {{
            margin-bottom: 15px;
            color: #2c3e50;
        }}
        
        .toc ul {{
            list-style: none;
        }}
        
        .toc li {{
            margin: 8px 0;
        }}
        
        .toc a {{
            color: #3498db;
            text-decoration: none;
            padding: 5px 0;
            display: block;
        }}
        
        .toc a:hover {{
            color: #2980b9;
            text-decoration: underline;
        }}
        
        @media (max-width: 768px) {{
            .finding-meta {{
                grid-template-columns: 1fr;
            }}
            
            .stats {{
                grid-template-columns: 1fr;
            }}
            
            .contract-summary {{
                grid-template-columns: 1fr;
            }}
            
            .header {{
                padding: 20px;
            }}
            
            .content {{
                padding: 20px;
            }}
        }}
        
        @media print {{
            body {{
                background: white;
                padding: 0;
            }}
            
            .container {{
                box-shadow: none;
            }}
            
            .finding:hover {{
                transform: none;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🥄 Spoon Audit Security Report</h1>
            <div class="subtitle">Comprehensive Smart Contract Analysis</div>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-number">{contract_count}</div>
                <div class="stat-label">Contracts Analyzed</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{len(data.get('static', []))}</div>
                <div class="stat-label">Static Analysis Findings</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{len(data.get('ai', []))}</div>
                <div class="stat-label">AI Analysis Findings</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{len(data.get('static', [])) + len(data.get('ai', []))}</div>
                <div class="stat-label">Total Issues Found</div>
            </div>
        </div>
        
        <div class="content">
            <div class="finding-meta">
                <div class="meta-item">
                    <div class="meta-label">Contract Path</div>
                    <div class="meta-value">{data['path']}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">Analysis Date</div>
                    <div class="meta-value">{ts}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">Report Generated</div>
                    <div class="meta-value">{time.strftime("%Y-%m-%d %H:%M:%S")}</div>
                </div>
            </div>
"""
    
    # Add contract summary if multiple contracts
    if contract_count > 1:
        html_content += f"""
            <h2 class="section-title">📋 Contract Summary</h2>
            <div class="contract-summary">
"""
        for contract in data.get('contracts', []):
            html_content += f"""
                <div class="contract-card">
                    <div class="contract-name">{contract['name']}</div>
                    <div class="contract-stats">
                        {contract['functions_count']} functions • 
                        {contract['events_count']} events • 
                        {contract['modifiers_count']} modifiers
                    </div>
                </div>
"""
        html_content += "            </div>\n"
    
    html_content += f"""
            <div class="toc">
                <h3>📋 Table of Contents</h3>
                <ul>
                    <li><a href="#static-findings">🔧 Static Analysis Findings ({len(data.get('static', []))})</a></li>
                    <li><a href="#ai-findings">🤖 AI Analysis Findings ({len(data.get('ai', []))})</a></li>
                </ul>
            </div>
"""
    
    # Static Analysis Findings
    if data.get('static'):
        html_content += '<div id="static-findings"><h2 class="section-title">🔧 Static Analysis Findings</h2>\n'
        for i, finding in enumerate(data['static'], 1):
            severity_class = finding['severity'].lower()
            html_content += f"""
            <div class="finding {severity_class}">
                <div class="finding-header">
                    <span>{i}. {finding['title']}</span>
                    <span class="confidence-badge">{finding['tool']}</span>
                </div>
                <div class="finding-body">
                    <div class="finding-meta">
                        <div class="meta-item">
                            <div class="meta-label">Severity</div>
                            <div class="meta-value">{finding['severity'].upper()}</div>
                        </div>
                        <div class="meta-item">
                            <div class="meta-label">Tool</div>
                            <div class="meta-value">{finding['tool']}</div>
                        </div>
                        <div class="meta-item">
                            <div class="meta-label">Location</div>
                            <div class="meta-value">{finding['location']}</div>
                        </div>"""
            
            if finding.get('contract'):
                html_content += f"""
                        <div class="meta-item">
                            <div class="meta-label">Contract</div>
                            <div class="meta-value">{finding['contract']}</div>
                        </div>"""
            
            html_content += """
                    </div>
"""
            
            if finding.get('description'):
                html_content += f"""
                    <div class="description">
                        <div class="section-label">Description</div>
                        <div>{finding['description']}</div>
                    </div>
"""
            
            if finding.get('suggestion'):
                html_content += f"""
                    <div class="suggestion">
                        <div class="section-label">Suggestion</div>
                        <div>{finding['suggestion']}</div>
                    </div>
"""
            
            html_content += "                </div>\n            </div>\n"
        
        html_content += "</div>\n"
    
    # AI Analysis Findings
    if data.get('ai'):
        html_content += '<div id="ai-findings"><h2 class="section-title">🤖 AI Analysis Findings</h2>\n'
        for i, finding in enumerate(data['ai'], 1):
            severity_class = finding['severity'].lower()
            confidence = finding.get('confidence', 0)
            confidence_str = f"{confidence:.1f}" if isinstance(confidence, (int, float)) else str(confidence)
            
            html_content += f"""
            <div class="finding {severity_class}">
                <div class="finding-header">
                    <span>{i}. {finding['title']}</span>
                    <span class="confidence-badge">Confidence: {confidence_str}</span>
                </div>
                <div class="finding-body">
                    <div class="finding-meta">
                        <div class="meta-item">
                            <div class="meta-label">Severity</div>
                            <div class="meta-value">{finding['severity'].upper()}</div>
                        </div>
                        <div class="meta-item">
                            <div class="meta-label">Confidence</div>
                            <div class="meta-value">{confidence_str}</div>
                        </div>
                        <div class="meta-item">
                            <div class="meta-label">Location</div>
                            <div class="meta-value">{finding['location']}</div>
                        </div>"""
            
            if finding.get('contract'):
                html_content += f"""
                        <div class="meta-item">
                            <div class="meta-label">Contract</div>
                            <div class="meta-value">{finding['contract']}</div>
                        </div>"""
            
            html_content += """
                    </div>
"""
            
            if finding.get('description'):
                html_content += f"""
                    <div class="description">
                        <div class="section-label">Description</div>
                        <div>{finding['description']}</div>
                    </div>
"""
            
            if finding.get('reasoning'):
                html_content += f"""
                    <div class="reasoning">
                        <div class="section-label">Technical Reasoning</div>
                        <div>{finding['reasoning']}</div>
                    </div>
"""
            
            if finding.get('suggested_fix'):
                html_content += f"""
                    <div class="suggestion">
                        <div class="section-label">Suggested Fix</div>
                        <div>{finding['suggested_fix']}</div>
                    </div>
"""
            
            html_content += "                </div>\n            </div>\n"
        
        html_content += "</div>\n"
    
    html_content += """
        </div>
    </div>
    
    <script>
        // Smooth scrolling for table of contents
        document.querySelectorAll('.toc a').forEach(anchor => {
            anchor.addEventListener('click', function (e) {
                e.preventDefault();
                document.querySelector(this.getAttribute('href')).scrollIntoView({
                    behavior: 'smooth'
                });
            });
        });
        
        // Print functionality
        function printReport() {
            window.print();
        }
        
        // Add print button
        const header = document.querySelector('.header');
        const printBtn = document.createElement('button');
        printBtn.innerHTML = '🖨️ Print Report';
        printBtn.style.cssText = `
            background: rgba(255,255,255,0.2);
            border: none;
            color: white;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            margin-top: 20px;
        `;
        printBtn.onclick = printReport;
        header.appendChild(printBtn);
    </script>
</body>
</html>
"""
    
    with open(output_file, 'w') as f:
        f.write(html_content)
    
    if open_browser:
        try:
            import webbrowser
            import platform
            
            file_url = f'file://{Path(output_file).absolute()}'
            
            # Try different methods based on the platform
            if platform.system() == 'Darwin':  # macOS
                try:
                    import subprocess
                    subprocess.run(['open', str(Path(output_file).absolute())], check=True)
                except subprocess.CalledProcessError:
                    # Fallback to webbrowser
                    webbrowser.open(file_url)
            else:
                webbrowser.open(file_url)
                
        except Exception as e:
            console.print(f"[yellow]⚠️  Could not open browser automatically: {e}[/yellow]")
            console.print(f"[blue]📄 You can manually open: {Path(output_file).absolute()}[/blue]")

def export_pdf(data: dict, output_file: str):
    """Export report as PDF using multiple fallback methods"""
    
    # Method 1: Try WeasyPrint first
    try:
        from weasyprint import HTML, CSS
        from weasyprint.text.fonts import FontConfiguration
        
        # Generate HTML content first
        temp_html = output_file.replace('.pdf', '_temp.html')
        export_html(data, temp_html, open_browser=False)
        
        # Convert HTML to PDF
        font_config = FontConfiguration()
        html = HTML(filename=temp_html)
        
        # Custom CSS for PDF
        pdf_css = CSS(string='''
            @page {
                size: A4;
                margin: 1in;
            }
            
            body {
                background: white !important;
                padding: 0 !important;
            }
            
            .container {
                box-shadow: none !important;
            }
            
            .finding {
                page-break-inside: avoid;
                margin-bottom: 20px;
            }
            
            .section-title {
                page-break-after: avoid;
            }
        ''')
        
        html.write_pdf(output_file, stylesheets=[pdf_css], font_config=font_config)
        Path(temp_html).unlink(missing_ok=True)
        console.print(f"[green]✅ PDF report generated successfully using WeasyPrint[/green]")
        return
        
    except ImportError:
        console.print("[yellow]⚠️  WeasyPrint not available, trying alternative methods...[/yellow]")
    except OSError as e:
        console.print(f"[yellow]⚠️  WeasyPrint missing system dependencies, trying alternatives...[/yellow]")
    except Exception as e:
        console.print(f"[yellow]⚠️  WeasyPrint failed ({e}), trying alternatives...[/yellow]")
    
    # Method 2: Try pdfkit + wkhtmltopdf
    try:
        import pdfkit
        
        # Generate HTML content
        temp_html = output_file.replace('.pdf', '_temp.html')
        export_html(data, temp_html, open_browser=False)
        
        # Configure pdfkit options
        options = {
            'page-size': 'A4',
            'margin-top': '1in',
            'margin-right': '1in',
            'margin-bottom': '1in',
            'margin-left': '1in',
            'encoding': "UTF-8",
            'no-outline': None,
            'enable-local-file-access': None
        }
        
        pdfkit.from_file(temp_html, output_file, options=options)
        Path(temp_html).unlink(missing_ok=True)
        console.print(f"[green]✅ PDF report generated successfully using wkhtmltopdf[/green]")
        return
        
    except ImportError:
        console.print("[yellow]⚠️  pdfkit not available (pip install pdfkit), trying next method...[/yellow]")
    except Exception as e:
        console.print(f"[yellow]⚠️  pdfkit failed ({e}), trying next method...[/yellow]")
    
    # Method 3: Try reportlab for simple PDF
    try:
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
        import html
        
        # Create PDF using reportlab
        doc = SimpleDocTemplate(output_file, pagesize=A4, topMargin=1*inch)
        styles = getSampleStyleSheet()
        story = []
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            alignment=TA_CENTER,
            spaceAfter=30
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=16,
            alignment=TA_LEFT,
            spaceAfter=12,
            textColor=colors.darkblue
        )
        
        # Title
        story.append(Paragraph("🥄 Spoon Audit Security Report", title_style))
        story.append(Spacer(1, 20))
        
        # Contract info
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(data["timestamp"]))
        info_text = f"<b>Contract Path:</b> {html.escape(data['path'])}<br/>" \
                   f"<b>Analysis Date:</b> {ts}<br/>" \
                   f"<b>Contracts:</b> {len(data.get('contracts', []))}<br/>" \
                   f"<b>Static Findings:</b> {len(data.get('static', []))}<br/>" \
                   f"<b>AI Findings:</b> {len(data.get('ai', []))}"
        
        story.append(Paragraph(info_text, styles['Normal']))
        story.append(Spacer(1, 20))
        
        # Contract Summary
        if len(data.get('contracts', [])) > 1:
            story.append(Paragraph("Contract Summary", heading_style))
            for contract in data.get('contracts', []):
                contract_text = f"<b>{html.escape(contract['name'])}:</b> " \
                               f"{contract['functions_count']} functions, " \
                               f"{contract['events_count']} events, " \
                               f"{contract['modifiers_count']} modifiers"
                story.append(Paragraph(contract_text, styles['Normal']))
            story.append(Spacer(1, 20))
        
        # Static Analysis Findings
        if data.get('static'):
            story.append(Paragraph("🔧 Static Analysis Findings", heading_style))
            for i, finding in enumerate(data['static'], 1):
                finding_text = f"<b>{i}. {html.escape(finding['title'])}</b><br/>" \
                              f"<b>Severity:</b> {finding['severity'].upper()}<br/>" \
                              f"<b>Tool:</b> {html.escape(finding['tool'])}<br/>" \
                              f"<b>Location:</b> {html.escape(finding['location'])}<br/>"
                
                if finding.get('contract'):
                    finding_text += f"<b>Contract:</b> {html.escape(finding['contract'])}<br/>"
                
                if finding.get('description'):
                    finding_text += f"<b>Description:</b> {html.escape(finding['description'])}<br/>"
                
                if finding.get('suggestion'):
                    finding_text += f"<b>Suggestion:</b> {html.escape(finding['suggestion'])}<br/>"
                
                story.append(Paragraph(finding_text, styles['Normal']))
                story.append(Spacer(1, 12))
        
        # AI Analysis Findings
        if data.get('ai'):
            story.append(Paragraph("🤖 AI Analysis Findings", heading_style))
            for i, finding in enumerate(data['ai'], 1):
                confidence = finding.get('confidence', 0)
                confidence_str = f"{confidence:.1f}" if isinstance(confidence, (int, float)) else str(confidence)
                
                finding_text = f"<b>{i}. {html.escape(finding['title'])}</b><br/>" \
                              f"<b>Severity:</b> {finding['severity'].upper()}<br/>" \
                              f"<b>Confidence:</b> {confidence_str}<br/>" \
                              f"<b>Location:</b> {html.escape(finding['location'])}<br/>"
                
                if finding.get('contract'):
                    finding_text += f"<b>Contract:</b> {html.escape(finding['contract'])}<br/>"
                
                if finding.get('description'):
                    finding_text += f"<b>Description:</b> {html.escape(finding['description'])}<br/>"
                
                if finding.get('reasoning'):
                    finding_text += f"<b>Reasoning:</b> {html.escape(finding['reasoning'])}<br/>"
                
                if finding.get('suggested_fix'):
                    finding_text += f"<b>Suggested Fix:</b> {html.escape(finding['suggested_fix'])}<br/>"
                
                story.append(Paragraph(finding_text, styles['Normal']))
                story.append(Spacer(1, 12))
        
        # Build PDF
        doc.build(story)
        console.print(f"[green]✅ PDF report generated successfully using ReportLab[/green]")
        return
        
    except ImportError:
        console.print("[yellow]⚠️  ReportLab not available (pip install reportlab), trying next method...[/yellow]")
    except Exception as e:
        console.print(f"[yellow]⚠️  ReportLab failed ({e}), trying next method...[/yellow]")
    
    # Method 4: Try matplotlib to create a simple PDF
    try:
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
        import matplotlib.patches as patches
        
        with PdfPages(output_file) as pdf:
            # Create first page with title and summary
            fig, ax = plt.subplots(figsize=(8.5, 11))
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis('off')
            
            # Title
            ax.text(0.5, 0.9, '🥄 Spoon Audit Security Report', 
                   fontsize=20, weight='bold', ha='center')
            
            # Summary info
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(data["timestamp"]))
            summary_text = f"""Contract Path: {data['path']}
Analysis Date: {ts}
Contracts Analyzed: {len(data.get('contracts', []))}
Static Findings: {len(data.get('static', []))}
AI Findings: {len(data.get('ai', []))}
Total Issues: {len(data.get('static', [])) + len(data.get('ai', []))}"""
            
            ax.text(0.1, 0.7, summary_text, fontsize=12, va='top', family='monospace')
            
            # Add contract summary if multiple contracts
            y_pos = 0.5
            if len(data.get('contracts', [])) > 1:
                ax.text(0.1, y_pos, 'Contract Summary:', fontsize=14, weight='bold')
                y_pos -= 0.05
                for contract in data.get('contracts', []):
                    contract_text = f"• {contract['name']}: {contract['functions_count']} functions, " \
                                   f"{contract['events_count']} events, {contract['modifiers_count']} modifiers"
                    ax.text(0.15, y_pos, contract_text, fontsize=10)
                    y_pos -= 0.03
            
            pdf.savefig(fig, bbox_inches='tight')
            plt.close()
            
            # Add findings pages (simplified)
            all_findings = []
            for finding in data.get('static', []):
                all_findings.append(('Static', finding))
            for finding in data.get('ai', []):
                all_findings.append(('AI', finding))
            
            # Group findings into pages (max 5 per page)
            findings_per_page = 5
            for page_start in range(0, len(all_findings), findings_per_page):
                fig, ax = plt.subplots(figsize=(8.5, 11))
                ax.set_xlim(0, 1)
                ax.set_ylim(0, 1)
                ax.axis('off')
                
                y_pos = 0.95
                page_findings = all_findings[page_start:page_start + findings_per_page]
                
                for finding_type, finding in page_findings:
                    # Finding title
                    ax.text(0.05, y_pos, f"{finding_type} Finding: {finding['title'][:60]}...", 
                           fontsize=12, weight='bold')
                    y_pos -= 0.04
                    
                    # Finding details
                    details = f"Severity: {finding['severity'].upper()}"
                    if finding_type == 'AI' and 'confidence' in finding:
                        confidence = finding.get('confidence', 0)
                        conf_str = f"{confidence:.1f}" if isinstance(confidence, (int, float)) else str(confidence)
                        details += f" | Confidence: {conf_str}"
                    if finding.get('contract'):
                        details += f" | Contract: {finding['contract']}"
                    
                    ax.text(0.05, y_pos, details, fontsize=10, style='italic')
                    y_pos -= 0.03
                    
                    # Location
                    ax.text(0.05, y_pos, f"Location: {finding['location']}", fontsize=9)
                    y_pos -= 0.03
                    
                    # Description (truncated)
                    if finding.get('description'):
                        desc = finding['description'][:200] + "..." if len(finding['description']) > 200 else finding['description']
                        ax.text(0.05, y_pos, f"Description: {desc}", fontsize=9, wrap=True)
                        y_pos -= 0.06
                    
                    y_pos -= 0.02  # Space between findings
                
                pdf.savefig(fig, bbox_inches='tight')
                plt.close()
        
        console.print(f"[green]✅ PDF report generated successfully using Matplotlib[/green]")
        console.print("[blue]📝 Note: This is a simplified PDF format. For full formatting, install WeasyPrint dependencies.[/blue]")
        return
        
    except ImportError:
        console.print("[yellow]⚠️  Matplotlib not available (pip install matplotlib), trying final fallback...[/yellow]")
    except Exception as e:
        console.print(f"[yellow]⚠️  Matplotlib failed ({e}), trying final fallback...[/yellow]")
    
    # Final fallback: Generate HTML and provide instructions
    console.print(f"[red]❌ All PDF generation methods failed[/red]")
    console.print("[blue]💡 PDF Generation Options:[/blue]")
    console.print("[blue]   1. Install WeasyPrint dependencies:[/blue]")
    console.print("[blue]      • macOS: brew install pango[/blue]")
    console.print("[blue]      • Ubuntu: sudo apt-get install libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0[/blue]")
    console.print("[blue]      • Windows: Download GTK+ from https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer[/blue]")
    console.print("[blue]   2. Install wkhtmltopdf + pdfkit: pip install pdfkit[/blue]")
    console.print("[blue]   3. Install ReportLab: pip install reportlab[/blue]")
    console.print("[blue]   4. Install Matplotlib: pip install matplotlib[/blue]")
    
    # Fallback to HTML
    html_output = output_file.replace('.pdf', '.html')
    console.print(f"[cyan]📄 Generating HTML report instead: {html_output}[/cyan]")
    export_html(data, html_output, open_browser=False)
    console.print(f"[green]✅ HTML report exported to[/green] {html_output}")
    console.print("[blue]💡 You can print the HTML to PDF using your browser's print function[/blue]")

if __name__ == "__main__":
    main()