package dwapp

import (
	"context"
	"errors"
	"fmt"
	"strings"
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

// EnsurePubSub creates the GossipSub instance once and reuses it.
func (s *P2PService) EnsurePubSub(ctx context.Context, clientCtx client.Context) error {
	if s == nil {
		return errors.New("p2p service unavailable")
	}
	if s.host == nil {
		return errors.New("libp2p host not initialized")
	}

	s.pubsubMu.Lock()
	defer s.pubsubMu.Unlock()

	if s.pubsub != nil {
		return nil
	}
	if s.pubsubErr != nil {
		return s.pubsubErr
	}

	tracer := &autoJoinTracer{svc: s, clientCtx: clientCtx}
	s.logger.Info("initializing GossipSub", "peer_id", s.host.ID().String())
	ps, err := pubsub.NewGossipSub(context.Background(), s.host, pubsub.WithRawTracer(tracer))
	if err != nil {
		s.pubsubErr = fmt.Errorf("create gossip-sub: %w", err)
		return s.pubsubErr
	}

	s.pubsub = ps
	s.pubsubErr = nil
	s.logger.Info("GossipSub initialized")
	return nil
}

// SubscribeTopic ensures we are part of the GossipSub mesh for the given topic.
func (s *P2PService) SubscribeTopic(ctx context.Context, clientCtx client.Context, topic string) error {
	if err := s.EnsurePubSub(ctx, clientCtx); err != nil {
		s.logger.Error("ensure pubsub failed", "topic", topic, "err", err)
		return err
	}

	ps := s.pubsub
	if ps == nil {
		return errors.New("pubsub not initialized")
	}

	if !strings.HasSuffix(topic, "/discovery") {
		validator := func(ctx context.Context, p peer.ID, m *pubsub.Message) pubsub.ValidationResult {
			if _, _, err := s.ValidatePubSubPayload(ctx, clientCtx, topic, m.Data, p.String()); err != nil {
				telemetry.IncrCounter(1, "libp2p", "validator", "reject")
				s.recordPeerFailure(p)
				return pubsub.ValidationReject
			}
			telemetry.IncrCounter(1, "libp2p", "validator", "accept")
			s.resetPeerFailures(p)
			return pubsub.ValidationAccept
		}
		if err := ps.RegisterTopicValidator(topic, validator); err != nil {
			s.logger.Error("register topic validator failed", "topic", topic, "err", err)
			return err
		}
	}

	s.topicsMu.Lock()
	if st, ok := s.topics[topic]; ok {
		if st.timer != nil {
			st.timer.Stop()
			st.timer = nil
		}
		s.topicsMu.Unlock()
		return nil
	}
	if len(s.topics) >= topicMax {
		s.topicsMu.Unlock()
		return fmt.Errorf("topic limit reached: %d", topicMax)
	}
	s.topicsMu.Unlock()

	t, err := ps.Join(topic)
	if err != nil {
		return err
	}
	sub, err := t.Subscribe()
	if err != nil {
		return err
	}

	s.topicsMu.Lock()
	s.topics[topic] = &topicState{topic: t, sub: sub}
	count := len(s.topics)
	s.topicsMu.Unlock()
	telemetry.SetGauge(float32(count), "libp2p", "topics", "active")
	return nil
}

// UnsubscribeTopic removes the validator/subscription for a topic.
func (s *P2PService) UnsubscribeTopic(topic string) error {
	s.topicsMu.Lock()
	st, ok := s.topics[topic]
	if ok {
		delete(s.topics, topic)
	}
	s.topicsMu.Unlock()
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
	if s.pubsub != nil {
		_ = s.pubsub.UnregisterTopicValidator(topic)
	}
	s.topicsMu.Lock()
	count := len(s.topics)
	s.topicsMu.Unlock()
	telemetry.SetGauge(float32(count), "libp2p", "topics", "active")
	return nil
}

// autoJoinTracer observes incoming RPCs and joins topics when peers subscribe.
type autoJoinTracer struct {
	svc       *P2PService
	clientCtx client.Context
}

func (t *autoJoinTracer) AddPeer(p peer.ID, proto protocol.ID) {
}
func (t *autoJoinTracer) RemovePeer(p peer.ID) {}
func (t *autoJoinTracer) Join(topic string)    {}
func (t *autoJoinTracer) Leave(topic string)   {}
func (t *autoJoinTracer) Graft(p peer.ID, topic string) {
	chainID := strings.TrimSpace(t.clientCtx.ChainID)
	prefix := "/" + chainID + "/v1/"
	if strings.HasPrefix(topic, prefix) {
		go func(tp string, c client.Context) {
			if err := t.svc.SubscribeTopic(context.Background(), c, tp); err != nil {
				t.svc.logger.Error("tracer auto-join failed", "topic", tp, "err", err)
			}
			t.svc.disableTopicTimer(tp)
		}(topic, t.clientCtx)
	}
}
func (t *autoJoinTracer) Prune(p peer.ID, topic string)     {}
func (t *autoJoinTracer) ValidateMessage(m *pubsub.Message) {}
func (t *autoJoinTracer) DeliverMessage(m *pubsub.Message) {
	if m == nil {
		return
	}
	t.svc.disableTopicTimer(m.GetTopic())
}
func (t *autoJoinTracer) RejectMessage(m *pubsub.Message, reason string) {}
func (t *autoJoinTracer) DuplicateMessage(m *pubsub.Message)             {}
func (t *autoJoinTracer) ThrottlePeer(p peer.ID)                         {}
func (t *autoJoinTracer) SendRPC(rpc *pubsub.RPC, p peer.ID)             {}
func (t *autoJoinTracer) DropRPC(rpc *pubsub.RPC, p peer.ID)             {}
func (t *autoJoinTracer) UndeliverableMessage(m *pubsub.Message)         {}

func (t *autoJoinTracer) RecvRPC(rpc *pubsub.RPC) {
	if rpc == nil || rpc.Subscriptions == nil {
		return
	}
	chainID := strings.TrimSpace(t.clientCtx.ChainID)
	prefix := "/" + chainID + "/v1/"
	for _, sub := range rpc.Subscriptions {
		if sub == nil {
			continue
		}
		topic := sub.GetTopicid()
		subscribe := sub.GetSubscribe()
		if subscribe && strings.HasPrefix(topic, prefix) {
			go func(tp string, c client.Context) {
				if err := t.svc.SubscribeTopic(context.Background(), c, tp); err != nil {
					t.svc.logger.Error("tracer auto-join failed", "topic", tp, "err", err)
				}
				t.svc.disableTopicTimer(tp)
			}(topic, t.clientCtx)
		}
	}
	for _, sub := range rpc.Subscriptions {
		if sub == nil || sub.GetSubscribe() {
			continue
		}
		topic := sub.GetTopicid()
		if strings.HasPrefix(topic, prefix) {
			t.svc.scheduleTopicCheck(topic)
		}
	}
}

func (s *P2PService) disableTopicTimer(topic string) {
	s.topicsMu.Lock()
	if st, ok := s.topics[topic]; ok {
		if st.timer != nil {
			st.timer.Stop()
			st.timer = nil
		}
	}
	s.topicsMu.Unlock()
}

func (s *P2PService) scheduleTopicCheck(topic string) {
	s.topicsMu.Lock()
	st, ok := s.topics[topic]
	if !ok {
		s.topicsMu.Unlock()
		return
	}
	if st.timer != nil {
		st.timer.Stop()
	}
	st.timer = time.AfterFunc(topicIdleTTL, func() {
		if s.pubsub == nil {
			return
		}
		if len(s.pubsub.ListPeers(topic)) == 0 {
			_ = s.UnsubscribeTopic(topic)
		} else {
			s.scheduleTopicCheck(topic)
		}
	})
	s.topicsMu.Unlock()
}

func (s *P2PService) recordPeerFailure(p peer.ID) {
	s.peerRejectsMu.Lock()
	defer s.peerRejectsMu.Unlock()

	s.peerRejects[p]++
	if s.peerRejects[p] >= 5 {
		if s.pubsub != nil {
			s.pubsub.BlacklistPeer(p)
		}
		delete(s.peerRejects, p)
	}
}

func (s *P2PService) resetPeerFailures(p peer.ID) {
	s.peerRejectsMu.Lock()
	delete(s.peerRejects, p)
	s.peerRejectsMu.Unlock()
}
