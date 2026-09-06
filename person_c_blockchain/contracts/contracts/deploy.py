import json
import os
from pathlib import Path

from dotenv import load_dotenv
from web3 import Web3


load_dotenv()

RPC_URL = os.getenv("POLYGON_AMOY_RPC_URL")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")

if not RPC_URL:
    raise ValueError("POLYGON_AMOY_RPC_URL is missing from .env")

if not PRIVATE_KEY:
    raise ValueError("PRIVATE_KEY is missing from .env")


w3 = Web3(Web3.HTTPProvider(RPC_URL))

if not w3.is_connected():
    raise ConnectionError("Could not connect to Polygon Amoy")

print("Connected to Polygon Amoy")
print("Chain ID:", w3.eth.chain_id)


account = w3.eth.account.from_key(PRIVATE_KEY)

print("Deployment account:", account.address)

balance = w3.eth.get_balance(account.address)

print(
    "Balance:",
    w3.from_wei(balance, "ether"),
    "POL"
)


abi = json.loads(
    Path("PostVerification_abi.json").read_text()
)

bytecode = Path(
    "PostVerification_bytecode.txt"
).read_text().strip()


contract = w3.eth.contract(
    abi=abi,
    bytecode=bytecode
)


nonce = w3.eth.get_transaction_count(
    account.address
)


# Estimate the gas required for deployment
estimated_gas = contract.constructor().estimate_gas(
    {
        "from": account.address
    }
)

print("Estimated gas:", estimated_gas)


# Add a small safety margin
gas_limit = int(estimated_gas * 1.2)

print("Gas limit:", gas_limit)


transaction = contract.constructor().build_transaction(
    {
        "from": account.address,
        "nonce": nonce,
        "chainId": 80002,
        "gas": gas_limit,
        "gasPrice": w3.eth.gas_price,
    }
)


signed_transaction = account.sign_transaction(
    transaction
)


tx_hash = w3.eth.send_raw_transaction(
    signed_transaction.raw_transaction
)

print("Deployment transaction:", tx_hash.hex())

print("Waiting for confirmation...")

receipt = w3.eth.wait_for_transaction_receipt(
    tx_hash
)


print("\n================================")
print("CONTRACT DEPLOYED")
print("================================")

print("Contract address:", receipt.contractAddress)
print("Transaction hash:", receipt.transactionHash.hex())
print("Block number:", receipt.blockNumber)

print(
    "Explorer:",
    f"https://amoy.polygonscan.com/tx/{receipt.transactionHash.hex()}"
)