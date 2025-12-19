# POW Coin - Difficulty-Adjusted Emission

**Target: 24 POW per day (1 POW per hour)**

## How It Works

```
Reward = EMISSION × (elapsed / TARGET) × (work / difficulty)
```

Three factors determine your reward:

1. **Time** - How long since last claim (elapsed / TARGET)
2. **Work** - How much proof-of-work you found (bits)
3. **Difficulty** - Current target that adjusts to stabilize emission

## Examples

| Elapsed | Work | Difficulty | Reward |
|---------|------|------------|--------|
| 1 hour | 20 bits | 20 | 1.0 POW |
| 1 hour | 40 bits | 20 | 2.0 POW |
| 30 min | 20 bits | 20 | 0.5 POW |
| 30 min | 10 bits | 20 | 0.25 POW |
| 2 hours | 10 bits | 20 | 1.0 POW |

## Difficulty Adjustment

After each claim, difficulty adjusts using an EMA based on observed hashrate:

```
ideal_diff = work - log2(elapsed / TARGET)
α = min(0.5, elapsed / WINDOW)
new_diff = α × ideal + (1-α) × old_diff
```

Where `WINDOW = 48 hours` is the EMA time constant. This smoothly converges toward the actual network hashrate.

## Storage

**1 slot**: `[prev_hash, last_time, difficulty]`

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
- `check(nonce, miner?)` - Check potential reward
- `info()` - Current state, difficulty, and base reward

## Key Properties

1. **More work = more reward** (linear scaling, no cap)
2. **More time = more reward** (linear scaling)
3. **Difficulty adjusts** to target 1 claim per hour
4. **First valid proof wins** - it's a race!
