import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


try:
    from solcx import compile_source, compile_files, install_solc, set_solc_version
    from solcx.exceptions import SolcError
    SOLCX_AVAILABLE = True
except ImportError:
    SOLCX_AVAILABLE = False
   
    class SolcError(Exception):
        pass

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
        if SOLCX_AVAILABLE:
            self._install_solc(self.default_solc)
        elif debug:
            print("[parser] solcx not available - using mock mode")

    def _install_solc(self, version: str):
        if not SOLCX_AVAILABLE:
            if self.debug:
                print(f"[parser] mock solc {version} (solcx not installed)")
            return
        
        try:
            install_solc(version)
            set_solc_version(version)
            if self.debug:
                print(f"[parser] solc {version} ready")
        except Exception as e:
            raise RuntimeError(f"Failed to install solc {version}: {e}")

    def parse_file(self, file_path: str) -> List[ParsedContract]:
        """Parse a single .sol file OR all .sol files in a directory"""
        path = Path(file_path)
        
        # If it's a directory, find all .sol files
        if path.is_dir():
            sol_files = list(path.glob("*.sol"))
            if not sol_files:
                # Look recursively for .sol files
                sol_files = list(path.rglob("*.sol"))
            
            if not sol_files:
                raise FileNotFoundError(f"No .sol files found in directory: {file_path}")
            
            if self.debug:
                print(f"[parser] Found {len(sol_files)} .sol files to parse")
            
            # Parse all files
            contracts = []
            for sol_file in sol_files:
                try:
                    contract = self._parse_single_file(sol_file)
                    contracts.append(contract)
                    if self.debug:
                        print(f"[parser] Parsed: {sol_file} -> {contract.name}")
                except Exception as e:
                    if self.debug:
                        print(f"[parser] Failed to parse {sol_file}: {e}")
                    continue
            
            if not contracts:
                raise RuntimeError(f"Failed to parse any .sol files in: {file_path}")
            
            return contracts
        
        # Handle single file
        return [self._parse_single_file(path)]

    def _parse_single_file(self, file_path: Path) -> ParsedContract:
        """Parse a single .sol file"""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if file_path.suffix != ".sol":
            raise FileNotFoundError(f"Not a Solidity file: {file_path}")

        source = file_path.read_text(encoding="utf-8")
        
        if not SOLCX_AVAILABLE:
            # Extract contract name from source for mock mode
            contract_name = self._extract_contract_name(source) or file_path.stem
            return self._create_mock_contract(contract_name, source)
        
        pragma = self._extract_pragma(source)
        if pragma:
            self._install_solc(pragma)

        try:
            compiled = compile_files([str(file_path)], output_values=["abi", "bin", "ast"])
        except SolcError as e:
            raise RuntimeError(f"Compilation failed for {file_path}: {e}")

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
        if not SOLCX_AVAILABLE:
            extracted_name = self._extract_contract_name(source) or contract_name
            return self._create_mock_contract(extracted_name, source)
            
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

    def _extract_contract_name(self, source: str) -> Optional[str]:
        """Extract the contract name from Solidity source code"""
       
        match = re.search(r'contract\s+(\w+)', source)
        if match:
            return match.group(1)
        
        # Look for interface definition
        match = re.search(r'interface\s+(\w+)', source)
        if match:
            return match.group(1)
        
        # Look for library definition
        match = re.search(r'library\s+(\w+)', source)
        if match:
            return match.group(1)
        
        return None

    def _create_mock_contract(self, name: str, source: str) -> ParsedContract:
        """Create a mock contract for testing when solcx is not available"""
        # Extract basic info from source using regex
        functions = []
        events = []
        modifiers = []
        
        # Basic regex parsing for testing
        func_matches = re.findall(r'function\s+(\w+)', source)
        event_matches = re.findall(r'event\s+(\w+)', source)
        modifier_matches = re.findall(r'modifier\s+(\w+)', source)
        
        functions = [{"name": f, "src": ""} for f in func_matches]
        events = [{"name": e, "src": ""} for e in event_matches]
        modifiers = [{"name": m, "src": ""} for m in modifier_matches]
        
        return ParsedContract(
            name=name,
            source_code=source,
            ast={"nodeType": "SourceUnit", "children": []},
            bytecode="0x608060405234801561001057600080fd5b50",  
            abi=[],
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