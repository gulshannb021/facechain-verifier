import json
import os
from pathlib import Path

from dotenv import load_dotenv
from web3 import Web3

from hash_utils import hash_post


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


# Load wallet
account = w3.eth.account.from_key(PRIVATE_KEY)

print("Wallet:", account.address)

balance = w3.eth.get_balance(account.address)

print(
    "Balance:",
    w3.from_wei(balance, "ether"),
    "POL"
)


# Load contract information
abi = json.loads(
    Path("PostVerification_abi.json").read_text()
)

contract_address = os.getenv("CONTRACT_ADDRESS")

if not contract_address:
    raise ValueError("CONTRACT_ADDRESS is missing from .env")

contract = w3.eth.contract(
    address=Web3.to_checksum_address(contract_address),
    abi=abi
)


# Temporary test post
post = {
    "platform": "Instagram",
    "post_url": "https://example.com/post/123",
    "caption": "Renewable energy project",
    "author": "test_user"
}


# Generate SHA-256 hash
post_hash = hash_post(post)

print("\nPost hash:")
print(post_hash)


# Convert SHA-256 hex → bytes32
hash_bytes = bytes.fromhex(post_hash)

print("\nStoring hash on blockchain...")


nonce = w3.eth.get_transaction_count(account.address)


transaction = contract.functions.storeHash(
    hash_bytes
).build_transaction(
    {
        "from": account.address,
        "nonce": nonce,
        "chainId": 80002,
        "gas": 150000,
        "gasPrice": w3.eth.gas_price,
    }
)


signed_transaction = account.sign_transaction(transaction)


tx_hash = w3.eth.send_raw_transaction(
    signed_transaction.raw_transaction
)


print("Transaction sent:")
print(tx_hash.hex())


print("\nWaiting for confirmation...")


receipt = w3.eth.wait_for_transaction_receipt(
    tx_hash
)


print("\n================================")
print("HASH STORED SUCCESSFULLY")
print("================================")

print("Transaction:", receipt.transactionHash.hex())
print("Block:", receipt.blockNumber)

print(
    "Explorer:",
    f"https://amoy.polygonscan.com/tx/{receipt.transactionHash.hex()}"
)