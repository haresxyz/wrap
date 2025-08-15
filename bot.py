from web3 import Web3
import time
import os
import json

# Load RPC URL from environment
taiko_rpc_url = os.getenv("TAIKO_RPC_URL")
if not taiko_rpc_url:
    raise RuntimeError("Missing TAIKO_RPC_URL in environment variables.")

web3 = Web3(Web3.HTTPProvider(taiko_rpc_url))

# Verify connection
if not web3.is_connected():
    raise RuntimeError("Error: Cannot connect to Taiko network.")

# Load credentials and addresses from environment variables
private_key = os.getenv("PRIVATE_KEY")
if not private_key:
    raise RuntimeError("Missing PRIVATE_KEY in environment variables.")

my_address_env = os.getenv("MY_ADDRESS")
if not my_address_env:
    raise RuntimeError("Missing MY_ADDRESS in environment variables.")
my_address = Web3.to_checksum_address(my_address_env)

weth_contract_env = os.getenv("WETH_CONTRACT_ADDRESS")
if not weth_contract_env:
    raise RuntimeError("Missing WETH_CONTRACT_ADDRESS in environment variables.")
weth_contract_address = Web3.to_checksum_address(weth_contract_env)

# ABI for deposit (wrap), withdraw (unwrap), and balanceOf (WETH)
weth_abi = '''
[
    {
        "constant":true,
        "inputs":[{"name":"account","type":"address"}],
        "name":"balanceOf",
        "outputs":[{"name":"balance","type":"uint256"}],
        "payable":false,
        "stateMutability":"view",
        "type":"function"
    },
    {
        "constant":false,
        "inputs":[{"name":"wad","type":"uint256"}],
        "name":"withdraw",
        "outputs":[],
        "payable":false,
        "stateMutability":"nonpayable",
        "type":"function"
    },
    {
        "constant":false,
        "inputs":[{"name":"wad","type":"uint256"}],
        "name":"deposit",
        "outputs":[],
        "payable":true,
        "stateMutability":"payable",
        "type":"function"
    }
]
'''

# Create WETH contract instance
weth_contract = web3.eth.contract(address=weth_contract_address, abi=weth_abi)

# Amount ETH/WETH to wrap/unwrap (in wei)
amount_in_wei = web3.to_wei(0.4, 'ether')

# Gas settings
gas_price_gwei = 0.025
max_priority_fee_per_gas = web3.to_wei(gas_price_gwei, 'gwei')
max_fee_per_gas = web3.to_wei(gas_price_gwei, 'gwei')

def check_eth_balance():
    return web3.eth.get_balance(my_address)

def check_weth_balance():
    return weth_contract.functions.balanceOf(my_address).call()

def get_next_nonce():
    return web3.eth.get_transaction_count(my_address)

def has_sufficient_balance(amount_in_wei, is_wrap=True):
    try:
        if is_wrap:
            gas_estimate = weth_contract.functions.deposit(amount_in_wei).estimate_gas({'from': my_address, 'value': amount_in_wei})
        else:
            gas_estimate = weth_contract.functions.withdraw(amount_in_wei).estimate_gas({'from': my_address})
        total_cost = max_priority_fee_per_gas * gas_estimate
        if is_wrap:
            return check_eth_balance() >= total_cost
        else:
            return check_weth_balance() >= amount_in_wei
    except Exception as e:
        print(f"Error checking balance: {e}")
        return False

def wait_for_confirmation(tx_hash, timeout=300):
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            receipt = web3.eth.get_transaction_receipt(tx_hash)
            if receipt and receipt['status'] == 1:
                print(f"Confirmed: Transaction {web3.to_hex(tx_hash)} succeeded.")
                return True
            elif receipt and receipt['status'] == 0:
                print(f"Failed: Transaction {web3.to_hex(tx_hash)} reverted.")
                return False
        except:
            pass
        time.sleep(30)
    print(f"Timeout: No confirmation for transaction {web3.to_hex(tx_hash)}.")
    return False

