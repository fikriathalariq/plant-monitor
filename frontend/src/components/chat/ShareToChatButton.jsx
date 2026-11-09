import React from 'react';
import { Share2 } from 'lucide-react';
import { useChat } from '../../context/ChatContext';

export const ShareToChatButton = ({
  reportPayload,
  className = '',
  variant = 'default', // 'default', 'outline', 'subtle'
  label = 'Bagikan ke Chat',
}) => {
  const { openShareModal } = useChat();

  const handleClick = (e) => {
    e.stopPropagation();
    if (reportPayload) {
      openShareModal(reportPayload);
    }
  };

  const baseStyle =
    'inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer shadow-xs active:scale-95 no-print';

  const variants = {
    default: 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-indigo-200',
    outline: 'border border-indigo-200 bg-white hover:bg-indigo-50 text-indigo-700',
    subtle: 'bg-indigo-50 hover:bg-indigo-100 text-indigo-700',
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      className={`${baseStyle} ${variants[variant] || variants.default} ${className}`}
      title="Bagikan laporan ini ke rekan kerja lewat chat lokal"
    >
      <Share2 className="w-3.5 h-3.5" />
      <span>{label}</span>
    </button>
  );
};
