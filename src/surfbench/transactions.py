"""Decode signed transaction evidence without using the agent's report."""
import base64
from solders.transaction import VersionedTransaction


def decode_encoded(value,encoding='base58'):
    if encoding=='base64':return base64.b64decode(value,validate=True)
    if encoding!='base58':raise ValueError('Unsupported transaction encoding')
    alphabet='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
    number=0
    for c in value:number=number*58+alphabet.index(c)
    return b'\0'*(len(value)-len(value.lstrip('1')))+number.to_bytes((number.bit_length()+7)//8,'big')


def transaction(pair):
    req=pair['request'];params=req.get('params',[])
    opts=params[1] if len(params)>1 and isinstance(params[1],dict) else {}
    tx=VersionedTransaction.from_bytes(decode_encoded(params[0],opts.get('encoding','base58')))
    keys=[str(k) for k in tx.message.account_keys]
    return {'signature':str(tx.signatures[0]),'valid_signatures':all(tx.verify_with_results()),
            'instructions':[{'program':keys[ix.program_id_index],'accounts':[keys[i] for i in ix.accounts],
                             'data':bytes(ix.data)} for ix in tx.message.instructions]}


def submitted_transactions(pairs):
    result=[]
    for pair in pairs:
        if pair['request'].get('method')!='sendTransaction':continue
        try:
            tx=transaction(pair)
            response=pair['response']
            tx['accepted']=response.get('result')==tx['signature']
            tx['error']=response.get('error')
            tx['confirmed']=False
            for status in pairs:
                req=status['request'];res=status['response']
                if req.get('method')!='getSignatureStatuses':continue
                signatures=req.get('params',[[]])[0]
                if tx['signature'] not in signatures:continue
                values=res.get('result',{}).get('value',[])
                index=signatures.index(tx['signature'])
                if index<len(values) and values[index]:
                    value=values[index]
                    tx['confirmed'] |= value.get('err') is None and value.get('confirmationStatus') in ('confirmed','finalized')
            result.append(tx)
        except (ValueError,IndexError,KeyError,TypeError):continue
    return result
