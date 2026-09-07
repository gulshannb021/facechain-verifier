import json
import os
from pathlib import Path

from dotenv import load_dotenv
from web3 import Web3

from hash_utils import hash_post


load_dotenv()


# ==============================
# Local Anvil Configuration
# ==============================

RPC_URL = os.getenv("LOCAL_RPC_URL")
PRIVATE_KEY = os.getenv("LOCAL_PRIVATE_KEY")

if not RPC_URL:
    raise ValueError("LOCAL_RPC_URL is missing from .env")

if not PRIVATE_KEY:
    raise ValueError("LOCAL_PRIVATE_KEY is missing from .env")


w3 = Web3(Web3.HTTPProvider(RPC_URL))

if not w3.is_connected():
    raise ConnectionError("Could not connect to local Anvil blockchain")

print("Connected to local Anvil blockchain")
print("Chain ID:", w3.eth.chain_id)


# ==============================
# Load Wallet
# ==============================

account = w3.eth.account.from_key(PRIVATE_KEY)

print("Wallet:", account.address)

balance = w3.eth.get_balance(account.address)

print(
    "Balance:",
    w3.from_wei(balance, "ether"),
    "ETH"
)


# ==============================
# Load Contract Information
# ==============================

abi = json.loads(
    Path(__file__).resolve().parent.joinpath(
        "PostVerification_abi.json"
    ).read_text()
)

contract_address = os.getenv("CONTRACT_ADDRESS")

if not contract_address:
    raise ValueError("CONTRACT_ADDRESS is missing from .env")

contract = w3.eth.contract(
    address=Web3.to_checksum_address(contract_address),
    abi=abi
)


# ==============================
# Load Person B's Discovered Post
# ==============================

post_data = json.loads(
    Path(__file__).resolve().parents[3].joinpath(
        "post.json"
    ).read_text()
)

if not post_data.get("canonical_data"):
    raise ValueError("post.json does not contain canonical_data")

post = post_data["canonical_data"]


# ==============================
# Generate SHA-256 Hash
# ==============================

post_hash = hash_post(post)

print("\nPost hash:")
print(post_hash)


# ==============================
# Convert SHA-256 Hex → bytes32
# ==============================

hash_bytes = bytes.fromhex(post_hash)

print("\nStoring hash on local blockchain...")


# ==============================
# Create Transaction
# ==============================

nonce = w3.eth.get_transaction_count(account.address)

transaction = contract.functions.storeHash(
    hash_bytes
).build_transaction(
    {
        "from": account.address,
        "nonce": nonce,
        "chainId": 31337,
        "gas": 150000,
        "gasPrice": w3.eth.gas_price,
    }
)


# ==============================
# Sign and Send Transaction
# ==============================

signed_transaction = account.sign_transaction(
    transaction
)

tx_hash = w3.eth.send_raw_transaction(
    signed_transaction.raw_transaction
)

print("Transaction sent:")
print(tx_hash.hex())


# ==============================
# Wait for Confirmation
# ==============================

print("\nWaiting for confirmation...")

receipt = w3.eth.wait_for_transaction_receipt(
    tx_hash
)


# ==============================
# Create Chain Record
# ==============================

chain_record = {
    "hash": post_hash,
    "contract_address": contract_address,
    "transaction_hash": receipt.transactionHash.hex(),
    "block_number": receipt.blockNumber,
    "chain_id": w3.eth.chain_id,
    "submitter": account.address
}

chain_record_path = Path(__file__).resolve().parent.joinpath(
    "chain_record.json"
)

chain_record_path.write_text(
    json.dumps(chain_record, indent=4),
    encoding="utf-8"
)


# ==============================
# Success
# ==============================

print("\n================================")
print("HASH STORED SUCCESSFULLY")
print("================================")

print("Transaction:", receipt.transactionHash.hex())
print("Block:", receipt.blockNumber)
print("Contract:", contract_address)
print("Hash:", post_hash)

print("\nChain record saved:")
print(chain_record_path)