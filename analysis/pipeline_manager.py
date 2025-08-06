"""
Enhanced Pipeline Manager for Smart Contract Analysis
Handles orchestration of multiple analysis tools and AI models
"""

import os
import time
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass
from rich.console import Console

console = Console()

# ---------------------------
# Config & Core Manager
# ---------------------------

@dataclass
class PipelineConfig:
    """Configuration for analysis pipeline"""
    parallel_execution: bool = True
    cache_enabled: bool = True
    timeout_seconds: int = 300
    max_concurrent_tools: int = 3
    retry_attempts: int = 2


class PipelineManager:
    """
    Manages the analysis pipeline orchestration
    """
    def __init__(self, debug: bool = False):
        self.debug = debug
        self.config = PipelineConfig()
        self.console = Console()
        if self.debug:
            self.console.log("[yellow]PipelineManager initialized (debug ON)[/yellow]")

    async def validate_paths(self, path: str) -> List[str]:
        """
        Validate and collect all Solidity files from the given path
        """
        validated_paths: List[str] = []
        path_obj = Path(path)

        if not path_obj.exists():
            if self.debug:
                console.log(f"[red]Path does not exist: {path}[/red]")
            return []

        if path_obj.is_file():
            if path_obj.suffix.lower() == ".sol":
                validated_paths.append(str(path_obj))
                if self.debug:
                    console.log(f"[green]Added single file: {path_obj}[/green]")
            else:
                if self.debug:
                    console.log(f"[yellow]File is not a Solidity file: {path_obj}[/yellow]")

        elif path_obj.is_dir():
            exclude_dirs = {'node_modules', '.git', 'build', 'dist', 'out', 'artifacts', 'cache', '.venv', 'venv'}
            for sol_file in path_obj.rglob("*.sol"):
                # Skip excluded directories (any segment)
                if any(part in exclude_dirs for part in sol_file.parts):
                    if self.debug:
                        console.log(f"[yellow]Excluded file: {sol_file}[/yellow]")
                    continue
                validated_paths.append(str(sol_file))

        validated_paths.sort()
        if self.debug:
            console.log(f"[blue]Total validated .sol paths: {len(validated_paths)}[/blue]")
        return validated_paths

    def should_use_parallel(self, tool_count: int, file_count: int) -> bool:
        """Decide if parallel execution should be used based on workload"""
        if not self.config.parallel_execution:
            return False
        return (tool_count > 1 and file_count >= 1) or (file_count > 2 and tool_count >= 1)

    async def execute_with_timeout(self, coro, timeout: Optional[int] = None) -> Any:
        """Execute a coroutine with timeout handling"""
        timeout = timeout or self.config.timeout_seconds
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            if self.debug:
                console.log(f"[red]Operation timed out after {timeout} seconds[/red]")
            raise

    def get_cache_key(self, file_path: str, tool: str, file_hash: Optional[str] = None) -> str:
        """Generate a (currently non-persisted) cache key for analysis results"""
        if file_hash is None:
            try:
                stat = os.stat(file_path)
                file_hash = str(int(stat.st_mtime))
            except (OSError, IOError):
                file_hash = "unknown"
        return f"{tool}:{Path(file_path).name}:{file_hash}"

    def is_cache_valid(self, cache_key: str) -> bool:
        """Stub: Always False until a store is wired up"""
        return self.config.cache_enabled and False

    def get_cached_result(self, cache_key: str) -> Optional[Any]:
        """Stub: No cache backend yet"""
        return None

    def cache_result(self, cache_key: str, result: Any) -> bool:
        """Stub: No cache backend yet"""
        if self.debug:
            console.log(f"[blue]Would cache result for key: {cache_key}[/blue]")
        return self.config.cache_enabled

    async def run_tool_with_retry(self, tool_func, *args, **kwargs) -> Any:
        """Run a tool function with retry + simple backoff"""
        last_exc: Optional[Exception] = None
        for attempt in range(self.config.retry_attempts + 1):
            try:
                if self.debug and attempt > 0:
                    console.log(f"[yellow]Retry attempt {attempt}[/yellow]")
                return await tool_func(*args, **kwargs) if asyncio.iscoroutinefunction(tool_func) \
                       else tool_func(*args, **kwargs)
            except Exception as e:
                last_exc = e
                if self.debug:
                    console.log(f"[red]Tool failed (attempt {attempt + 1}): {e}[/red]")
                if attempt < self.config.retry_attempts:
                    await asyncio.sleep(2 ** attempt)
        if last_exc:
            raise last_exc
        raise RuntimeError("Tool execution failed after all retry attempts")

    def get_pipeline_stats(self) -> Dict[str, Any]:
        """Report current config & debug status"""
        return {
            "config": {
                "parallel_execution": self.config.parallel_execution,
                "cache_enabled": self.config.cache_enabled,
                "timeout_seconds": self.config.timeout_seconds,
                "max_concurrent_tools": self.config.max_concurrent_tools,
                "retry_attempts": self.config.retry_attempts,
            },
            "debug_mode": self.debug,
        }

    def optimize_pipeline_config(self, file_count: int, tool_count: int) -> None:
        """Heuristic tuning based on workload"""
        total = file_count * tool_count
        if total > 10:
            self.config.max_concurrent_tools = min(4, tool_count)
        elif total > 5:
            self.config.max_concurrent_tools = min(3, tool_count)
        else:
            self.config.max_concurrent_tools = min(2, tool_count)
        base_timeout = 60
        self.config.timeout_seconds = base_timeout + (file_count * tool_count * 10)
        if self.debug:
            console.log(
                f"[blue]Optimized config -> max_concurrent: {self.config.max_concurrent_tools}, "
                f"timeout: {self.config.timeout_seconds}s[/blue]"
            )

