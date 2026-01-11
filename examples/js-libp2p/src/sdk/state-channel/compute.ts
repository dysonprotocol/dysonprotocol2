/**
 * State Channel Computation (40-11)
 *
 * Query the on-chain script via REST API to compute deterministic results.
 * All participants calling with identical inputs MUST get identical outputs.
 */

import type { ChannelConfig, ComputeResult } from './types'

/**
 * Compute next state via Dyson REST API query.
 *
 * This calls the on-chain execute_computation function in read-only mode.
 * Deterministic: same (script, state, step) → identical result.
 *
 * @param apiUrl - Dyson REST API URL (e.g., "http://localhost:1317" or "" for relative)
 * @param config - Channel configuration with script_address and computation_script
 * @param currentState - Current state object
 * @param step - Current step number
 * @returns Computation result with hash
 *
 * @throws Error if API request fails or returns invalid format
 *
 * Future optimization: Port computation to JavaScript for fully off-chain execution.
 * Requirements: byte-identical JSON serialization and hash function.
 */
export async function computeNextState(
  apiUrl: string,
  config: ChannelConfig,
  currentState: unknown,
  step: number
): Promise<ComputeResult> {
  const baseUrl = apiUrl.endsWith('/') ? apiUrl.slice(0, -1) : apiUrl
  const endpoint = `${baseUrl}/dysonprotocol/script/v1/query_script`

  const body = {
    script_address: config.script_address,
    function_name: 'execute_computation',
    kwargs: JSON.stringify({
      computation_script: config.computation_script,
      prev_state: currentState,
      step,
    }),
  }

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(
      `Computation query failed: ${response.status} ${response.statusText} - ${text}`
    )
  }

  const data = await response.json()

  // Response format: { result: { result: any, result_hash: string } }
  // The outer "result" is from the script query, inner is from execute_computation
  const scriptResult = data?.result
  if (!scriptResult) {
    throw new Error(`Invalid computation response: missing result field`)
  }

  // Parse the script result (it's JSON-stringified in the response)
  let parsed: { result: unknown; result_hash: string }
  if (typeof scriptResult === 'string') {
    parsed = JSON.parse(scriptResult)
  } else {
    parsed = scriptResult
  }

  if (typeof parsed?.result_hash !== 'string') {
    throw new Error(`Invalid computation result format: missing result_hash`)
  }

  return {
    result: parsed.result,
    result_hash: parsed.result_hash,
  }
}

/**
 * Query channel configuration from on-chain storage.
 *
 * @param apiUrl - Dyson REST API URL
 * @param scriptAddress - Address of deployed state channel script
 * @param channelId - Channel identifier
 * @returns Channel configuration
 */
export async function queryChannelConfig(
  apiUrl: string,
  scriptAddress: string,
  channelId: string
): Promise<ChannelConfig> {
  const baseUrl = apiUrl.endsWith('/') ? apiUrl.slice(0, -1) : apiUrl
  const endpoint = `${baseUrl}/dysonprotocol/script/v1/query_script`

  const body = {
    script_address: scriptAddress,
    function_name: 'query_config',
    kwargs: JSON.stringify({ channel_id: channelId }),
  }

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(
      `Query config failed: ${response.status} ${response.statusText} - ${text}`
    )
  }

  const data = await response.json()
  const scriptResult = data?.result

  let parsed: { config: ChannelConfig }
  if (typeof scriptResult === 'string') {
    parsed = JSON.parse(scriptResult)
  } else {
    parsed = scriptResult
  }

  if (!parsed?.config) {
    throw new Error(`Channel not found: ${channelId}`)
  }

  return parsed.config
}

/**
 * Query current channel state from on-chain storage.
 *
 * @param apiUrl - Dyson REST API URL
 * @param scriptAddress - Address of deployed state channel script
 * @param channelId - Channel identifier
 * @returns Current step and state data
 */
export async function queryChannelState(
  apiUrl: string,
  scriptAddress: string,
  channelId: string
): Promise<{ step: number; state_data: unknown; state_hash: string }> {
  const baseUrl = apiUrl.endsWith('/') ? apiUrl.slice(0, -1) : apiUrl
  const endpoint = `${baseUrl}/dysonprotocol/script/v1/query_script`

  const body = {
    script_address: scriptAddress,
    function_name: 'query_state',
    kwargs: JSON.stringify({ channel_id: channelId }),
  }

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(
      `Query state failed: ${response.status} ${response.statusText} - ${text}`
    )
  }

  const data = await response.json()
  const scriptResult = data?.result

  let parsed: { state: { step: number; state_data: unknown; state_hash: string } }
  if (typeof scriptResult === 'string') {
    parsed = JSON.parse(scriptResult)
  } else {
    parsed = scriptResult
  }

  if (!parsed?.state) {
    throw new Error(`Channel state not found: ${channelId}`)
  }

  return parsed.state
}

