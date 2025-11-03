import { toBase64 } from '@cosmjs/encoding'
import type { OfflineDirectSigner } from '@cosmjs/proto-signing'
import type { SignDoc } from '@cosmjs/proto-signing'

import type { Adr36Signer, SignResult } from './types'

export async function createKeplrSigner(chainId: string): Promise<Adr36Signer> {
    if (!window.keplr) {
        throw new Error('Keplr extension not detected')
    }
    await window.keplr.enable(chainId)
    const key = await window.keplr.getKey(chainId)
    const address = key.bech32Address
    const pubkeyBase64 = toBase64(key.pubKey)

    return {
        address,
        pubkeyBase64,
        async sign(signDoc: SignDoc): Promise<SignResult> {
            const res = await window.keplr!.signDirect(chainId, address, signDoc)
            const sig = typeof res.signature.signature === 'string' ? res.signature.signature : toBase64(res.signature.signature)
            return { signed: res.signed, signatureBase64: sig }
        },
    }
}

export async function createOfflineSignerSigner(params: {
    wallet: OfflineDirectSigner
    address?: string
}): Promise<Adr36Signer> {
    const { wallet, address } = params
    const accounts = await wallet.getAccounts()
    if (accounts.length === 0) {
        throw new Error('Wallet has no accounts')
    }
    const account = address ? accounts.find((acct) => acct.address === address) ?? accounts[0] : accounts[0]
    const resolvedAddress = account.address
    const pubkeyBase64 = toBase64(account.pubkey)

    return {
        address: resolvedAddress,
        pubkeyBase64,
        async sign(signDoc: SignDoc): Promise<SignResult> {
            const res = await wallet.signDirect(resolvedAddress, signDoc)
            const sig = typeof res.signature.signature === 'string' ? res.signature.signature : toBase64(res.signature.signature)
            return { signed: res.signed, signatureBase64: sig }
        },
    }
}

declare global {
    interface Window {
        keplr?: {
            enable: (chainId: string) => Promise<void>
            getKey: (chainId: string) => Promise<{ pubKey: Uint8Array; bech32Address: string }>
            signDirect: (
                chainId: string,
                signer: string,
                signDoc: SignDoc,
            ) => Promise<{ signed: SignDoc; signature: { signature: string | Uint8Array } }>
        }
    }
}

