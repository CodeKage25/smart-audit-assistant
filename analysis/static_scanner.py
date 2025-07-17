import json
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

@dataclass
class StaticFinding:
    tool: str
    severity: str
    title: str
    description: str
    location: str
    line: Optional[int] = None

class StaticScanner:
    """
    Orchestrates static analysis tools for Solidity contracts:
    - Slither (JSON output)
    - Mythril (JSON output)
    - Basic regex checks
    """

    def __init__(self, debug: bool = False):
        self.debug = debug

    def scan(self, contract_path: str, tools: Optional[List[str]] = None) -> Dict[str, List[StaticFinding]]:
        path = Path(contract_path)
        if not path.exists():
            raise FileNotFoundError(f"Contract not found: {contract_path}")

        # Default tools
        selected = tools or ["slither", "mythril", "basic"]

        results: Dict[str, List[StaticFinding]] = {}
        for tool in selected:
            try:
                if tool == "slither":
                    findings = self._run_slither(path)
                elif tool == "mythril":
                    findings = self._run_mythril(path)
                elif tool == "basic":
                    findings = self._run_basic_checks(path)
                else:
                    findings = []
                results[tool] = findings
                if self.debug:
                    print(f"[static] {tool} -> {len(findings)} findings")
            except Exception as e:
                if self.debug:
                    print(f"[static] {tool} error: {e}")
                results[tool] = []
        return results

    def _run_slither(self, path: Path) -> List[StaticFinding]:
        findings: List[StaticFinding] = []
        try:
            proc = subprocess.run(
                ["slither", str(path), "--json", "-"],
                capture_output=True, text=True, timeout=60
            )
            data = json.loads(proc.stdout)
            for det in data.get("results", {}).get("detectors", []):
                loc = det.get("elements", [{}])[0].get("source_mapping", {})
                location = f"{loc.get('filename_short', '')}:{loc.get('lines',[0])[0]}"
                findings.append(StaticFinding(
                    tool="slither",
                    severity=det.get("impact", "Low").lower(),
                    title=det.get("check", ""),
                    description=det.get("description", ""),
                    location=location
                ))
        except Exception:
            if self.debug:
                print("[static] slither failed or not installed")
        return findings

    def _run_mythril(self, path: Path) -> List[StaticFinding]:
        findings: List[StaticFinding] = []
        try:
            proc = subprocess.run(
                ["myth", "analyze", str(path), "--output", "json"],
                capture_output=True, text=True, timeout=60
            )
            data = json.loads(proc.stdout)
            for issue in data.get("issues", []):
                findings.append(StaticFinding(
                    tool="mythril",
                    severity=issue.get("severity", "Medium").lower(),
                    title=issue.get("title", ""),
                    description=issue.get("description", ""),
                    location=f"{issue.get('filename','')}:{issue.get('lineno',0)}",
                    line=issue.get("lineno")
                ))
        except Exception:
            if self.debug:
                print("[static] mythril failed or not installed")
        return findings

    def _run_basic_checks(self, path: Path) -> List[StaticFinding]:
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        findings: List[StaticFinding] = []
        patterns = [
            (r"tx\.origin", "high", "Use of tx.origin", "Avoid tx.origin for auth"),
            (r"block\.timestamp", "medium", "Block timestamp dependency", "Timestamp can be manipulated"),
            (r"\.call\s*\(", "medium", "Low-level call", "Check return value of call"),
            (r"suicide\s*\(", "high", "Deprecated suicide()", "Use selfdestruct instead"),
        ]
        for idx, line in enumerate(lines, start=1):
            for pat, sev, title, desc in patterns:
                if re.search(pat, line):
                    findings.append(StaticFinding(
                        tool="basic",
                        severity=sev,
                        title=title,
                        description=desc,
                        location=f"{path.name}:{idx}",
                        line=idx
                    ))
        return findings
