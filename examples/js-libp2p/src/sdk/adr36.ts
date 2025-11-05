import { fromBase64, toBase64 } from '@cosmjs/encoding'
import { makeSignDoc } from '@cosmjs/proto-signing'
import { AuthInfo, Fee, SignerInfo, TxBody } from 'cosmjs-types/cosmos/tx/v1beta1/tx'
import { ModeInfo } from 'cosmjs-types/cosmos/tx/v1beta1/tx'
import { Any } from 'cosmjs-types/google/protobuf/any'
import { SignMode } from 'cosmjs-types/cosmos/tx/signing/v1beta1/signing'
import { PubKey } from 'cosmjs-types/cosmos/crypto/secp256k1/keys'
import { Writer } from 'protobufjs/minimal'

import type { MsgArbitraryData, Adr36Signer } from './types'

interface ArbitraryDataMessage {
    signer: string
    data: string
    app_domain: string
    metadata: string
}

interface EnvelopeParams {
    chainId: string
    topic: string
    payload: Uint8Array
    signer: Adr36Signer
    peerId?: string
}

function encodeMsgArbitraryData(message: ArbitraryDataMessage): Uint8Array {
    const writer = Writer.create()
    if (message.signer) writer.uint32(10).string(message.signer)
    if (message.data) writer.uint32(18).string(message.data)
    if (message.app_domain) writer.uint32(26).string(message.app_domain)
    if (message.metadata) writer.uint32(34).string(message.metadata)
    return writer.finish()
}

export async function createAdr36Envelope(params: EnvelopeParams): Promise<MsgArbitraryData> {
    const { chainId, topic, payload, signer, peerId } = params

    // Treat payload as raw bytes, encode as base64
    const binaryString = Array.from(payload).map(byte => String.fromCharCode(byte)).join('')
    const dataStr = btoa(binaryString)

    // Create metadata JSON with peerId
    const metadataStr = JSON.stringify({ peerId: peerId ?? '' })

    const msg: ArbitraryDataMessage = {
        signer: signer.address,
        data: dataStr,
        app_domain: topic,
        metadata: metadataStr,
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
                    metadata: msg.metadata,
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
        body: txJson.body,
        auth_info: txJson.auth_info,
        signatures: txJson.signatures,
    }
}

