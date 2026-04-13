# POW Coin - Difficulty-Adjusted Emission

**Target: 24 POW per day (1 POW per hour)**

## How It Works

```
reward = EMISSION × work / (target_hashrate × PERIOD)
```

Where:
- **work** = 2^256 / hash_value (expected hashes to find this proof)
- **target_hashrate** = current difficulty in H/s, adjusted via EMA
- **PERIOD** = 3600s (1 hour)
- **EMISSION** = 1,000,000 micro-units (1 POW)

Reward is capped at 4 POW per claim.

## Examples

At target_hashrate = 100 H/s (expected_work = 360,000):

| Work | Reward |
|------|--------|
| 180,000 | 0.5 POW |
| 360,000 | 1.0 POW |
| 720,000 | 2.0 POW |
| 1,440,000 | 4.0 POW (cap) |

## Difficulty Adjustment

After each claim, target_hashrate adjusts using an EMA based on observed hashrate:

```
observed = work / elapsed
observed = min(observed, target × 4)       # cap spike protection
α = min(0.5, elapsed / WINDOW)             # WINDOW = 3600s (1 hour)
new_target = α × observed + (1-α) × target
```

This smoothly converges toward the actual network hashrate while resisting sudden spikes.

## Storage

**1 slot**: `[prev_hash, last_time, target_hashrate]`

## Deploy

```bash
# 1. Register name, set destination to script address
# 2. Edit DENOM in pow_coin.py
# 3. Deploy
dysond tx script update --code-path pow_coin.py --from alice --gas 2000000 -y
```

## Mine

```bash
# CLI miner
python miner.py <script_address> <account>

# Or use web_miner.html in browser with Keplr
```

## API

- `mine(nonce)` - Submit proof and claim reward

## Key Properties

1. **More work = more reward** (linear, capped at 4 POW)
2. **Difficulty adjusts** via EMA to maintain ~1 POW/hour emission
3. **Serial claims** - prev_hash changes on every mine(), preventing Sybil attacks
4. **Miner-bound proofs** - hash includes miner address, so proofs can't be stolen
