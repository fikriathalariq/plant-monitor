import { useEffect, useRef, useCallback } from 'react';

/**
 * Custom hook untuk polling periodik dengan proteksi:
 * 1. Anti-Stacking (Recursive setTimeout): Poll berikutnya HANYA dijadwalkan setelah request selesai.
 * 2. Background Tab Pause: Otomatis berhenti saat tab diminimize/background (menghemat PLC & Waitress).
 * 3. Tab Focus Wakeup: Otomatis me-refresh saat tab kembali dibuka.
 * 4. Proper cleanup saat unmount.
 *
 * @param {Function} asyncCallback Fungsi async yang akan dipanggil secara periodik
 * @param {number} intervalMs Durasi interval dalam milidetik (mis. 30000)
 * @param {Object} options Opsi konfigurasi
 * @param {boolean} options.enabled Menyalakan/mematikan polling (default: true)
 * @param {boolean} options.immediate Jalankan seketika saat mount (default: true)
 * @param {boolean} options.pauseOnHidden Berhenti saat tab tidak aktif (default: true)
 */
export function useSmartPolling(
  asyncCallback,
  intervalMs = 30000,
  { enabled = true, immediate = true, pauseOnHidden = true } = {}
) {
  const savedCallback = useRef(asyncCallback);
  const timerRef = useRef(null);
  const isExecutingRef = useRef(false);
  const isMountedRef = useRef(false);

  useEffect(() => {
    savedCallback.current = asyncCallback;
  }, [asyncCallback]);

  const executePoll = useCallback(async () => {
    if (isExecutingRef.current || !isMountedRef.current) return;
    isExecutingRef.current = true;

    try {
      if (savedCallback.current) {
        await savedCallback.current();
      }
    } catch (err) {
      console.warn('[SmartPolling] Error in polling callback:', err);
    } finally {
      isExecutingRef.current = false;
      if (isMountedRef.current && enabled && (!pauseOnHidden || !document.hidden)) {
        clearTimeout(timerRef.current);
        timerRef.current = setTimeout(executePoll, intervalMs);
      }
    }
  }, [enabled, intervalMs, pauseOnHidden]);

  useEffect(() => {
    isMountedRef.current = true;

    if (!enabled) {
      clearTimeout(timerRef.current);
      return () => {
        isMountedRef.current = false;
        clearTimeout(timerRef.current);
      };
    }

    if (immediate && (!pauseOnHidden || !document.hidden)) {
      executePoll();
    } else if (!pauseOnHidden || !document.hidden) {
      timerRef.current = setTimeout(executePoll, intervalMs);
    }

    const handleVisibilityChange = () => {
      if (!pauseOnHidden) return;

      if (document.hidden) {
        clearTimeout(timerRef.current);
      } else if (enabled) {
        clearTimeout(timerRef.current);
        executePoll();
      }
    };

    if (pauseOnHidden) {
      document.addEventListener('visibilitychange', handleVisibilityChange);
    }

    return () => {
      isMountedRef.current = false;
      clearTimeout(timerRef.current);
      if (pauseOnHidden) {
        document.removeEventListener('visibilitychange', handleVisibilityChange);
      }
    };
  }, [enabled, executePoll, immediate, intervalMs, pauseOnHidden]);

  // Kembalikan helper trigger manual
  const triggerNow = useCallback(() => {
    clearTimeout(timerRef.current);
    return executePoll();
  }, [executePoll]);

  return { triggerNow };
}
