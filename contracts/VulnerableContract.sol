// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title VulnerableContract
 * @dev A deliberately vulnerable contract for testing security analysis tools
 */
contract VulnerableContract {
    mapping(address => uint256) public balances;
    address public owner;
    bool private locked;
    
    event Deposit(address indexed user, uint256 amount);
    event Withdrawal(address indexed user, uint256 amount);
    
    modifier onlyOwner() {
        require(msg.sender == owner, "Not the owner");
        _;
    }
    
    modifier noReentrancy() {
        require(!locked, "Reentrant call");
        locked = true;
        _;
        locked = false;
    }
    
    constructor() {
        owner = msg.sender;
    }
    
    // VULNERABILITY 1: Reentrancy attack possible
    function withdraw(uint256 amount) public {
        require(balances[msg.sender] >= amount, "Insufficient balance");
        
        // External call before state change (vulnerable to reentrancy)
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "Transfer failed");
        
        balances[msg.sender] -= amount; // State change after external call
        
        emit Withdrawal(msg.sender, amount);
    }
    
    // VULNERABILITY 2: Use of tx.origin for authorization
    function emergencyWithdraw() public {
        require(tx.origin == owner, "Not authorized"); // Should use msg.sender
        payable(tx.origin).transfer(address(this).balance);
    }
    
    // VULNERABILITY 3: Block timestamp dependency
    function timeLock() public view returns(bool) {
        return block.timestamp > 1234567890; // Timestamp can be manipulated
    }
    
    // VULNERABILITY 4: Unchecked external call
    function unsafeTransfer(address to, uint256 amount) public onlyOwner {
        to.call{value: amount}(""); // Return value not checked
    }
    
    // VULNERABILITY 5: Integer overflow (though Solidity 0.8+ has built-in checks)
    function deposit() public payable {
        balances[msg.sender] += msg.value;
        emit Deposit(msg.sender, msg.value);
    }
    
    // VULNERABILITY 6: Denial of Service with gas limit
    function massTransfer(address[] memory recipients, uint256 amount) public onlyOwner {
        for(uint i = 0; i < recipients.length; i++) { // Unbounded loop
            payable(recipients[i]).transfer(amount);
        }
    }
    
    // VULNERABILITY 7: Access control issue
    function changeOwner(address newOwner) public {
        // Missing access control - anyone can change owner!
        owner = newOwner;
    }
    
    // GOOD: Secure withdrawal function
    function secureWithdraw(uint256 amount) public noReentrancy {
        require(balances[msg.sender] >= amount, "Insufficient balance");
        
        // State change before external call (follows checks-effects-interactions)
        balances[msg.sender] -= amount;
        
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "Transfer failed");
        
        emit Withdrawal(msg.sender, amount);
    }
    
    // Allow contract to receive ether
    receive() external payable {
        balances[msg.sender] += msg.value;
        emit Deposit(msg.sender, msg.value);
    }
    
    // Get contract balance
    function getBalance() public view returns (uint256) {
        return address(this).balance;
    }
}