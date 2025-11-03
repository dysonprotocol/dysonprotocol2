package dwapp

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"time"

	"github.com/cosmos/cosmos-sdk/client"
	"github.com/cosmos/cosmos-sdk/telemetry"
	pubsub "github.com/libp2p/go-libp2p-pubsub"
	peer "github.com/libp2p/go-libp2p/core/peer"
	protocol "github.com/libp2p/go-libp2p/core/protocol"
)

const (
	topicIdleTTL = 10 * time.Minute
	topicMax     = 512
)

type topicState struct {
	topic *pubsub.Topic
	sub   *pubsub.Subscription
	timer *time.Timer
}

var (
	ps            *pubsub.PubSub
	topics        = map[string]*topicState{}
	topicsMu      sync.Mutex
	peerRejects   = make(map[peer.ID]int)
	peerRejectsMu sync.Mutex
)

func ensurePubSub(ctx context.Context, clientCtx client.Context) error {
	if ps != nil {
		fmt.Printf("[DWApp] GossipSub already initialized\n")
		return nil
	}
	if embeddedHost == nil {
		panic("[DWApp] FATAL: embeddedHost is nil when initializing pubsub")
	}
	var err error
	// Install a raw tracer to auto-join topics when peers subscribe
	tracer := &autoJoinTracer{clientCtx: clientCtx}
	fmt.Printf("[DWApp] Creating GossipSub with raw tracer (host=%s)...\n", embeddedHost.ID().String())
	// Use context.Background() not request ctx so GossipSub stays alive
	ps, err = pubsub.NewGossipSub(context.Background(), embeddedHost, pubsub.WithRawTracer(tracer))
	if err != nil {
		panic(fmt.Errorf("[DWApp] FATAL: failed to create GossipSub: %w", err))
	}
	fmt.Printf("[DWApp] GossipSub initialized successfully\n")
	return nil
}

// P2PSubscribeTopic subscribes the embedded host to a topic and installs a validator
// that enforces ADR-36 checks via ValidatePubSubPayload.
func P2PSubscribeTopic(ctx context.Context, clientCtx client.Context, topic string) error {
	fmt.Printf("[DWApp] P2PSubscribeTopic called: topic=%s\n", topic)
	if err := ensurePubSub(ctx, clientCtx); err != nil {
		fmt.Printf("[DWApp] P2PSubscribeTopic: ensurePubSub failed: %v\n", err)
		return err
	}
	fmt.Printf("[DWApp] P2PSubscribeTopic: ensurePubSub succeeded, registering validator...\n")
	// Install validator once per topic (skip for discovery topic which uses pubsub-peer-discovery format)
	if !strings.HasSuffix(topic, "/discovery") {
		if err := ps.RegisterTopicValidator(topic, func(ctx context.Context, p peer.ID, m *pubsub.Message) pubsub.ValidationResult {
			if _, _, err := ValidatePubSubPayload(ctx, clientCtx, topic, m.Data); err != nil {
				fmt.Printf("[DWApp] validator reject: topic=%s peer=%s err=%v\n", topic, p.String(), err)
				telemetry.IncrCounter(1, "libp2p", "validator", "reject")
				recordPeerFailure(p)
				return pubsub.ValidationReject
			}
			fmt.Printf("[DWApp] validator accept: topic=%s peer=%s\n", topic, p.String())
			telemetry.IncrCounter(1, "libp2p", "validator", "accept")
			resetPeerFailures(p)
			return pubsub.ValidationAccept
		}); err != nil {
			fmt.Printf("[DWApp] RegisterTopicValidator failed: topic=%s err=%v\n", topic, err)
			return err
		}
	} else {
		fmt.Printf("[DWApp] P2PSubscribeTopic: skipping validator for discovery topic\n")
	}
	fmt.Printf("[DWApp] P2PSubscribeTopic: validator registered, checking if already subscribed...\n")
	topicsMu.Lock()
	fmt.Printf("[DWApp] P2PSubscribeTopic: acquired topicsMu lock\n")
	if st, ok := topics[topic]; ok {
		fmt.Printf("[DWApp] P2PSubscribeTopic: topic already exists in map\n")
		if st.timer != nil {
			st.timer.Stop()
			st.timer = nil
		}
		topicsMu.Unlock()
		fmt.Printf("[DWApp] subscribe: already tracking topic=%s\n", topic)
		return nil
	}
	if len(topics) >= topicMax {
		topicsMu.Unlock()
		fmt.Printf("[DWApp] subscribe: topic cap reached (cap=%d)\n", topicMax)
		return nil
	}
	fmt.Printf("[DWApp] P2PSubscribeTopic: releasing lock before ps.Join\n")
	topicsMu.Unlock()

	// Join the topic first (announces to peers and sets up mesh)
	fmt.Printf("[DWApp] P2PSubscribeTopic: calling ps.Join(%s)...\n", topic)
	t, err := ps.Join(topic)
	if err != nil {
		fmt.Printf("[DWApp] join failed: topic=%s err=%v\n", topic, err)
		return err
	}
	fmt.Printf("[DWApp] joined topic: %s\n", topic)

	// Then subscribe to receive messages
	fmt.Printf("[DWApp] P2PSubscribeTopic: calling topic.Subscribe()...\n")
	s, err := t.Subscribe()
	if err != nil {
		fmt.Printf("[DWApp] subscribe failed: topic=%s err=%v\n", topic, err)
		return err
	}

	fmt.Printf("[DWApp] P2PSubscribeTopic: reacquiring lock to store subscription\n")
	topicsMu.Lock()
	topics[topic] = &topicState{topic: t, sub: s}
	count := len(topics)
	topicsMu.Unlock()
	telemetry.SetGauge(float32(count), "libp2p", "topics", "active")
	fmt.Printf("[DWApp] subscribed: topic=%s (total=%d)\n", topic, count)
	return nil
}

