package keeper

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"sort"

	cosmossdkerrors "cosmossdk.io/errors"
	sdk "github.com/cosmos/cosmos-sdk/types"

	hosttypes "github.com/cosmos/ibc-go/v10/modules/apps/27-interchain-accounts/host/types"
	icatypes "github.com/cosmos/ibc-go/v10/modules/apps/27-interchain-accounts/types"
	callbacktypes "github.com/cosmos/ibc-go/v10/modules/apps/callbacks/types"
	clienttypes "github.com/cosmos/ibc-go/v10/modules/core/02-client/types"
	channeltypes "github.com/cosmos/ibc-go/v10/modules/core/04-channel/types"
	ibcexported "github.com/cosmos/ibc-go/v10/modules/core/exported"

	"dysonprotocol.com/x/script/types"
	scripttypes "dysonprotocol.com/x/script/types"
)

// marshalDeterministic encodes JSON with lexicographically-sorted object keys for deterministic bytes.
func marshalDeterministic(v any) ([]byte, error) {
	switch vv := v.(type) {
	case map[string]any:
		keys := make([]string, 0, len(vv))
		for k := range vv {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		buf := bytes.NewBuffer(make([]byte, 0, 256))
		buf.WriteByte('{')
		for i, k := range keys {
			kb, _ := json.Marshal(k)
			buf.Write(kb)
			buf.WriteByte(':')
			vb, err := marshalDeterministic(vv[k])
			if err != nil {
				return nil, err
			}
			buf.Write(vb)
			if i < len(keys)-1 {
				buf.WriteByte(',')
			}
		}
		buf.WriteByte('}')
		return buf.Bytes(), nil
	case []any:
		buf := bytes.NewBuffer(make([]byte, 0, 256))
		buf.WriteByte('[')
		for i, el := range vv {
			eb, err := marshalDeterministic(el)
			if err != nil {
				return nil, err
			}
			buf.Write(eb)
			if i < len(vv)-1 {
				buf.WriteByte(',')
			}
		}
		buf.WriteByte(']')
		return buf.Bytes(), nil
	default:
		return json.Marshal(v)
	}
}

// Verify Keeper implements ContractKeeper at compile time
var _ callbacktypes.ContractKeeper = (*Keeper)(nil)

// IBCSendPacketCallback is called in the source chain when a PacketSend is executed
// Currently, we only log the information and don't store any data
func (k *Keeper) IBCSendPacketCallback(
	ctx sdk.Context,
	sourcePort string,
	sourceChannel string,
	timeoutHeight clienttypes.Height,
	timeoutTimestamp uint64,
	packetData []byte, // Raw packet data being sent
	contractAddress string, // Source chain contract address
	packetSenderAddress string, // Initiator of the packet send on the source chain
	version string, // Negotiated app version
) error {
	logger := k.Logger(ctx).With("IBCPacketCallback", "IBCSendPacketCallback")

	logger.Info("IBCSendPacketCallback called",
		"sourcePort", sourcePort,
		"sourceChannel", sourceChannel,
		"timeoutHeight", timeoutHeight,
		"timeoutTimestamp", timeoutTimestamp,
		// "packetData", packetData, // Avoid logging potentially large raw data by default
		"packetData_len", len(packetData),
		"contractAddress", contractAddress,
		"packetSenderAddress", packetSenderAddress,
		"version", version,
	)

	return nil
}

// IBCOnAcknowledgementPacketCallback is called in the source chain when a packet acknowledgement is received
// Decodes and logs the packet data
func (k *Keeper) IBCOnAcknowledgementPacketCallback(
	ctx sdk.Context,
	packet channeltypes.Packet,
	acknowledgement []byte,
	relayer sdk.AccAddress,
	contractAddress string,
	packetSenderAddress string,
	version string,
) error {
	logger := k.Logger(ctx).With("IBCPacketCallback", "IBCOnAcknowledgementPacketCallback")

	// Initialize callback message execution struct early to progressively populate
	callbackMsgExec := scripttypes.MsgExec{
		ExecutorAddress: packetSenderAddress,
		ScriptAddress:   contractAddress,
	}

	// Initialize data structures to accumulate parsed data
	ackMsgsJson := []map[string]interface{}{}
	var versionJSON map[string]interface{}
	var packetData icatypes.InterchainAccountPacketData
	var ackJSON map[string]interface{}
	var memoJSON struct {
		SrcCallback struct {
			Address      string                 `json:"address"`
			FunctionName string                 `json:"function_name"`
			Kwargs       map[string]interface{} `json:"kwargs"`
			Args         []interface{}          `json:"args"`
			ExtraCode    string                 `json:"extra_code"`
		} `json:"src_callback"`
	}
	var callbackError string

	// Helper function to execute callback with current data
	executeCallback := func() error {
		// Decode packet.data recursively to get nested structure
		var decodedPacketData interface{}
		if len(packet.Data) > 0 {
			// First, try to parse packet.Data as JSON (it's usually already a JSON string)
			var outerData map[string]interface{}
			if err := json.Unmarshal(packet.Data, &outerData); err != nil {
				logger.Error("Failed to parse packet.Data as JSON", "error", err)
				// Fallback: try base64 decoding first
				if decoded, err := base64.StdEncoding.DecodeString(string(packet.Data)); err != nil {
					logger.Error("Failed to decode packet.Data as base64", "error", err)
					decodedPacketData = string(packet.Data) // fallback to original
				} else {
					// Try parsing the decoded data as JSON
					if err := json.Unmarshal(decoded, &outerData); err != nil {
						logger.Error("Failed to parse base64-decoded packet.Data as JSON", "error", err)
						decodedPacketData = string(decoded) // fallback to decoded string
					} else {
						// Continue with nested decoding below
					}
				}
			}

			// If we successfully got the outer JSON structure, decode nested data
			if outerData != nil {
				// Check if there's a nested "data" field that's base64 encoded
				if dataField, ok := outerData["data"].(string); ok && dataField != "" {
					// Try to decode the nested data field
					if nestedDecoded, err := base64.StdEncoding.DecodeString(dataField); err != nil {
						logger.Error("Failed to decode nested data field as base64", "error", err)
						// Keep the original structure
						decodedPacketData = outerData
					} else {
						// Try to parse the nested data as JSON
						var nestedData interface{}
						if err := json.Unmarshal(nestedDecoded, &nestedData); err != nil {
							logger.Error("Failed to parse nested data as JSON", "error", err)
							// Replace data field with decoded string
							outerData["data"] = string(nestedDecoded)
							decodedPacketData = outerData
						} else {
							// Replace data field with fully decoded nested structure
							outerData["data"] = nestedData
							decodedPacketData = outerData
							logger.Info("Successfully decoded packet.data recursively", "nested_data_type", fmt.Sprintf("%T", nestedData))
						}
					}
				} else {
					// No nested data field or it's not a string, use the outer structure
					decodedPacketData = outerData
				}

				// Also decode the memo field if it's a JSON string
				if memoField, ok := outerData["memo"].(string); ok && memoField != "" {
					var memoData interface{}
					if err := json.Unmarshal([]byte(memoField), &memoData); err != nil {
						logger.Error("Failed to parse memo field as JSON", "error", err)
						// Keep memo as string if parsing fails
					} else {
						// Replace memo field with decoded JSON structure
						outerData["memo"] = memoData
						logger.Info("Successfully decoded memo field as JSON", "memo_type", fmt.Sprintf("%T", memoData))
					}
				}
			}
		} else {
			decodedPacketData = nil
		}

		// Build callback data with whatever we have so far
		type CallbackData struct {
			AckMsgsJson         []map[string]interface{} `json:"ack_msgs_json"`
			Relayer             string                   `json:"relayer"`
			ContractAddress     string                   `json:"contract_address"`
			PacketSenderAddress string                   `json:"packet_sender_address"`
			Version             map[string]interface{}   `json:"version"`
			Packet              map[string]interface{}   `json:"packet"`
			MemoJson            interface{}              `json:"memo_json"`
			Error               string                   `json:"error"`
		}
		// Convert packet to map with decoded data
		packetMap := map[string]interface{}{
			"sequence":            packet.Sequence,
			"source_port":         packet.SourcePort,
			"source_channel":      packet.SourceChannel,
			"destination_port":    packet.DestinationPort,
			"destination_channel": packet.DestinationChannel,
			"data":                decodedPacketData, // Use fully decoded data instead of raw bytes
			"timeout_height": map[string]interface{}{
				"revision_number": packet.TimeoutHeight.RevisionNumber,
				"revision_height": packet.TimeoutHeight.RevisionHeight,
			},
			"timeout_timestamp": packet.TimeoutTimestamp,
		}

		// Extract packet messages for query processing
		var packetMessages []interface{}
		if decodedPacketData != nil {
			if packetDataMap, ok := decodedPacketData.(map[string]interface{}); ok {
				if dataField, ok := packetDataMap["data"].(map[string]interface{}); ok {
					if messages, ok := dataField["messages"].([]interface{}); ok {
						packetMessages = messages
					}
				}
			}
		}

		// Process and decode query requests in packet messages
		enrichedPacketMessages := k.ProcessPacketMessages(packetMessages)

		// Update the decoded packet data with enriched messages
		if decodedPacketData != nil {
			if packetDataMap, ok := decodedPacketData.(map[string]interface{}); ok {
				if dataField, ok := packetDataMap["data"].(map[string]interface{}); ok {
					dataField["messages"] = enrichedPacketMessages
				}
			}
		}

		// Process and decode query responses
		enrichedAckMsgsJson := k.ProcessQueryResponses(ackMsgsJson, enrichedPacketMessages)

		callbackData := CallbackData{
			AckMsgsJson:         enrichedAckMsgsJson,
			Relayer:             relayer.String(),
			ContractAddress:     contractAddress,
			PacketSenderAddress: packetSenderAddress,
			Version:             versionJSON,
			Packet:              packetMap,
			MemoJson:            memoJSON,
			Error:               callbackError,
		}

		// Combine src_callback.kwargs with beta_ibc_callback_data_v1
		finalKwargsMap := make(map[string]interface{})
		if memoJSON.SrcCallback.Kwargs != nil {
			for k, v := range memoJSON.SrcCallback.Kwargs {
				finalKwargsMap[k] = v
			}
		}
		finalKwargsMap["beta_ibc_callback_data_v1"] = callbackData

		// Marshal the combined kwargs
		finalKwargsJson, err := marshalDeterministic(finalKwargsMap)
		if err != nil {
			logger.Error("Failed to MarshalJSON final callback kwargs", "error", err)
			return cosmossdkerrors.Wrap(err, "failed to marshal combined callback kwargs")
		}
		logger.Info("Constructed final callback kwargs", "kwargs", string(finalKwargsJson))
		callbackMsgExec.Kwargs = string(finalKwargsJson)

		// Call the main k.ExecScript method with recovery to log panics
		logger.Info("Calling k.ExecScript for src_callback", "executor", callbackMsgExec.ExecutorAddress, "script", callbackMsgExec.ScriptAddress, "args_len", len(callbackMsgExec.Args), "attached_msgs_count", len(callbackMsgExec.AttachedMessages))

		var execResp *types.MsgExecResponse
		var execErr error

		// Use a function with defer to log panics before re-panicking
		func() {
			defer func() {
				if r := recover(); r != nil {
					logger.Error("PANIC occurred during ExecScript callback execution",
						"panic", r,
						"panic_type", fmt.Sprintf("%T", r),
						"panic_description", fmt.Sprintf("%v", r),
						"executor", callbackMsgExec.ExecutorAddress,
						"script", callbackMsgExec.ScriptAddress,
						"function", callbackMsgExec.FunctionName,
						"args", callbackMsgExec.Args,
						"kwargs_len", len(callbackMsgExec.Kwargs))
					// Re-panic to let the normal panic flow continue
					panic(r)
				}
			}()

			execResp, execErr = k.ExecScript(ctx, &callbackMsgExec)
		}()

		if execErr != nil {
			logger.Error("Error executing callback script via k.ExecScript",
				"error", execErr,
				"error_type", fmt.Sprintf("%T", execErr),
				"error_description", execErr.Error(),
				"executor", callbackMsgExec.ExecutorAddress,
				"script", callbackMsgExec.ScriptAddress,
				"function", callbackMsgExec.FunctionName,
				"args", callbackMsgExec.Args,
				"kwargs_len", len(callbackMsgExec.Kwargs))
			return cosmossdkerrors.Wrap(execErr, "error executing callback script via k.ExecScript")
		}
		logger.Info("Successfully executed callback script via k.ExecScript", "result", execResp.Result)
		return nil
	}

	// Log the basic info
	logger.Info("IBCOnAcknowledgementPacketCallback called",
		"packet", packet,
		"acknowledgement", string(acknowledgement),
		"relayer", relayer,
		"contractAddress", contractAddress,
		"packetSenderAddress", packetSenderAddress,
		"version", version,
	)

	// Parse version JSON
	var encoding string
	if err := json.Unmarshal([]byte(version), &versionJSON); err != nil {
		logger.Error("Failed to unmarshal version as JSON", "error", err)
		if callbackError == "" {
			callbackError = fmt.Sprintf("failed to unmarshal version as JSON: %v", err)
		} else {
			callbackError = fmt.Sprintf("%s; failed to unmarshal version as JSON: %v", callbackError, err)
		}
		// Continue with default encoding assumption
		encoding = icatypes.EncodingProtobuf
	} else {
		logger.Info("Parsed version as JSON", "data", fmt.Sprintf("%+v", versionJSON))

		// Extract encoding from version
		encodingField, ok := versionJSON["encoding"]
		if !ok {
			err := errors.New("version JSON does not contain 'encoding' field")
			logger.Error(err.Error())
			if callbackError == "" {
				callbackError = err.Error()
			} else {
				callbackError = fmt.Sprintf("%s; %s", callbackError, err.Error())
			}
			// Continue with default encoding assumption
			encoding = icatypes.EncodingProtobuf
		} else {
			encodingStr, ok := encodingField.(string)
			if !ok {
				err := errors.New("'encoding' field in version JSON is not a string")
				logger.Error(err.Error())
				if callbackError == "" {
					callbackError = err.Error()
				} else {
					callbackError = fmt.Sprintf("%s; %s", callbackError, err.Error())
				}
				// Continue with default encoding assumption
				encoding = icatypes.EncodingProtobuf
			} else {
				encoding = encodingStr
			}
		}
	}

	// Parse packet data based on encoding
	if encoding == icatypes.EncodingProto3JSON {
		logger.Info("Encoding is Proto3JSON", "encoding", encoding)
		err := packetData.UnmarshalJSON(packet.Data)
		if err != nil {
			logger.Error("Failed to UnmarshalJSON packet data as InterchainAccountPacketData", "error", err)
			if callbackError == "" {
				callbackError = fmt.Sprintf("failed to UnmarshalJSON packet data: %v", err)
			} else {
				callbackError = fmt.Sprintf("%s; failed to UnmarshalJSON packet data: %v", callbackError, err)
			}
			// Continue processing with empty packetData
		} else {
			logger.Info("Parsed packet data as InterchainAccountPacketData", "data", fmt.Sprintf("%v", packetData))
		}
	} else if encoding == icatypes.EncodingProtobuf {
		logger.Info("Encoding is Protobuf", "encoding", encoding)
		err := packetData.Unmarshal(packet.Data)
		if err != nil {
			logger.Error("Failed to Unmarshal packet data as InterchainAccountPacketData", "error", err)
			if callbackError == "" {
				callbackError = fmt.Sprintf("failed to Unmarshal packet data: %v", err)
			} else {
				callbackError = fmt.Sprintf("%s; failed to Unmarshal packet data: %v", callbackError, err)
			}
			// Continue processing with empty packetData
		} else {
			logger.Info("Parsed packet data as InterchainAccountPacketData", "data", fmt.Sprintf("%+v", packetData))
		}
	} else {
		logger.Error("Unsupported encoding", "encoding", encoding)
		if callbackError == "" {
			callbackError = fmt.Sprintf("unsupported encoding: %s", encoding)
		} else {
			callbackError = fmt.Sprintf("%s; unsupported encoding: %s", callbackError, encoding)
		}
		// Continue processing with empty packetData and protobuf encoding assumption
		encoding = icatypes.EncodingProtobuf
	}

	// Parse memo to get callback information early
	if err := json.Unmarshal([]byte(packetData.Memo), &memoJSON); err != nil {
		logger.Error("Failed to parse memo as JSON", "error", err, "memo", packetData.Memo)
		if callbackError == "" {
			callbackError = fmt.Sprintf("failed to parse memo as JSON: %v", err)
		} else {
			callbackError = fmt.Sprintf("%s; failed to parse memo as JSON: %v", callbackError, err)
		}
		// Continue processing even if memo parsing fails
	} else {
		logger.Info("Parsed memo as JSON", "memo", fmt.Sprintf("%+v", memoJSON))

		// Set callback script information
		srcCallback := memoJSON.SrcCallback
		logger.Info("Found src_callback in memo", "src_callback", fmt.Sprintf("%+v", srcCallback))

		callbackMsgExec.FunctionName = srcCallback.FunctionName
		callbackMsgExec.ExtraCode = srcCallback.ExtraCode

		if srcCallback.Address != "" {
			logger.Info("Found src_callback address in memo (using contractAddress instead)", "memo_address", srcCallback.Address, "contract_address", contractAddress)
		}

		// Marshal callback args
		if srcCallbackArgsJson, err := marshalDeterministic(any(srcCallback.Args)); err != nil {
			logger.Error("Failed to MarshalJSON srcCallback.Args", "error", err)
			if callbackError == "" {
				callbackError = fmt.Sprintf("failed to marshal callback args: %v", err)
			} else {
				callbackError = fmt.Sprintf("%s; failed to marshal callback args: %v", callbackError, err)
			}
		} else {
			logger.Info("Parsed srcCallback.Args as JSON", "data", string(srcCallbackArgsJson))
			callbackMsgExec.Args = string(srcCallbackArgsJson)
		}
	}

	// Parse packet messages
	packetMsgs, err := icatypes.DeserializeCosmosTx(k.cdc, packetData.Data, encoding)
	if err != nil {
		logger.Error("Failed to DeserializeCosmosTx packetData.Data", "error", err,
			"packetData.Data", packetData.Data,
			"encoding", encoding,
		)
		if callbackError == "" {
			callbackError = fmt.Sprintf("failed to deserialize cosmos tx: %v", err)
		} else {
			callbackError = fmt.Sprintf("%s; failed to deserialize cosmos tx: %v", callbackError, err)
		}
		// Continue processing with empty packetMsgs
	} else {
		logger.Info("Parsed packetMsgs", "packetMsgs_count", len(packetMsgs))
		for i, msg := range packetMsgs {
			jsonMsg, err := k.cdc.MarshalInterfaceJSON(msg)
			if err != nil {
				logger.Error(fmt.Sprintf("Failed to MarshalJSON msg %d", i), "error", err)
				if callbackError == "" {
					callbackError = fmt.Sprintf("failed to marshal msg %d: %v", i, err)
				} else {
					callbackError = fmt.Sprintf("%s; failed to marshal msg %d: %v", callbackError, i, err)
				}
				continue // Skip this message and continue with others
			}
			logger.Info(fmt.Sprintf("Parsed packetMsgs message %d as JSON", i), "data", string(jsonMsg))
			var msgJson map[string]interface{}
			if err := json.Unmarshal(jsonMsg, &msgJson); err != nil {
				logger.Error(fmt.Sprintf("Failed to UnmarshalJSON msg %d", i), "error", err)
				if callbackError == "" {
					callbackError = fmt.Sprintf("failed to unmarshal msg %d: %v", i, err)
				} else {
					callbackError = fmt.Sprintf("%s; failed to unmarshal msg %d: %v", callbackError, i, err)
				}
				continue // Skip this message and continue with others
			}
		}
	}

	// Parse acknowledgement as JSON
	if err := json.Unmarshal(acknowledgement, &ackJSON); err != nil {
		logger.Error("Failed to parse acknowledgement as JSON for callback check", "error", err, "acknowledgement", string(acknowledgement))
		if callbackError == "" {
			callbackError = fmt.Sprintf("failed to parse acknowledgement as JSON: %v", err)
		} else {
			callbackError = fmt.Sprintf("%s; failed to parse acknowledgement as JSON: %v", callbackError, err)
		}
		// Continue processing with empty ackJSON
	} else {
		logger.Info("Parsed acknowledgement as JSON", "data", fmt.Sprintf("%+v", ackJSON))
	}

	// Process acknowledgement result if available
	if resultField, ok := ackJSON["result"].(string); ok {
		logger.Info("Acknowledgement result", "result", resultField)

		// Try to decode result as base64
		resultDecoded, err := base64.StdEncoding.DecodeString(resultField)
		if err != nil {
			logger.Error("Failed to decode acknowledgement result as base64", "error", err, "result", resultField)
			if callbackError == "" {
				callbackError = fmt.Sprintf("failed to decode acknowledgement result as base64: %v", err)
			} else {
				callbackError = fmt.Sprintf("%s; failed to decode acknowledgement result as base64: %v", callbackError, err)
			}
		} else {
			logger.Info("Decoded acknowledgement result (base64)", "result_decoded_len", len(resultDecoded))
			// Parse query response
			var queryResponse hosttypes.MsgModuleQuerySafeResponse
			if err := k.cdc.Unmarshal(resultDecoded, &queryResponse); err != nil {
				logger.Error("Failed to unmarshal resultDecoded into MsgModuleQuerySafeResponse", "error", err)
				if callbackError == "" {
					callbackError = fmt.Sprintf("failed to unmarshal query response: %v", err)
				} else {
					callbackError = fmt.Sprintf("%s; failed to unmarshal query response: %v", callbackError, err)
				}
			} else {
				logger.Info("Successfully unmarshalled into MsgModuleQuerySafeResponse", "responses_count", len(queryResponse.Responses))

				// Process query response messages
				for i, responseBytes := range queryResponse.Responses {
					var unpackedMsg sdk.Msg
					if err := k.cdc.UnmarshalInterface(responseBytes, &unpackedMsg); err != nil {
						logger.Error(fmt.Sprintf("Failed to unmarshal response %d into sdk.Msg", i), "error", err)
						if callbackError == "" {
							callbackError = fmt.Sprintf("failed to unmarshal response %d: %v", i, err)
						} else {
							callbackError = fmt.Sprintf("%s; failed to unmarshal response %d: %v", callbackError, i, err)
						}
						continue // Skip this response and continue with others
					}

					logger.Info(fmt.Sprintf("Successfully unmarshalled response %d as sdk.Msg msg: %+v", i, unpackedMsg))
					jsonMsg, err := k.cdc.MarshalInterfaceJSON(unpackedMsg)
					if err != nil {
						logger.Error("Failed to MarshalJSON msg", "error", err)
						if callbackError == "" {
							callbackError = fmt.Sprintf("failed to marshal response msg %d: %v", i, err)
						} else {
							callbackError = fmt.Sprintf("%s; failed to marshal response msg %d: %v", callbackError, i, err)
						}
						continue // Skip this response and continue with others
					}
					logger.Info("Parsed response message", "data", string(jsonMsg))
					var msgJson map[string]interface{}
					if err := json.Unmarshal(jsonMsg, &msgJson); err != nil {
						logger.Error("Failed to UnmarshalJSON msg", "error", err)
						if callbackError == "" {
							callbackError = fmt.Sprintf("failed to unmarshal response msg %d: %v", i, err)
						} else {
							callbackError = fmt.Sprintf("%s; failed to unmarshal response msg %d: %v", callbackError, i, err)
						}
						continue // Skip this response and continue with others
					}
					ackMsgsJson = append(ackMsgsJson, msgJson)
				}
			}
		}
	} else {
		logger.Error("Acknowledgement result is not a string", "result", ackJSON["result"])
	}

	// Extract error from acknowledgement
	if errorField, ok := ackJSON["error"].(string); ok && errorField != "" {
		logger.Info("Acknowledgement error", "error", errorField)
		if callbackError == "" {
			callbackError = errorField
		} else {
			callbackError = fmt.Sprintf("%s; ack_error: %s", callbackError, errorField)
		}
	}

	// Execute callback if we have a contract address
	if contractAddress != "" {
		return executeCallback()
	}

	// If no contract address, just log and return success
	logger.Info("No contract address found, processing complete")
	return nil
}

// IBCOnTimeoutPacketCallback is called when a packet times out
// Currently, we only log the information and don't store any data
func (k *Keeper) IBCOnTimeoutPacketCallback(
	ctx sdk.Context,
	packet channeltypes.Packet,
	relayer sdk.AccAddress,
	contractAddress string,
	packetSenderAddress string,
	version string,
) error {
	logger := k.Logger(ctx).With("IBCPacketCallback", "IBCOnTimeoutPacketCallback")

	// Log the basic info
	logger.Info("IBCOnTimeoutPacketCallback called",
		"packet", packet,
		"relayer", relayer,
		"contractAddress", contractAddress,
		"packetSenderAddress", packetSenderAddress,
		"version", version,
	)

	return nil
}

// IBCReceivePacketCallback is called in the destination chain when a packet acknowledgement is written
// Currently, we only log the information and don't store any data
func (k *Keeper) IBCReceivePacketCallback(
	ctx sdk.Context,
	packet ibcexported.PacketI,
	ack ibcexported.Acknowledgement,
	contractAddress string, // Destination chain contract address that is a module account or normal account
	version string, // Negotiated app version for the channel
) error {
	logger := k.Logger(ctx).With("IBCPacketCallback", "IBCReceivePacketCallback")

	logger.Info("IBCReceivePacketCallback called",
		"packet_source_port", packet.GetSourcePort(),
		"packet_source_channel", packet.GetSourceChannel(),
		"packet_dest_port", packet.GetDestPort(),
		"packet_dest_channel", packet.GetDestChannel(),
		"packet_sequence", packet.GetSequence(),
		"ack_len", len(ack.Acknowledgement()),
		"contractAddress", contractAddress,
		"version", version,
	)

	return nil
}