def wrap_eth_to_weth(amount_in_wei):
    if not has_sufficient_balance(amount_in_wei, is_wrap=True):
        print("Insufficient ETH balance for wrapping.")
        return False
    nonce = get_next_nonce()
    gas_estimate = weth_contract.functions.deposit(amount_in_wei).estimate_gas({'from': my_address, 'value': amount_in_wei})
    transaction = {
        'to': weth_contract_address,
        'chainId': 167000,
        'gas': gas_estimate,
        'maxFeePerGas': max_fee_per_gas,
        'maxPriorityFeePerGas': max_priority_fee_per_gas,
        'nonce': nonce,
        'value': amount_in_wei,
        'data': '0xd0e30db0'
    }
    signed_txn = web3.eth.account.sign_transaction(transaction, private_key)
    try:
        tx_hash = web3.eth.send_raw_transaction(signed_txn.raw_transaction)
        print(f"Wrap transaction sent. Tx Hash: {web3.to_hex(tx_hash)}")
        return wait_for_confirmation(tx_hash)
    except Exception as e:
        print(f"Error sending wrap transaction: {e}")
    return False

def unwrap_weth_to_eth(amount_in_wei):
    if not has_sufficient_balance(amount_in_wei, is_wrap=False):
        print("Insufficient WETH balance for unwrapping.")
        return False
    nonce = get_next_nonce()
    gas_estimate = weth_contract.functions.withdraw(amount_in_wei).estimate_gas({'from': my_address})
    transaction = {
        'to': weth_contract_address,
        'chainId': 167000,
        'gas': gas_estimate,
        'maxFeePerGas': max_fee_per_gas,
        'maxPriorityFeePerGas': max_priority_fee_per_gas,
        'nonce': nonce,
        'data': '0x2e1a7d4d' + amount_in_wei.to_bytes(32, 'big').hex()
    }
    signed_txn = web3.eth.account.sign_transaction(transaction, private_key)
    try:
        tx_hash = web3.eth.send_raw_transaction(signed_txn.raw_transaction)
        print(f"Unwrap transaction sent. Tx Hash: {web3.to_hex(tx_hash)}")
        return wait_for_confirmation(tx_hash)
    except Exception as e:
        print(f"Error sending unwrap transaction: {e}")
    return False

def save_transaction_status(wrap_counter, unwrap_counter, total_tx):
    status = {
        'wrap_counter': wrap_counter,
        'unwrap_counter': unwrap_counter,
        'total_tx': total_tx
    }
    with open('transaction_status.json', 'w') as f:
        json.dump(status, f)

def load_transaction_status():
    try:
        with open('transaction_status.json', 'r') as f:
            status = json.load(f)
        return status['wrap_counter'], status['unwrap_counter'], status['total_tx']
    except (FileNotFoundError, json.JSONDecodeError):
        return 0, 0, 0

wrap_counter, unwrap_counter, total_tx = load_transaction_status()

while total_tx < 90:
    if wrap_counter < 45 and total_tx < 90:
        if wrap_eth_to_weth(amount_in_wei):
            wrap_counter += 1
            total_tx += 1
            print(f"Total Transactions: {total_tx} (Wrapping: {wrap_counter})")
            save_transaction_status(wrap_counter, unwrap_counter, total_tx)

    if unwrap_counter < 45 and total_tx < 90:
        if unwrap_weth_to_eth(amount_in_wei):
            unwrap_counter += 1
            total_tx += 1
            print(f"Total Transactions: {total_tx} (Unwrapping: {unwrap_counter})")
            save_transaction_status(wrap_counter, unwrap_counter, total_tx)

    if total_tx >= 90:
        if os.path.exists('transaction_status.json'):
            os.remove('transaction_status.json')
            print("Transaction status file deleted after reaching 90 transactions.")
        break

    time.sleep(10)