# ---------------------------
# Minimal Pipelines
# ---------------------------

# Lazy imports so this module is importable even if deps are missing
try:
    from analysis.parser import SolidityParser
    from analysis.static_scanner import StaticScanner
    from analysis.ai_analyzer import AIAnalyzer
except Exception:
    SolidityParser = None  # type: ignore
    StaticScanner = None   # type: ignore
    AIAnalyzer = None      # type: ignore


def _require_components():
    missing = []
    if SolidityParser is None: missing.append("analysis.parser.SolidityParser")
    if StaticScanner is None:  missing.append("analysis.static_scanner.StaticScanner")
    if AIAnalyzer is None:     missing.append("analysis.ai_analyzer.AIAnalyzer")
    if missing:
        raise ImportError("Missing analysis components: " + ", ".join(missing))


def _as_list(x: Union[Any, List[Any]]) -> List[Any]:
    """Ensure parse result is list-like for uniform downstream handling."""
    if x is None:
        return []
    if isinstance(x, list):
        return x
    # Some parsers return a single ParsedContract
    return [x]


async def _parse_and_static(paths: List[str], debug: bool) -> Dict[str, Any]:
    """
    Parse contracts and run static scanners per path.

    Returns:
        {
          "parsed": { path: [ParsedContract, ...] },
          "static": { path: { tool: [StaticFinding, ...], ... } }
        }
    """
    parsed_map: Dict[str, List[Any]] = {}
    static_map: Dict[str, Dict[str, List[Any]]] = {}

    for path in paths:
        # Parse
        parser = SolidityParser(debug=debug)  # type: ignore
        parsed_contracts = parser.parse_file(path)
        parsed_map[path] = _as_list(parsed_contracts)

        # Static
        scanner = StaticScanner(debug=debug)  # type: ignore
        static_map[path] = scanner.scan(path)  # expects {tool: [findings]}

    return {"parsed": parsed_map, "static": static_map}


def create_pipeline_manager(debug: bool = False) -> PipelineManager:
    """Backwards-compatible factory used by external scripts."""
    return PipelineManager(debug=debug)


async def run_spoon_analysis(
    contract_paths: List[str],
    agent_type: str = "react",   # "react" | "spoon_react_mcp" | "custom"
    debug: bool = False,
) -> Dict[str, Any]:
    """
    SpoonOS agent pipeline:
    validate -> parse -> static scan -> AI (Spoon agent) -> summary
    """
    _require_components()
    pm = PipelineManager(debug=debug)

    # Validate
    validated: List[str] = []
    for p in contract_paths:
        validated.extend(await pm.validate_paths(p))
    if not validated:
        raise ValueError("No valid Solidity files found")

    t0 = time.time()

    # Parse + static
    ps = await _parse_and_static(validated, debug=debug)

    # AI (Spoon agent)
    ai = AIAnalyzer(debug=debug, use_spoon_agent=True, spoon_agent_type=agent_type)  # type: ignore
    findings_by_path: Dict[str, List[Any]] = {}
    total_findings = 0

    for path in validated:
        per_contract_findings: List[Any] = []
        for contract in ps["parsed"].get(path, []):
            # static context for that path: {tool: [findings]}
            static_ctx = ps["static"].get(path, {})
            try:
                per_contract_findings.extend(ai.analyze(path, contract, static_ctx))
            except Exception as e:
                if debug:
                    console.log(f"[red]AI analysis error for {Path(path).name}: {e}[/red]")
        if per_contract_findings:
            findings_by_path[path] = per_contract_findings
            total_findings += len(per_contract_findings)

    results: Dict[str, Any] = {
        "pipeline": "spoon-powered",
        "status": "completed",
        "total_duration": time.time() - t0,
        "stages": {
            "parse": {"status": "completed"},
            "static_full": {"status": "completed"},
            "spoon_analysis": {
                "status": "completed",
                "results": {
                    "findings": findings_by_path,
                    "agent_stats": {
                        "agent_type": agent_type,
                        "contracts_analyzed": len(validated),
                        "contracts_with_findings": sum(1 for v in findings_by_path.values() if v),
                        "total_findings": total_findings,
                    },
                },
            },
        },
        "summary": {"total_findings": total_findings},
    }
    return results


