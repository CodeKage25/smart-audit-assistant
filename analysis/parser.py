import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from solcx import compile_source, compile_files, install_solc, set_solc_version
from solcx.exceptions import SolcError

@dataclass
class ParsedContract:
    """Represents a parsed Solidity contract."""
    name: str
    source_code: str
    ast: Dict[str, Any]
    bytecode: Optional[str]
    abi: Optional[List[Dict[str, Any]]]
    functions: List[Dict[str, Any]]
    events: List[Dict[str, Any]]
    modifiers: List[Dict[str, Any]]

class SolidityParser:
    """
    Handles parsing and compilation of Solidity contracts.
    Extracts AST, functions, events, and other metadata.
    """

    def __init__(self, debug: bool = False):
        self.debug = debug
        self.default_solc = "0.8.19"
        self._install_solc(self.default_solc)

    def _install_solc(self, version: str):
        try:
            install_solc(version)
            set_solc_version(version)
            if self.debug:
                print(f"[parser] solc {version} ready")
        except Exception as e:
            raise RuntimeError(f"Failed to install solc {version}: {e}")

    def parse_file(self, file_path: str) -> ParsedContract:
        path = Path(file_path)
        if not path.exists() or path.suffix != ".sol":
            raise FileNotFoundError(f"Invalid Solidity file: {file_path}")

        source = path.read_text(encoding="utf-8")
        pragma = self._extract_pragma(source)
        if pragma:
            self._install_solc(pragma)

        try:
            compiled = compile_files([str(path)], output_values=["abi", "bin", "ast"])
        except SolcError as e:
            raise RuntimeError(f"Compilation failed: {e}")

        key, data = next(iter(compiled.items()))
        contract_name = key.split(":")[-1]
        ast = data["ast"]
        abi = data.get("abi")
        bytecode = data.get("bin")

        functions = self._extract_defs(ast, "FunctionDefinition")
        events    = self._extract_defs(ast, "EventDefinition")
        modifiers = self._extract_defs(ast, "ModifierDefinition")

        return ParsedContract(
            name=contract_name,
            source_code=source,
            ast=ast,
            bytecode=bytecode,
            abi=abi,
            functions=functions,
            events=events,
            modifiers=modifiers,
        )

    def parse_source(self, source: str, contract_name: str = "Contract") -> ParsedContract:
        pragma = self._extract_pragma(source)
        if pragma:
            self._install_solc(pragma)

        try:
            compiled = compile_source(source, output_values=["abi", "bin", "ast"])
        except SolcError as e:
            raise RuntimeError(f"Compilation failed: {e}")

        key, data = next(iter(compiled.items()))
        name = key.split(":")[-1]
        ast = data["ast"]
        abi = data.get("abi")
        bytecode = data.get("bin")

        functions = self._extract_defs(ast, "FunctionDefinition")
        events    = self._extract_defs(ast, "EventDefinition")
        modifiers = self._extract_defs(ast, "ModifierDefinition")

        return ParsedContract(
            name=name,
            source_code=source,
            ast=ast,
            bytecode=bytecode,
            abi=abi,
            functions=functions,
            events=events,
            modifiers=modifiers,
        )

    def _extract_pragma(self, src: str) -> Optional[str]:
        match = re.search(r'pragma\s+solidity\s+[\^~]?(\d+\.\d+\.\d+)', src)
        return match.group(1) if match else None

    def _extract_defs(self, node: Any, node_type: str) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []

        def recurse(n):
            if isinstance(n, dict):
                if n.get("nodeType") == node_type:
                    results.append({
                        "name": n.get("name", ""),
                        "src": n.get("src", ""),
                        # extend with more fields if needed
                    })
                for v in n.values():
                    recurse(v)
            elif isinstance(n, list):
                for item in n:
                    recurse(item)

        recurse(node)
        return results
