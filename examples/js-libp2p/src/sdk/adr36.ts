import { fromBase64, toBase64 } from '@cosmjs/encoding'
import { makeSignDoc } from '@cosmjs/proto-signing'
import { AuthInfo, Fee, SignerInfo, TxBody } from 'cosmjs-types/cosmos/tx/v1beta1/tx'
import { ModeInfo } from 'cosmjs-types/cosmos/tx/v1beta1/tx'
import { Any } from 'cosmjs-types/google/protobuf/any'
import { SignMode } from 'cosmjs-types/cosmos/tx/signing/v1beta1/signing'
import { PubKey } from 'cosmjs-types/cosmos/crypto/secp256k1/keys'
import { Writer } from 'protobufjs/minimal'

import type { Adr36Envelope, Adr36Signer } from './types'

interface MsgArbitraryData {
    signer: string
    data: string
    app_domain: string
}

interface EnvelopeParams {
    chainId: string
    topic: string
    payload: Uint8Array
    signer: Adr36Signer
    peerId?: string
}

function encodeMsgArbitraryData(message: MsgArbitraryData): Uint8Array {
    const writer = Writer.create()
    if (message.signer) writer.uint32(10).string(message.signer)
    if (message.data) writer.uint32(18).string(message.data)
    if (message.app_domain) writer.uint32(26).string(message.app_domain)
    return writer.finish()
}

export async function createAdr36Envelope(params: EnvelopeParams): Promise<Adr36Envelope> {
    const { chainId, topic, payload, signer, peerId } = params

    let decodedPayload: unknown = {}
    const text = new TextDecoder().decode(payload)
    if (text.trim().length > 0) {
        try {
            decodedPayload = JSON.parse(text)
        } catch (err) {
            throw new Error(`Payload must be JSON-serialisable: ${String(err)}`)
        }
    }

    if (decodedPayload === null || typeof decodedPayload !== 'object' || Array.isArray(decodedPayload)) {
        throw new Error('Payload must be a JSON object')
    }

    const dataObj = {
        ...decodedPayload as Record<string, unknown>,
        peerId: peerId ?? '',
    }

    const msg: MsgArbitraryData = {
        signer: signer.address,
        data: JSON.stringify(dataObj),
        app_domain: topic,
    }

    const msgBytes = encodeMsgArbitraryData(msg)
    const body = TxBody.fromPartial({
        messages: [Any.fromPartial({ typeUrl: '/dysonprotocol.script.v1.MsgArbitraryData', value: msgBytes })],
        memo: '',
        timeoutHeight: BigInt(0),
    })
    const bodyBytes = TxBody.encode(body).finish()

    const pubkeyAny = Any.fromPartial({
        typeUrl: '/cosmos.crypto.secp256k1.PubKey',
        value: PubKey.encode(PubKey.fromPartial({ key: fromBase64(signer.pubkeyBase64) })).finish(),
    })
    const signerInfo = SignerInfo.fromPartial({
        publicKey: pubkeyAny,
        modeInfo: ModeInfo.fromPartial({ single: { mode: SignMode.SIGN_MODE_DIRECT } }),
        sequence: BigInt(0),
    })
    const authInfo = AuthInfo.fromPartial({
        signerInfos: [signerInfo],
        fee: Fee.fromPartial({ gasLimit: BigInt(0), amount: [] }),
    })
    const authInfoBytes = AuthInfo.encode(authInfo).finish()

    // ADR-36 requires empty chainId for arbitrary signatures
    const signDoc = makeSignDoc(bodyBytes, authInfoBytes, '', 0)
    const { signed, signatureBase64 } = await signer.sign(signDoc)

    const txJson = {
        body: {
            messages: [
                {
                    '@type': '/dysonprotocol.script.v1.MsgArbitraryData',
                    signer: signer.address,
                    data: msg.data,
                    app_domain: topic,
                },
            ],
            memo: '',
            timeout_height: '0',
        },
        auth_info: {
            signer_infos: [
                {
                    public_key: {
                        '@type': '/cosmos.crypto.secp256k1.PubKey',
                        key: signer.pubkeyBase64,
                    },
                    mode_info: {
                        single: { mode: 'SIGN_MODE_DIRECT' },
                    },
                    sequence: '0',
                },
            ],
            fee: {
                amount: [],
                gas_limit: '0',
            },
        },
        signatures: [signatureBase64],
    }

    if (signed?.bodyBytes && toBase64(signed.bodyBytes) !== toBase64(bodyBytes)) {
        throw new Error('Signed bodyBytes mismatch')
    }

    return {
        adr36_tx_json: JSON.stringify(txJson),
        v: 1,
    }
}

