import React, { createContext, useContext, useState, useRef, useEffect, useCallback } from 'react';
import { useAuth } from './AuthContext';
import { useGetChatUnreadSummaryQuery } from '../store/chatApi';

const ChatContext = createContext();

// Pleasant, soft notification chime using Web Audio API (0 bytes extra assets, works 100% offline)
export const playChatChime = () => {
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    const ctx = new AudioContextClass();
    const now = ctx.currentTime;

    // Chime Note 1
    const osc1 = ctx.createOscillator();
    const gain1 = ctx.createGain();
    osc1.type = 'sine';
    osc1.frequency.setValueAtTime(587.33, now); // D5
    gain1.gain.setValueAtTime(0.12, now);
    gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.22);
    osc1.connect(gain1);
    gain1.connect(ctx.destination);
    osc1.start(now);
    osc1.stop(now + 0.22);

    // Chime Note 2 (higher harmony)
    const osc2 = ctx.createOscillator();
    const gain2 = ctx.createGain();
    osc2.type = 'sine';
    osc2.frequency.setValueAtTime(880.0, now + 0.1); // A5
    gain2.gain.setValueAtTime(0.12, now + 0.1);
    gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
    osc2.connect(gain2);
    gain2.connect(ctx.destination);
    osc2.start(now + 0.1);
    osc2.stop(now + 0.35);
  } catch (err) {
    // Ignore audio autoplay restrictions
  }
};

export const ChatProvider = ({ children }) => {
  const { user } = useAuth();
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [activeRecipient, setActiveRecipient] = useState(null);
  const [pendingShareReport, setPendingShareReport] = useState(null);
  const [isShareModalOpen, setIsShareModalOpen] = useState(false);

  // Poll unread summary only if authenticated: 3s if drawer is open, 12s if closed
  const { data: unreadData, refetch: refetchUnread } = useGetChatUnreadSummaryQuery(undefined, {
    skip: !user,
    pollingInterval: isChatOpen ? 3000 : 12000,
  });

  const unreadCount = unreadData?.total_unread || 0;
  const prevUnreadRef = useRef(unreadCount);

  // Chime and window title alert on new message
  useEffect(() => {
    if (unreadCount > prevUnreadRef.current) {
      playChatChime();
    }
    prevUnreadRef.current = unreadCount;
  }, [unreadCount]);

  const toggleChat = useCallback(() => {
    setIsChatOpen((prev) => !prev);
  }, []);

  const openChatWithUser = useCallback((targetUser) => {
    setActiveRecipient(targetUser);
    setIsChatOpen(true);
  }, []);

  const openShareModal = useCallback((reportPayload) => {
    setPendingShareReport(reportPayload);
    setIsShareModalOpen(true);
  }, []);

  const closeShareModal = useCallback(() => {
    setIsShareModalOpen(false);
    setPendingShareReport(null);
  }, []);

  return (
    <ChatContext.Provider
      value={{
        isChatOpen,
        setIsChatOpen,
        toggleChat,
        activeRecipient,
        setActiveRecipient,
        openChatWithUser,
        pendingShareReport,
        openShareModal,
        closeShareModal,
        isShareModalOpen,
        unreadCount,
        refetchUnread,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
};

export const useChat = () => {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error('useChat must be used within a ChatProvider');
  }
  return context;
};
