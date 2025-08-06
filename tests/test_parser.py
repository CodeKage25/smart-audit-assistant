import pytest
from analysis.parser import SolidityParser, ParsedContract
import tempfile
from pathlib import Path

SAMPLE_SOL = """
pragma solidity ^0.8.0;

contract Test {
    uint public x;

    function setX(uint _x) public {
        x = _x;
    }

    event XSet(address indexed setter, uint newValue);
}
"""

def test_parse_source_and_file(tmp_path):
    # Write sample .sol file
    sol_file = tmp_path / "Test.sol"
    sol_file.write_text(SAMPLE_SOL)

    parser = SolidityParser(debug=True)
    # parse from file
    parsed_file: ParsedContract = parser.parse_file(str(sol_file))
    assert parsed_file.name == "Test"
    assert "x" in parsed_file.source_code
    assert any(fn["name"] == "setX" for fn in parsed_file.functions)
    assert any(ev["name"] == "XSet" for ev in parsed_file.events)

    # parse from source string
    parsed_src: ParsedContract = parser.parse_source(SAMPLE_SOL)
    assert parsed_src.name == "Test"
    assert parsed_src.bytecode is not None
    assert isinstance(parsed_src.ast, dict)
