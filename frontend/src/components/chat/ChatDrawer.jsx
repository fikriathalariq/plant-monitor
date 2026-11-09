import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  X,
  ArrowLeft,
  Search,
  Send,
  CornerUpLeft,
  Check,
  CheckCheck,
  Activity,
  Plus,
  ClipboardCheck,
  Flame,
  Clock,
  Sparkles,
  MessageSquare,
  Users,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useChat } from '../../context/ChatContext';
import {
  useGetChatContactsQuery,
  useGetChatMessagesQuery,
  useSendChatMessageMutation,
  useGetActiveMachinesListQuery,
  useLazyGetMachineSnapshotQuery,
} from '../../store/chatApi';
import {
  ReportShareCard,
  MachineSnapshotCard,
  ChartBookmarkCard,
  ActionCheckCard,
} from './ChatMessageCards';

const QUICK_TEMPLATES = [
  'Mohon dicek ya 👍',
  'Suhu mesin drop, butuh pengecekan.',
  'Catatan untuk operan shift.',
  'Valve steam sudah dibuka kembali.',
  'Batch sudah selesai diproses.',
];

export const ChatDrawer = () => {
  const { user } = useAuth();
  const { isChatOpen, setIsChatOpen, activeRecipient, setActiveRecipient } = useChat();

  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState('all'); // 'all', 'unread', 'online'
  const [inputContent, setInputContent] = useState('');
  const [replyingTo, setReplyingTo] = useState(null);
  const [showAttachMenu, setShowAttachMenu] = useState(false);
  const [selectedMachineForSnapshot, setSelectedMachineForSnapshot] = useState('');
  const [showTaskModal, setShowTaskModal] = useState(false);
  const [taskNameInput, setTaskNameInput] = useState('');

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Queries
  const {
    data: contactsData,
    isLoading: isContactsLoading,
    refetch: refetchContacts,
  } = useGetChatContactsQuery(undefined, {
    skip: !isChatOpen || !user,
    pollingInterval: isChatOpen ? 5000 : 0,
  });

  const {
    data: messagesData,
    isLoading: isMessagesLoading,
    refetch: refetchMessages,
  } = useGetChatMessagesQuery(
    { otherUserId: activeRecipient?.id },
    {
      skip: !isChatOpen || !activeRecipient?.id,
      pollingInterval: isChatOpen && activeRecipient?.id ? 2000 : 0,
    }
  );

  const { data: machinesData } = useGetActiveMachinesListQuery(undefined, {
    skip: !isChatOpen,
  });

  const [triggerMachineSnapshot, { isFetching: isSnapshotFetching }] = useLazyGetMachineSnapshotQuery();
  const [sendMessage, { isLoading: isSending }] = useSendChatMessageMutation();

  const contacts = contactsData?.contacts || [];
  const messages = messagesData?.messages || [];
  const machines = machinesData?.machines || [];

  // Filter contacts
  const filteredContacts = useMemo(() => {
    return contacts.filter((c) => {
      const matchSearch =
        c.display_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        c.username.toLowerCase().includes(searchQuery.toLowerCase()) ||
        c.position.toLowerCase().includes(searchQuery.toLowerCase());

      if (!matchSearch) return false;
      if (filterType === 'unread') return c.unread_count > 0;
      if (filterType === 'online') return c.is_online;
      return true;
    });
  }, [contacts, searchQuery, filterType]);

  // Auto-scroll on new messages
  useEffect(() => {
    if (activeRecipient) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages.length, activeRecipient]);

  // Focus input when opening chat
  useEffect(() => {
    if (activeRecipient && isChatOpen) {
      setTimeout(() => inputRef.current?.focus(), 150);
    }
  }, [activeRecipient, isChatOpen]);

  // Handle Send Text
  const handleSendText = async (e) => {
    e?.preventDefault();
    if (!inputContent.trim() || !activeRecipient || isSending) return;

    const text = inputContent.trim();
    const replyId = replyingTo?.id;

    setInputContent('');
    setReplyingTo(null);

    try {
      await sendMessage({
        otherUserId: activeRecipient.id,
        content: text,
        message_type: 'TEXT',
        metadata: {},
        reply_to_id: replyId,
      }).unwrap();
      refetchContacts();
    } catch (err) {
      console.error('Failed to send message:', err);
    }
  };

  // Handle Send Machine Snapshot
  const handleSendMachineSnapshot = async (machineCode) => {
    if (!machineCode || !activeRecipient) return;
    setShowAttachMenu(false);
    setSelectedMachineForSnapshot('');

    try {
      const snap = await triggerMachineSnapshot(machineCode).unwrap();
      await sendMessage({
        otherUserId: activeRecipient.id,
        content: `Kondisi mesin ${snap.machine_name} (${snap.machine_code})`,
        message_type: 'MACHINE_SNAPSHOT',
        metadata: snap,
      }).unwrap();
      refetchContacts();
    } catch (err) {
      console.error('Failed to snapshot machine:', err);
    }
  };

  // Handle Send Task / Action Check
  const handleSendTask = async () => {
    if (!taskNameInput.trim() || !activeRecipient) return;
    const taskText = taskNameInput.trim();
    setShowTaskModal(false);
    setTaskNameInput('');
    setShowAttachMenu(false);

    try {
      await sendMessage({
        otherUserId: activeRecipient.id,
        content: taskText,
        message_type: 'ACTION_CHECK',
        metadata: {
          task_name: taskText,
          acknowledged: false,
        },
      }).unwrap();
      refetchContacts();
    } catch (err) {
      console.error('Failed to send task:', err);
    }
  };

  if (!isChatOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden flex justify-end no-print pointer-events-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-slate-900/40 backdrop-blur-[2px] transition-opacity"
        onClick={() => setIsChatOpen(false)}
      />

      {/* Drawer Container */}
      <div className="relative w-full max-w-md bg-white h-full shadow-2xl flex flex-col border-l border-slate-200 z-10 transition-transform duration-300 ease-in-out">
        {/* HEADER */}
        <div className="bg-gradient-to-r from-slate-900 via-slate-800 to-indigo-950 text-white px-4 py-3 shrink-0 flex items-center justify-between shadow-xs">
          {activeRecipient ? (
            <div className="flex items-center gap-3 min-w-0">
              <button
                onClick={() => {
                  setActiveRecipient(null);
                  refetchContacts();
                }}
                className="p-1 -ml-1 text-slate-300 hover:text-white rounded-lg hover:bg-white/10 transition-colors"
                title="Kembali ke Kontak"
              >
                <ArrowLeft className="w-5 h-5" />
              </button>
              <div className="relative shrink-0">
                <div className="w-9 h-9 rounded-full bg-indigo-600 text-white flex items-center justify-center font-bold text-sm shadow-inner uppercase">
                  {activeRecipient.display_name?.charAt(0) || activeRecipient.username?.charAt(0)}
                </div>
                {activeRecipient.is_online && (
                  <span className="absolute bottom-0 right-0 w-3 h-3 bg-emerald-500 border-2 border-slate-900 rounded-full" />
                )}
              </div>
              <div className="min-w-0">
                <div className="font-semibold text-sm truncate flex items-center gap-1.5">
                  <span className="truncate">{activeRecipient.display_name}</span>
                </div>
                <div className="text-[11px] text-slate-300 truncate flex items-center gap-2">
                  <span>{activeRecipient.position}</span>
                  {activeRecipient.shift && activeRecipient.shift !== '-' && (
                    <span className="px-1.5 py-0.2 bg-white/15 text-[10px] rounded-full">
                      {activeRecipient.shift}
                    </span>
                  )}
                  <span className={activeRecipient.is_online ? 'text-emerald-400 font-medium' : 'text-slate-400'}>
                    {activeRecipient.is_online ? '• Online' : '• Offline'}
                  </span>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-indigo-500/20 text-indigo-400 flex items-center justify-center">
                <MessageSquare className="w-4 h-4" />
              </div>
              <div>
                <h3 className="font-semibold text-sm leading-tight">Chat Jaringan Lokal</h3>
                <p className="text-[11px] text-slate-300">Intranet Offline • 100% On-Premise</p>
              </div>
            </div>
          )}

          <button
            onClick={() => setIsChatOpen(false)}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
            title="Tutup Chat"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* BODY */}
        {!activeRecipient ? (
          /* ================= LIST KONTAK VIEW ================= */
          <div className="flex-1 flex flex-col min-h-0 bg-slate-50">
            {/* Search & Filter Bar */}
            <div className="p-3 bg-white border-b border-slate-200 shrink-0 space-y-2">
              <div className="relative">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                <input
                  type="text"
                  placeholder="Cari nama, posisi, shift..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-9 pr-3 py-1.5 bg-slate-100 hover:bg-slate-100/80 focus:bg-white text-xs rounded-lg border border-slate-200 focus:border-indigo-500 focus:outline-hidden transition-all"
                />
              </div>

              {/* Filter Tabs */}
              <div className="flex gap-1.5 text-xs">
                <button
                  onClick={() => setFilterType('all')}
                  className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors ${
                    filterType === 'all'
                      ? 'bg-indigo-600 text-white'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  Semua ({contacts.length})
                </button>
                <button
                  onClick={() => setFilterType('unread')}
                  className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors flex items-center gap-1 ${
                    filterType === 'unread'
                      ? 'bg-indigo-600 text-white'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  <span>Belum Dibaca</span>
                  {contacts.filter((c) => c.unread_count > 0).length > 0 && (
                    <span className="w-4 h-4 rounded-full bg-rose-500 text-white text-[9px] flex items-center justify-center font-bold">
                      {contacts.filter((c) => c.unread_count > 0).length}
                    </span>
                  )}
                </button>
                <button
                  onClick={() => setFilterType('online')}
                  className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors flex items-center gap-1 ${
                    filterType === 'online'
                      ? 'bg-indigo-600 text-white'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" />
                  <span>Online ({contacts.filter((c) => c.is_online).length})</span>
                </button>
              </div>
            </div>

            {/* Contact Items */}
            <div className="flex-1 overflow-y-auto divide-y divide-slate-100">
              {isContactsLoading ? (
                <div className="p-8 text-center text-slate-400 text-xs">Memuat kontak...</div>
              ) : filteredContacts.length === 0 ? (
                <div className="p-8 text-center text-slate-400 text-xs">
                  Tidak ada kontak yang cocok dengan pencarian.
                </div>
              ) : (
                filteredContacts.map((c) => (
                  <div
                    key={c.id}
                    onClick={() => setActiveRecipient(c)}
                    className="p-3 bg-white hover:bg-indigo-50/50 cursor-pointer flex items-center gap-3 transition-colors relative"
                  >
                    <div className="relative shrink-0">
                      <div className="w-10 h-10 rounded-full bg-slate-200 text-slate-700 flex items-center justify-center font-bold text-sm uppercase">
                        {c.display_name?.charAt(0) || c.username?.charAt(0)}
                      </div>
                      {c.is_online && (
                        <span className="absolute bottom-0 right-0 w-3 h-3 bg-emerald-500 border-2 border-white rounded-full" />
                      )}
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-1 mb-0.5">
                        <span className="font-semibold text-xs text-slate-900 truncate">
                          {c.display_name}
                        </span>
                        {c.last_message_at && (
                          <span className="text-[10px] text-slate-400 shrink-0">
                            {c.last_message_at.slice(11, 16)}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-1.5 text-[11px] text-slate-500 mb-0.5">
                        <span className="truncate">{c.position}</span>
                        {c.shift && c.shift !== '-' && (
                          <span className="px-1 py-0.2 bg-slate-100 rounded text-[10px] text-slate-600">
                            {c.shift}
                          </span>
                        )}
                      </div>

                      <p className="text-xs text-slate-500 truncate">
                        {c.last_message_preview || (
                          <span className="italic text-slate-400">Belum ada percakapan</span>
                        )}
                      </p>
                    </div>

                    {c.unread_count > 0 && (
                      <div className="shrink-0 w-5 h-5 rounded-full bg-rose-500 text-white font-bold text-[10px] flex items-center justify-center shadow-xs">
                        {c.unread_count}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        ) : (
          /* ================= 1-ON-1 CHAT ROOM VIEW ================= */
          <div className="flex-1 flex flex-col min-h-0 bg-slate-100/70">
            {/* Messages Scroll Area */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3.5">
              {isMessagesLoading ? (
                <div className="p-6 text-center text-xs text-slate-400">Memuat obrolan...</div>
              ) : messages.length === 0 ? (
                <div className="py-12 text-center">
                  <div className="w-12 h-12 rounded-full bg-indigo-100 text-indigo-600 mx-auto flex items-center justify-center mb-2">
                    <MessageSquare className="w-6 h-6" />
                  </div>
                  <h4 className="text-xs font-semibold text-slate-700">Mulai Obrolan</h4>
                  <p className="text-[11px] text-slate-500 max-w-[220px] mx-auto mt-1">
                    Kirim pesan teks atau bagikan laporan langsung ke {activeRecipient.display_name}.
                  </p>
                </div>
              ) : (
                messages.map((m) => {
                  const isMe = m.sender_id === user?.id || m.sender_username === user?.username;

                  return (
                    <div
                      key={m.id}
                      className={`flex flex-col group ${isMe ? 'items-end' : 'items-start'}`}
                    >
                      {/* Reply Quoted Preview */}
                      {m.reply_to && (
                        <div
                          className={`mb-1 px-2.5 py-1 rounded-lg text-[11px] border border-slate-200/60 max-w-[280px] truncate ${
                            isMe ? 'bg-indigo-50 text-indigo-900' : 'bg-slate-200/80 text-slate-700'
                          }`}
                        >
                          <span className="font-semibold block text-[10px] text-indigo-700">
                            {m.reply_to.sender_name}
                          </span>
                          <span className="truncate block italic">{m.reply_to.content}</span>
                        </div>
                      )}

                      {/* Message Bubble Container */}
                      <div className="relative max-w-[85%] flex items-end gap-1">
                        {/* Reply Button on hover */}
                        <button
                          onClick={() => setReplyingTo(m)}
                          className={`opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-slate-700 rounded transition-opacity ${
                            isMe ? 'order-first' : 'order-last'
                          }`}
                          title="Balas pesan ini"
                        >
                          <CornerUpLeft className="w-3.5 h-3.5" />
                        </button>

                        <div
                          className={`rounded-2xl px-3.5 py-2 text-xs shadow-xs transition-all ${
                            isMe
                              ? 'bg-indigo-600 text-white rounded-br-xs'
                              : 'bg-white text-slate-900 border border-slate-200/80 rounded-bl-xs'
                          }`}
                        >
                          {/* Render Different Message Types */}
                          {m.message_type === 'TEXT' && (
                            <p className="whitespace-pre-wrap break-words leading-relaxed">{m.content}</p>
                          )}

                          {m.message_type === 'REPORT_SHARE' && (
                            <div>
                              {m.content && (
                                <p className="mb-2 whitespace-pre-wrap break-words leading-relaxed font-medium">
                                  {m.content}
                                </p>
                              )}
                              <ReportShareCard
                                metadata={m.metadata}
                                isMe={isMe}
                                onCloseChat={() => setIsChatOpen(false)}
                              />
                            </div>
                          )}

                          {m.message_type === 'MACHINE_SNAPSHOT' && (
                            <div>
                              {m.content && (
                                <p className="mb-2 whitespace-pre-wrap break-words leading-relaxed">
                                  {m.content}
                                </p>
                              )}
                              <MachineSnapshotCard metadata={m.metadata} isMe={isMe} />
                            </div>
                          )}

                          {m.message_type === 'CHART_BOOKMARK' && (
                            <div>
                              {m.content && (
                                <p className="mb-2 whitespace-pre-wrap break-words leading-relaxed">
                                  {m.content}
                                </p>
                              )}
                              <ChartBookmarkCard
                                metadata={m.metadata}
                                isMe={isMe}
                                onCloseChat={() => setIsChatOpen(false)}
                              />
                            </div>
                          )}

                          {m.message_type === 'ACTION_CHECK' && (
                            <div>
                              {m.content && (
                                <p className="mb-2 whitespace-pre-wrap break-words leading-relaxed font-semibold">
                                  {m.content}
                                </p>
                              )}
                              <ActionCheckCard messageId={m.id} metadata={m.metadata} isMe={isMe} />
                            </div>
                          )}

                          {/* Footer: Time & Status Ticks */}
                          <div
                            className={`flex items-center justify-end gap-1 mt-1 text-[10px] ${
                              isMe ? 'text-indigo-200' : 'text-slate-400'
                            }`}
                          >
                            <span>{m.created_at ? m.created_at.slice(11, 16) : ''}</span>
                            {isMe && (
                              <span>
                                {m.is_read ? (
                                  <CheckCheck className="w-3.5 h-3.5 text-cyan-300" />
                                ) : (
                                  <Check className="w-3.5 h-3.5" />
                                )}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* QUICK TEMPLATES CHIPS */}
            <div className="px-3 py-1.5 bg-white border-t border-slate-200/80 shrink-0 overflow-x-auto flex gap-1.5 hide-scrollbar">
              {QUICK_TEMPLATES.map((tmpl, idx) => (
                <button
                  key={idx}
                  onClick={() => setInputContent(tmpl)}
                  className="px-2.5 py-1 rounded-full bg-slate-100 hover:bg-slate-200 active:bg-indigo-100 text-slate-700 text-[11px] whitespace-nowrap shrink-0 transition-colors"
                >
                  {tmpl}
                </button>
              ))}
            </div>

            {/* ATTACHMENT POPUP / MENU */}
            {showAttachMenu && (
              <div className="mx-3 mb-2 p-2.5 bg-white rounded-xl shadow-lg border border-slate-200 shrink-0 animate-in fade-in slide-in-from-bottom-2 duration-150">
                <div className="flex items-center justify-between pb-1.5 border-b border-slate-100 mb-2">
                  <span className="text-xs font-semibold text-slate-800">Lampirkan ke Chat</span>
                  <button
                    onClick={() => setShowAttachMenu(false)}
                    className="p-1 text-slate-400 hover:text-slate-600 rounded"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>

                <div className="space-y-2">
                  {/* Option 1: Snapshot Kondisi Mesin */}
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                      <Activity className="w-4 h-4" />
                    </div>
                    <div className="flex-1 flex gap-1.5">
                      <select
                        value={selectedMachineForSnapshot}
                        onChange={(e) => setSelectedMachineForSnapshot(e.target.value)}
                        className="text-xs py-1 px-2 rounded-lg border border-slate-200 flex-1 focus:outline-hidden"
                      >
                        <option value="">Pilih Mesin Aktif...</option>
                        {machines.map((m) => (
                          <option key={m.id} value={m.code}>
                            {m.code} - {m.name}
                          </option>
                        ))}
                      </select>
                      <button
                        onClick={() => handleSendMachineSnapshot(selectedMachineForSnapshot)}
                        disabled={!selectedMachineForSnapshot || isSnapshotFetching}
                        className="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs font-medium rounded-lg"
                      >
                        {isSnapshotFetching ? '...' : 'Kirim'}
                      </button>
                    </div>
                  </div>

                  {/* Option 2: Tugas Cepat / Action Check */}
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center shrink-0">
                      <ClipboardCheck className="w-4 h-4" />
                    </div>
                    <button
                      onClick={() => setShowTaskModal(true)}
                      className="text-left text-xs font-medium text-slate-700 hover:text-indigo-600 p-1 rounded hover:bg-slate-50 flex-1"
                    >
                      Buat Tiket Instruksi Cepat [✓]
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* TASK / INSTRUCTION MODAL */}
            {showTaskModal && (
              <div className="mx-3 mb-2 p-3 bg-white rounded-xl shadow-lg border border-amber-200 shrink-0">
                <div className="text-xs font-semibold text-slate-800 mb-1.5 flex items-center gap-1.5">
                  <ClipboardCheck className="w-4 h-4 text-amber-600" />
                  <span>Kirim Instruksi Lapangan</span>
                </div>
                <input
                  type="text"
                  placeholder="Contoh: Tolong cek valve steam jalur B..."
                  value={taskNameInput}
                  onChange={(e) => setTaskNameInput(e.target.value)}
                  className="w-full text-xs p-2 rounded-lg border border-slate-200 focus:border-amber-500 focus:outline-hidden mb-2"
                  autoFocus
                />
                <div className="flex justify-end gap-1.5">
                  <button
                    onClick={() => setShowTaskModal(false)}
                    className="px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-100 rounded-md"
                  >
                    Batal
                  </button>
                  <button
                    onClick={handleSendTask}
                    disabled={!taskNameInput.trim()}
                    className="px-3 py-1 bg-amber-600 hover:bg-amber-700 disabled:opacity-50 text-white text-xs font-medium rounded-md"
                  >
                    Kirim Instruksi
                  </button>
                </div>
              </div>
            )}

            {/* REPLYING BANNER */}
            {replyingTo && (
              <div className="mx-3 mb-1 px-3 py-1.5 bg-indigo-50 border border-indigo-200 rounded-lg flex items-center justify-between text-xs shrink-0">
                <div className="truncate min-w-0 pr-2">
                  <span className="font-semibold text-indigo-700 block text-[10px]">
                    Membalas {replyingTo.sender_name}:
                  </span>
                  <span className="text-slate-600 truncate block italic text-[11px]">
                    {replyingTo.content}
                  </span>
                </div>
                <button
                  onClick={() => setReplyingTo(null)}
                  className="p-1 text-slate-400 hover:text-slate-600 rounded"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {/* INPUT FORM */}
            <form
              onSubmit={handleSendText}
              className="p-3 bg-white border-t border-slate-200 shrink-0 flex items-center gap-2"
            >
              <button
                type="button"
                onClick={() => setShowAttachMenu((prev) => !prev)}
                className={`p-2 rounded-lg border transition-colors ${
                  showAttachMenu
                    ? 'bg-indigo-50 border-indigo-300 text-indigo-600'
                    : 'bg-slate-50 border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700'
                }`}
                title="Lampirkan Kondisi Mesin atau Tugas"
              >
                <Plus className="w-4 h-4" />
              </button>

              <input
                ref={inputRef}
                type="text"
                placeholder={`Kirim pesan ke ${activeRecipient.display_name}...`}
                value={inputContent}
                onChange={(e) => setInputContent(e.target.value)}
                className="flex-1 py-2 px-3 bg-slate-50 hover:bg-slate-100/70 focus:bg-white text-xs rounded-lg border border-slate-200 focus:border-indigo-500 focus:outline-hidden transition-all"
              />

              <button
                type="submit"
                disabled={!inputContent.trim() || isSending}
                className="p-2 bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 disabled:opacity-40 text-white rounded-lg transition-colors shadow-xs"
                title="Kirim Pesan"
              >
                <Send className="w-4 h-4" />
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
};
