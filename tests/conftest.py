# tests/conftest.py
import sys
from pathlib import Path

# Add the project root to Python path so we can import analysis and cli modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Optional: Add some common test fixtures here
import pytest

@pytest.fixture
def sample_contract_path():
    """Fixture providing a path to a sample contract for testing"""
    return str(project_root / "tests" / "fixtures" / "sample.sol")

@pytest.fixture
def sample_contract_content():
    """Fixture providing sample Solidity contract content"""
    return """
pragma solidity ^0.8.0;

contract Sample {
    address public owner;
    
    constructor() {
        owner = msg.sender;
    }
    
    function transfer(address to) public {
        // Potential issue: using tx.origin
        require(tx.origin == owner, "Not authorized");
        payable(to).transfer(address(this).balance);
    }
}
"""