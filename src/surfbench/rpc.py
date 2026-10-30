"""Independent RPC and account decoding primitives, also used by fixture tools."""
import base64
import json
import struct
import time
from urllib.request import Request, urlopen
from solders.pubkey import Pubkey

TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
ASSOCIATED_TOKEN_PROGRAM = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
SYSTEM_PROGRAM = "11111111111111111111111111111111"

class RpcError(RuntimeError):
    def __init__(self, method, error):
        self.method, self.error = method, error
        super().__init__(f"{method}: {json.dumps(error)}")

class RPC:
    def __init__(self, url="http://127.0.0.1:8899", timeout=5):
        self.url, self.timeout, self.sequence = url, timeout, 0

    def call(self, method, *params):
        self.sequence += 1
        request = Request(self.url, json.dumps({"jsonrpc":"2.0", "id":self.sequence,
                         "method":method, "params":list(params)}).encode(),
                         {"Content-Type":"application/json"})
        with urlopen(request, timeout=self.timeout) as response:
            body = json.load(response)
        if body.get("id") != self.sequence:
            raise RuntimeError("RPC response ID mismatch")
        if "error" in body:
            raise RpcError(method, body["error"])
        if "result" not in body:
            raise RuntimeError("RPC response has no result")
        return body["result"]

    def account(self, key):
        return self.call("getAccountInfo", str(key), {"encoding":"base64", "commitment":"confirmed"})

    def ready(self, timeout=30):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            try:
                if self.call("getHealth") == "ok": return
            except Exception as error:
                last = error
            time.sleep(.2)
        raise TimeoutError(f"RPC did not become ready: {last}")


def raw_data(account):
    data = account["data"]
    if not isinstance(data, list) or len(data) != 2 or data[1] != "base64":
        raise ValueError("Expected RPC base64 tuple, not parsed or compressed data")
    return base64.b64decode(data[0], validate=True)


def canonical_account(account):
    if account is None: return None
    return {"lamports":account["lamports"], "owner":account["owner"],
            "executable":account["executable"], "rentEpoch":account["rentEpoch"],
            "data":base64.b64encode(raw_data(account)).decode()}


def decode_mint(account):
    if account["owner"] != TOKEN_PROGRAM or account["executable"]:
        raise ValueError("Not a standard SPL Token mint")
    data = raw_data(account)
    if len(data) != 82: raise ValueError("Expected 82-byte legacy SPL mint")
    if data[45] not in (0,1): raise ValueError("Invalid SPL mint initialized flag")
    def authority(offset):
        tag = struct.unpack_from("<I", data, offset)[0]
        if tag not in (0,1): raise ValueError("Invalid COption tag")
        return str(Pubkey.from_bytes(data[offset+4:offset+36])) if tag else None
    return {"mint_authority":authority(0), "supply":struct.unpack_from("<Q",data,36)[0],
            "decimals":data[44], "initialized":bool(data[45]), "freeze_authority":authority(46)}


def decode_token(account):
    if account["owner"] != TOKEN_PROGRAM or account["executable"]:
        raise ValueError("Not a standard SPL Token account")
    data = raw_data(account)
    if len(data) != 165: raise ValueError("Expected 165-byte legacy SPL token account")
    if data[108] not in (0,1,2): raise ValueError("Invalid SPL account state")
    if any(struct.unpack_from("<I",data,offset)[0] not in (0,1) for offset in (72,109,129)):
        raise ValueError("Invalid SPL token COption tag")
    return {"mint":str(Pubkey.from_bytes(data[:32])),
            "wallet":str(Pubkey.from_bytes(data[32:64])),
            "amount":struct.unpack_from("<Q",data,64)[0], "state":data[108]}


def ata(wallet, mint):
    return str(Pubkey.find_program_address([
        bytes(Pubkey.from_string(str(wallet))), bytes(Pubkey.from_string(TOKEN_PROGRAM)),
        bytes(Pubkey.from_string(str(mint)))], Pubkey.from_string(ASSOCIATED_TOKEN_PROGRAM))[0])


def canonical_upstream(account):
    """Decode the upstream wire encoding while retaining exact account fields."""
    if account is None:return None
    data=account.get('data')
    if isinstance(data,list) and len(data)==2 and data[1]=='base64+zstd':
        import zstandard
        compressed=base64.b64decode(data[0],validate=True)
        raw=zstandard.ZstdDecompressor().decompress(compressed,max_output_size=10_485_760)
        account={**account,'data':[base64.b64encode(raw).decode(),'base64']}
    return canonical_account(account)