func P2PUnsubscribeTopic(topic string) error {
	topicsMu.Lock()
	st, ok := topics[topic]
	if ok {
		delete(topics, topic)
	}
	topicsMu.Unlock()
	if !ok {
		return nil
	}
	if st.timer != nil {
		st.timer.Stop()
	}
	st.sub.Cancel()
	if st.topic != nil {
		_ = st.topic.Close()
	}
	if ps != nil {
		_ = ps.UnregisterTopicValidator(topic)
	}
	topicsMu.Lock()
	count := len(topics)
	topicsMu.Unlock()
	telemetry.SetGauge(float32(count), "libp2p", "topics", "active")
	fmt.Printf("[DWApp] unsubscribed: topic=%s (remaining=%d)\n", topic, count)
	return nil
}

// autoJoinTracer observes incoming RPCs and joins topics when peers subscribe.
type autoJoinTracer struct {
	clientCtx client.Context
}

func (t *autoJoinTracer) AddPeer(p peer.ID, proto protocol.ID) {
	fmt.Printf("[DWApp] tracer AddPeer: peer=%s proto=%s\n", p.String(), proto)
}
func (t *autoJoinTracer) RemovePeer(p peer.ID) {
	fmt.Printf("[DWApp] tracer RemovePeer: peer=%s\n", p.String())
}
func (t *autoJoinTracer) Join(topic string) {
	fmt.Printf("[DWApp] tracer Join: topic=%s\n", topic)
}
func (t *autoJoinTracer) Leave(topic string) {
	fmt.Printf("[DWApp] tracer Leave: topic=%s\n", topic)
}
func (t *autoJoinTracer) Graft(p peer.ID, topic string) {
	fmt.Printf("[DWApp] tracer Graft: peer=%s topic=%s\n", p.String(), topic)
	chainID := strings.TrimSpace(t.clientCtx.ChainID)
	prefix := "/" + chainID + "/v1/"
	if strings.HasPrefix(topic, prefix) {
		fmt.Printf("[DWApp] tracer Graft auto-join: topic=%s\n", topic)
		go func(topicStr string, cCtx client.Context) {
			if err := P2PSubscribeTopic(context.Background(), cCtx, topicStr); err != nil {
				fmt.Printf("[DWApp] tracer Graft auto-join FAILED: topic=%s err=%v\n", topicStr, err)
			}
			disableTopicTimer(topicStr)
		}(topic, t.clientCtx)
	}
}
func (t *autoJoinTracer) Prune(p peer.ID, topic string) {
	fmt.Printf("[DWApp] tracer Prune: peer=%s topic=%s\n", p.String(), topic)
}
func (t *autoJoinTracer) ValidateMessage(m *pubsub.Message) {
	if m != nil {
		fmt.Printf("[DWApp] tracer ValidateMessage: topic=%s from=%s\n", m.GetTopic(), m.ReceivedFrom.String())
	}
}
func (t *autoJoinTracer) DeliverMessage(m *pubsub.Message) {
	if m == nil {
		return
	}
	fmt.Printf("[DWApp] tracer DeliverMessage: topic=%s from=%s\n", m.GetTopic(), m.ReceivedFrom.String())
	disableTopicTimer(m.GetTopic())
}
func (t *autoJoinTracer) RejectMessage(m *pubsub.Message, reason string) {
	if m != nil {
		fmt.Printf("[DWApp] tracer RejectMessage: topic=%s from=%s reason=%s\n", m.GetTopic(), m.ReceivedFrom.String(), reason)
	}
}
func (t *autoJoinTracer) DuplicateMessage(m *pubsub.Message) {
	if m != nil {
		fmt.Printf("[DWApp] tracer DuplicateMessage: topic=%s from=%s\n", m.GetTopic(), m.ReceivedFrom.String())
	}
}
func (t *autoJoinTracer) ThrottlePeer(p peer.ID) {
	fmt.Printf("[DWApp] tracer ThrottlePeer: peer=%s\n", p.String())
}
func (t *autoJoinTracer) SendRPC(rpc *pubsub.RPC, p peer.ID) {
	if rpc != nil {
		fmt.Printf("[DWApp] tracer SendRPC: peer=%s subs=%d\n", p.String(), len(rpc.GetSubscriptions()))
	}
}
func (t *autoJoinTracer) DropRPC(rpc *pubsub.RPC, p peer.ID) {
	if rpc != nil {
		fmt.Printf("[DWApp] tracer DropRPC: peer=%s\n", p.String())
	}
}
func (t *autoJoinTracer) UndeliverableMessage(m *pubsub.Message) {
	if m != nil {
		fmt.Printf("[DWApp] tracer UndeliverableMessage: topic=%s\n", m.GetTopic())
	}
}

