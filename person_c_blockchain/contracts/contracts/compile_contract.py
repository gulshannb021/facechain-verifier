import json
from pathlib import Path

from solcx import compile_standard, install_solc


install_solc("0.8.20")

contract_path = Path("contracts/PostVerification.sol")
source = contract_path.read_text()

compiled = compile_standard(
    {
        "language": "Solidity",
        "sources": {
            "PostVerification.sol": {
                "content": source
            }
        },
        "settings": {
            "outputSelection": {
                "*": {
                    "*": ["abi", "evm.bytecode"]
                }
            }
        },
    },
    solc_version="0.8.20",
)

contract = compiled["contracts"]["PostVerification.sol"]["PostVerification"]

Path("PostVerification_abi.json").write_text(
    json.dumps(contract["abi"], indent=2)
)

Path("PostVerification_bytecode.txt").write_text(
    contract["evm"]["bytecode"]["object"]
)

print("Contract compiled successfully.")
print("ABI: PostVerification_abi.json")
print("Bytecode: PostVerification_bytecode.txt")