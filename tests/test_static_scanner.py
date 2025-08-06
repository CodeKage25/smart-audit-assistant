import pytest
from analysis.static_scanner import StaticScanner, StaticFinding
import tempfile
from pathlib import Path

BAD_SOL = """
pragma solidity ^0.8.0;
contract Bad {
    function foo() public {
        if (tx.origin == msg.sender) {
            // insecure
        }
    }
}
"""

def test_basic_checks(tmp_path):
    sol_file = tmp_path / "Bad.sol"
    sol_file.write_text(BAD_SOL)

    scanner = StaticScanner(debug=True)
    results = scanner.scan(str(sol_file), tools=["basic"])
    assert "basic" in results
    findings = results["basic"]
    assert any(isinstance(f, StaticFinding) for f in findings)
    assert any("tx.origin" in f.description or "Use of tx.origin" in f.title for f in findings)
