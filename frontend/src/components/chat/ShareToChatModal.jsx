import React, { useState, useMemo } from 'react';
import { X, Send, Search, Check, FileText } from 'lucide-react';
import { useChat } from '../../context/ChatContext';
import { useGetChatContactsQuery, useSendChatMessageMutation } from '../../store/chatApi';

export const ShareToChatModal = () => {
  const { isShareModalOpen, closeShareModal, pendingShareReport, openChatWithUser } = useChat();
  const { data: contactsData, isLoading: isContactsLoading } = useGetChatContactsQuery(undefined, {
    skip: !isShareModalOpen,
  });
  const [sendChatMessage, { isLoading: isSending }] = useSendChatMessageMutation();

  const [selectedRecipientId, setSelectedRecipientId] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [comment, setComment] = useState('');

  const contacts = contactsData?.contacts || [];

  const filteredContacts = useMemo(() => {
    return contacts.filter((c) => {
      return (
        c.display_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        c.username.toLowerCase().includes(searchQuery.toLowerCase()) ||
        c.position.toLowerCase().includes(searchQuery.toLowerCase())
      );
    });
  }, [contacts, searchQuery]);

  if (!isShareModalOpen || !pendingShareReport) return null;

  const handleShare = async () => {
    if (!selectedRecipientId || isSending) return;

    const targetUser = contacts.find((c) => c.id === selectedRecipientId);

    try {
      await sendChatMessage({
        otherUserId: selectedRecipientId,
        content: comment.trim(),
        message_type: 'REPORT_SHARE',
        metadata: pendingShareReport,
      }).unwrap();

      closeShareModal();
      if (targetUser) {
        openChatWithUser(targetUser);
      }
    } catch (err) {
      console.error('Failed to share report:', err);
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-hidden flex items-center justify-center p-4 no-print">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-slate-900/50 backdrop-blur-[2px] transition-opacity"
        onClick={closeShareModal}
      />

      {/* Modal Card */}
      <div className="relative w-full max-w-md bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden flex flex-col max-h-[90vh] z-10 animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="bg-gradient-to-r from-slate-900 via-slate-800 to-indigo-950 text-white px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-blue-500/20 text-blue-400 flex items-center justify-center">
              <FileText className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-semibold text-sm">Bagikan Laporan ke Rekan Kerja</h3>
              <p className="text-[11px] text-slate-300">Jaringan Lokal Intranet</p>
            </div>
          </div>
          <button
            onClick={closeShareModal}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 overflow-y-auto flex-1 space-y-3.5">
          {/* Report Preview */}
          <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-3">
            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-blue-100 text-blue-800 uppercase tracking-wider">
              {pendingShareReport.report_type?.replace(/_/g, ' ') || 'LAPORAN'}
            </span>
            <h4 className="text-xs font-bold text-slate-900 mt-1 truncate">
              {pendingShareReport.title}
            </h4>
            {pendingShareReport.subtitle && (
              <p className="text-[11px] text-slate-500 truncate">{pendingShareReport.subtitle}</p>
            )}

            {pendingShareReport.metrics && Object.keys(pendingShareReport.metrics).length > 0 && (
              <div className="grid grid-cols-2 gap-1.5 mt-2 pt-2 border-t border-slate-200/60 text-[11px]">
                {Object.entries(pendingShareReport.metrics).map(([k, v]) => (
                  <div key={k} className="flex flex-col">
                    <span className="text-[10px] text-slate-500">{k}</span>
                    <span className="font-semibold text-slate-800">{v}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Recipient Selection */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1.5">
              Pilih Penerima:
            </label>
            <div className="relative mb-2">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
              <input
                type="text"
                placeholder="Cari operator, supervisor..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-8 pr-3 py-1.5 text-xs bg-slate-50 rounded-lg border border-slate-200 focus:bg-white focus:border-indigo-500 focus:outline-hidden"
              />
            </div>

            <div className="max-h-40 overflow-y-auto border border-slate-200 rounded-xl divide-y divide-slate-100 bg-white">
              {isContactsLoading ? (
                <div className="p-3 text-center text-xs text-slate-400">Memuat kontak...</div>
              ) : filteredContacts.length === 0 ? (
                <div className="p-3 text-center text-xs text-slate-400">Tidak ada kontak ditemukan</div>
              ) : (
                filteredContacts.map((c) => {
                  const isSelected = selectedRecipientId === c.id;
                  return (
                    <div
                      key={c.id}
                      onClick={() => setSelectedRecipientId(c.id)}
                      className={`p-2.5 flex items-center justify-between cursor-pointer transition-colors ${
                        isSelected ? 'bg-indigo-50/80' : 'hover:bg-slate-50'
                      }`}
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className="w-7 h-7 rounded-full bg-slate-200 text-slate-700 flex items-center justify-center font-bold text-xs uppercase shrink-0">
                          {c.display_name?.charAt(0) || c.username?.charAt(0)}
                        </div>
                        <div className="min-w-0">
                          <div className="text-xs font-semibold text-slate-900 truncate flex items-center gap-1.5">
                            <span>{c.display_name}</span>
                            {c.is_online && (
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" />
                            )}
                          </div>
                          <div className="text-[10px] text-slate-500 truncate">
                            {c.position} {c.shift && c.shift !== '-' ? `• ${c.shift}` : ''}
                          </div>
                        </div>
                      </div>

                      {isSelected && (
                        <div className="w-5 h-5 rounded-full bg-indigo-600 text-white flex items-center justify-center shrink-0">
                          <Check className="w-3.5 h-3.5" />
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Optional Note */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Catatan Tambahan (Opsional):
            </label>
            <input
              type="text"
              placeholder="Contoh: Tolong evaluasi anomali suhu di batch ini"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              className="w-full text-xs p-2 rounded-lg border border-slate-200 focus:border-indigo-500 focus:outline-hidden"
            />
          </div>
        </div>

        {/* Footer */}
        <div className="px-4 py-3 bg-slate-50 border-t border-slate-200 flex justify-end gap-2">
          <button
            onClick={closeShareModal}
            className="px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-200 rounded-lg transition-colors font-medium"
          >
            Batal
          </button>
          <button
            onClick={handleShare}
            disabled={!selectedRecipientId || isSending}
            className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 text-white text-xs font-semibold rounded-lg flex items-center gap-1.5 shadow-xs transition-colors"
          >
            <Send className="w-3.5 h-3.5" />
            <span>{isSending ? 'Mengirim...' : 'Kirim Laporan'}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
