import json
import os
from pathlib import Path

from dotenv import load_dotenv
from web3 import Web3

from hash_utils import hash_post


load_dotenv()

RPC_URL = os.getenv("POLYGON_AMOY_RPC_URL")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS")

if not RPC_URL:
    raise ValueError("POLYGON_AMOY_RPC_URL is missing from .env")

if not CONTRACT_ADDRESS:
    raise ValueError("CONTRACT_ADDRESS is missing from .env")


w3 = Web3(Web3.HTTPProvider(RPC_URL))

if not w3.is_connected():
    raise ConnectionError("Could not connect to Polygon Amoy")

print("Connected to Polygon Amoy")
print("Chain ID:", w3.eth.chain_id)


# Load contract ABI
abi = json.loads(
    Path("PostVerification_abi.json").read_text()
)

contract = w3.eth.contract(
    address=Web3.to_checksum_address(CONTRACT_ADDRESS),
    abi=abi
)


def verify_post(post):
    """
    Hash the supplied post and check whether
    that hash exists on the blockchain.
    """

    post_hash = hash_post(post)

    print("\nCalculated SHA-256:")
    print(post_hash)

    hash_bytes = bytes.fromhex(post_hash)

    exists, timestamp, submitter = contract.functions.verifyHash(
        hash_bytes
    ).call()

    if exists:
        print("\n✅ VERIFICATION SUCCESSFUL")
        print("The post matches a hash stored on Polygon Amoy.")
        print("Timestamp:", timestamp)
        print("Submitter:", submitter)
    else:
        print("\n❌ VERIFICATION FAILED")
        print("This exact post was not found on the blockchain.")

    return exists


if __name__ == "__main__":

    # Temporary test post
    post = {
        "platform": "Instagram",
        "post_url": "https://example.com/post/123",
        "caption": "TAMPERED DATA",
        "author": "test_user"
    }

    verify_post(post)
