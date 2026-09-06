import os
from dotenv import load_dotenv
from web3 import Web3

load_dotenv()

rpc_url = os.getenv("POLYGON_AMOY_RPC_URL")

if not rpc_url:
    raise ValueError("POLYGON_AMOY_RPC_URL is missing from .env")

w3 = Web3(Web3.HTTPProvider(rpc_url))

print("Connected:", w3.is_connected())

if w3.is_connected():
    print("Chain ID:", w3.eth.chain_id)
    print("Latest block:", w3.eth.block_number)