async def run_openai_analysis(
    contract_paths: List[str],
    debug: bool = False,
) -> Dict[str, Any]:
    """
    OpenAI-powered pipeline:
    validate -> parse -> static scan -> AI (OpenAI direct) -> summary
    """
    _require_components()
    pm = PipelineManager(debug=debug)

    validated: List[str] = []
    for p in contract_paths:
        validated.extend(await pm.validate_paths(p))
    if not validated:
        raise ValueError("No valid Solidity files found")

    t0 = time.time()

    ps = await _parse_and_static(validated, debug=debug)

    # AI (OpenAI direct)
    ai = AIAnalyzer(debug=debug, use_spoon_agent=False)  # type: ignore
    findings_by_path: Dict[str, List[Any]] = {}
    total_findings = 0

    for path in validated:
        per_contract_findings: List[Any] = []
        for contract in ps["parsed"].get(path, []):
            static_ctx = ps["static"].get(path, {})
            try:
                per_contract_findings.extend(ai.analyze(path, contract, static_ctx))
            except Exception as e:
                if debug:
                    console.log(f"[red]OpenAI analysis error for {Path(path).name}: {e}[/red]")
        if per_contract_findings:
            findings_by_path[path] = per_contract_findings
            total_findings += len(per_contract_findings)

    results: Dict[str, Any] = {
        "pipeline": "openai-powered",
        "status": "completed",
        "total_duration": time.time() - t0,
        "stages": {
            "parse": {"status": "completed"},
            "static_full": {"status": "completed"},
            "ai_single": {
                "status": "completed",
                "results": {
                    "findings": findings_by_path,
                    "model_stats": {
                        "engine": "openai",
                        "contracts_analyzed": len(validated),
                        "contracts_with_findings": sum(1 for v in findings_by_path.values() if v),
                        "total_findings": total_findings,
                    },
                },
            },
        },
        "summary": {"total_findings": total_findings},
    }
    return results


async def run_static_only(
    contract_paths: List[str],
    debug: bool = False,
) -> Dict[str, Any]:
    """
    Static-only pipeline:
    validate -> parse -> static scan -> summary
    """
    _require_components()
    pm = PipelineManager(debug=debug)

    validated: List[str] = []
    for p in contract_paths:
        validated.extend(await pm.validate_paths(p))
    if not validated:
        raise ValueError("No valid Solidity files found")

    t0 = time.time()
    ps = await _parse_and_static(validated, debug=debug)

    # Count static findings
    total_static = 0
    static_by_path: Dict[str, Dict[str, List[Any]]] = {}
    for path in validated:
        static_by_path[path] = ps["static"][path]
        for tool_findings in ps["static"][path].values():
            total_static += len(tool_findings)

    results: Dict[str, Any] = {
        "pipeline": "static-only",
        "status": "completed",
        "total_duration": time.time() - t0,
        "stages": {
            "parse": {"status": "completed"},
            "static_full": {
                "status": "completed",
                "results": {"findings": static_by_path},
            },
        },
        "summary": {"total_findings": total_static},
    }
    return results


async def run_pipeline_analysis(
    contract_paths: List[str],
    pipeline_name: str = "spoon-powered",
    custom_config: Optional[Dict[str, Any]] = None,
    debug: bool = False,
) -> Dict[str, Any]:
    """
    Compatibility wrapper supporting:
      - "spoon-powered"   (SpoonOS agent via AIAnalyzer)
      - "openai-powered"  (OpenAI via AIAnalyzer)
      - "static-only"     (no AI)
    """
    custom_config = custom_config or {}
    if pipeline_name == "spoon-powered":
        agent_type = custom_config.get("spoon_agent_type", "react")
        return await run_spoon_analysis(contract_paths, agent_type=agent_type, debug=debug)
    elif pipeline_name == "openai-powered":
        return await run_openai_analysis(contract_paths, debug=debug)
    elif pipeline_name == "static-only":
        return await run_static_only(contract_paths, debug=debug)
    elif "spoon_agent_type" in custom_config:
        # If someone passes a spoon agent type with any name, still do spoon
        agent_type = custom_config.get("spoon_agent_type", "react")
        return await run_spoon_analysis(contract_paths, agent_type=agent_type, debug=debug)
    else:
        raise NotImplementedError(
            f"Pipeline '{pipeline_name}' is not implemented in this lightweight manager. "
            f"Use 'spoon-powered', 'openai-powered', or 'static-only'."
        )
