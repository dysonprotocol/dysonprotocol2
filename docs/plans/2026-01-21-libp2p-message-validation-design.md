# LibP2P Message Validation Design

## Overview

Restore ADR-36 message validation for libp2p GossipSub messages. All non-discovery topic messages must be validated at the mesh level before propagation.

## Requirements

1. **app_domain must match topic** - The signed `app_domain` field must exactly match the GossipSub topic
2. **peerId in metadata** - The libp2p peer ID must match `metadata.peerId` in the signed message
3. **Chain ID prefix** - The topic must be prefixed with the chain ID

## Message Envelope Structure

```json
{
  "body": {
    "messages": [{
      "@type": "/dysonprotocol.script.v1.MsgArbitraryData",
      "signer": "dys1abc...",
      "data": "{\"your\":\"payload\"}",
      "app_domain": "chainid/v1/topic/path",
      "metadata": "{\"peerId\":\"12D3KooW...\"}"
    }],
    "memo": "",
    "timeout_height": "0"
  },
  "auth_info": {
    "signer_infos": [...],
    "fee": {...}
  },
  "signatures": ["base64..."]
}
```

## Files to Create

### 1. `dysond/server/dwapp/adr36_verifier.go`

Verifies ADR-36 signatures via the VerifyTx query.

```go
package dwapp

import (
    "context"
    "encoding/json"
    "fmt"

    "github.com/cosmos/cosmos-sdk/client"
    scriptv1 "dysonprotocol.com/x/script/types"
)

// VerifyADR36TxJSON calls the VerifyTx query to validate a DIRECT-signed
// MsgArbitraryData transaction. Returns signer, app_domain, data, and metadata.
func VerifyADR36TxJSON(ctx context.Context, clientCtx client.Context, txJSON string) (signer, appDomain, data, metadata string, err error)
```

**Implementation:**
- Call `/dysonprotocol.script.v1.Query/VerifyTx` with the tx JSON
- Parse the response to extract the verified signer
- Parse `body.messages[0]` to extract `app_domain`, `data`, `metadata`
- Verify message type is `/dysonprotocol.script.v1.MsgArbitraryData`
- Cross-check verified signer matches message signer

### 2. `dysond/server/dwapp/p2p_validate_payload.go`

Orchestrates validation for GossipSub payloads.

```go
package dwapp

import (
    "context"
    "encoding/json"
    "fmt"
    "strings"

    "github.com/cosmos/cosmos-sdk/client"
    "github.com/cosmos/cosmos-sdk/telemetry"
)

const maxEnvelopeSize = 64 * 1024

// ValidatePubSubPayload validates a GossipSub message payload.
// Returns the verified signer address and the data payload on success.
func (s *P2PService) ValidatePubSubPayload(
    ctx context.Context,
    clientCtx client.Context,
    topic string,
    payload []byte,
    senderPeerID string,
) (signer string, data string, err error)
```

**Validation steps:**
1. Check envelope size <= 64KB
2. Parse envelope JSON: `{ body, auth_info, signatures }`
3. Reconstruct tx JSON for verification
4. Call `VerifyADR36TxJSON` to verify signature
5. Verify `app_domain` == `topic`
6. Parse `metadata` JSON, extract `peerId`
7. Verify `metadata.peerId` == `senderPeerID`
8. Emit telemetry counters for accept/reject

### 3. Modify `dysond/server/dwapp/p2p_control_libp2p.go`

Register topic validators when subscribing to non-discovery topics.

**Changes to `SubscribeTopic`:**

```go
func (s *P2PService) SubscribeTopic(ctx context.Context, clientCtx client.Context, topic string) error {
    // ... existing pubsub/chainID checks ...

    // Register validator for non-discovery topics
    if !strings.HasSuffix(topic, "/discovery") {
        err := s.pubsub.RegisterTopicValidator(topic,
            func(ctx context.Context, pid peer.ID, msg *pubsub.Message) pubsub.ValidationResult {
                signer, _, err := s.ValidatePubSubPayload(ctx, clientCtx, topic, msg.Data, pid.String())
                if err != nil {
                    s.logger.Debug("validator rejected message",
                        "topic", topic,
                        "peer", pid.String(),
                        "error", err,
                    )
                    telemetry.IncrCounter(1, "libp2p", "validator", "reject")
                    return pubsub.ValidationReject
                }
                s.logger.Debug("validator accepted message",
                    "topic", topic,
                    "peer", pid.String(),
                    "signer", signer,
                )
                telemetry.IncrCounter(1, "libp2p", "validator", "accept")
                return pubsub.ValidationAccept
            },
        )
        if err != nil {
            return fmt.Errorf("register topic validator: %w", err)
        }
    }

    // ... rest of existing subscription logic ...
}
```

**Changes to `UnsubscribeTopic`:**

Add call to unregister the validator:
```go
if s.pubsub != nil {
    _ = s.pubsub.UnregisterTopicValidator(topic)
}
```

## Validation Flow Diagram

```
GossipSub Message Received
          |
          v
+-------------------+
| Topic Validator   |
| (mesh level)      |
+-------------------+
          |
          v
+-------------------+
| Size Check        |
| <= 64KB           |
+-------------------+
          |
          v
+-------------------+
| Parse Envelope    |
| {body,auth_info,  |
|  signatures}      |
+-------------------+
          |
          v
+-------------------+
| VerifyTx Query    |
| (ADR-36 sig)      |
+-------------------+
          |
          v
+-------------------+
| app_domain ==     |
| topic?            |
+-------------------+
          |
          v
+-------------------+
| metadata.peerId   |
| == sender?        |
+-------------------+
          |
          v
    ValidationAccept
    (propagate msg)
```

## Error Handling

- On validation failure: return `pubsub.ValidationReject`
- No peer blacklisting - simply reject invalid messages
- Log validation failures at DEBUG level with reason
- Emit telemetry counters: `libp2p.validator.accept`, `libp2p.validator.reject`

## Chain ID Prefix Validation

Already exists in `SubscribeTopic` (lines 93-96):
```go
chainID := strings.TrimSpace(clientCtx.ChainID)
if chainID != "" && !strings.HasPrefix(topic, chainID) && !strings.HasPrefix(topic, "/"+chainID) {
    return fmt.Errorf("topic must begin with chainID %q", chainID)
}
```

This runs at subscription time, not per-message. The app_domain check implicitly enforces this since app_domain must match the topic.

## Implementation Checklist

- [ ] Create `dysond/server/dwapp/adr36_verifier.go`
  - [ ] Implement `VerifyADR36TxJSON` function
  - [ ] Add unit tests

- [ ] Create `dysond/server/dwapp/p2p_validate_payload.go`
  - [ ] Implement `ValidatePubSubPayload` method on P2PService
  - [ ] Add telemetry counters
  - [ ] Add unit tests

- [ ] Modify `dysond/server/dwapp/p2p_control_libp2p.go`
  - [ ] Add validator registration in `SubscribeTopic`
  - [ ] Add validator unregistration in `UnsubscribeTopic`
  - [ ] Add necessary imports

- [ ] Test end-to-end with js-libp2p example