func (t *autoJoinTracer) RecvRPC(rpc *pubsub.RPC) {
	if rpc == nil || rpc.Subscriptions == nil {
		return
	}
	chainID := strings.TrimSpace(t.clientCtx.ChainID)
	prefix := "/" + chainID + "/v1/"
	fmt.Printf("[DWApp] tracer RecvRPC: %d subs prefix=%s\n", len(rpc.Subscriptions), prefix)
	for _, sub := range rpc.Subscriptions {
		if sub == nil {
			continue
		}
		topic := sub.GetTopicid()
		subscribe := sub.GetSubscribe()
		fmt.Printf("[DWApp] tracer RecvRPC sub: topic=%s subscribe=%v\n", topic, subscribe)
		if !subscribe {
			continue
		}
		if !strings.HasPrefix(topic, prefix) {
			fmt.Printf("[DWApp] tracer RecvRPC: topic %s does not match prefix %s, skipping\n", topic, prefix)
			continue
		}
		// Join and install validator if not already present (async to avoid deadlock)
		fmt.Printf("[DWApp] tracer auto-joining: %s\n", topic)
		go func(topicStr string, cCtx client.Context) {
			if err := P2PSubscribeTopic(context.Background(), cCtx, topicStr); err != nil {
				fmt.Printf("[DWApp] tracer auto-join FAILED: topic=%s err=%v\n", topicStr, err)
			}
			disableTopicTimer(topicStr)
		}(topic, t.clientCtx)
	}
	for _, sub := range rpc.Subscriptions {
		if sub == nil || sub.GetSubscribe() {
			continue
		}
		topic := sub.GetTopicid()
		if strings.HasPrefix(topic, prefix) {
			scheduleTopicCheck(topic)
			fmt.Printf("[DWApp] tracer observed unsubscribe: %s\n", topic)
		}
	}
}

func disableTopicTimer(topic string) {
	topicsMu.Lock()
	if st, ok := topics[topic]; ok {
		if st.timer != nil {
			st.timer.Stop()
			st.timer = nil
		}
	}
	topicsMu.Unlock()
}

func scheduleTopicCheck(topic string) {
	topicsMu.Lock()
	st, ok := topics[topic]
	if !ok {
		topicsMu.Unlock()
		return
	}
	if st.timer != nil {
		st.timer.Stop()
	}
	st.timer = time.AfterFunc(topicIdleTTL, func() {
		if ps == nil {
			return
		}
		if len(ps.ListPeers(topic)) == 0 {
			_ = P2PUnsubscribeTopic(topic)
		} else {
			scheduleTopicCheck(topic)
		}
	})
	topicsMu.Unlock()
}

func recordPeerFailure(p peer.ID) {
	peerRejectsMu.Lock()
	defer peerRejectsMu.Unlock()

	peerRejects[p]++
	if peerRejects[p] >= 5 {
		if ps != nil {
			ps.BlacklistPeer(p)
		}
		delete(peerRejects, p)
	}
}

func resetPeerFailures(p peer.ID) {
	peerRejectsMu.Lock()
	delete(peerRejects, p)
	peerRejectsMu.Unlock()
}

func setTopicGauge() {
	topicsMu.Lock()
	count := len(topics)
	topicsMu.Unlock()
	telemetry.SetGauge(float32(count), "libp2p", "topics", "active")
}
