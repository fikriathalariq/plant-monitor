/**
 * masterkain_nav.js
 * Navigasi keyboard spreadsheet-style untuk form Master Kain di Django Admin.
 *
 * Fitur:
 *   → (ujung kanan field)  → pindah ke field berikutnya
 *   ← (ujung kiri field)   → pindah ke field sebelumnya
 *   Enter (bukan textarea) → pindah ke field berikutnya
 *   Tab / Shift+Tab        → navigasi bawaan browser (tetap berfungsi normal)
 */
(function () {
    'use strict';

    /* ── Kumpulkan semua input yang bisa difokus ─────────────────────────── */
    function getFocusableInputs(form) {
        return Array.from(form.querySelectorAll(
            'input:not([type="hidden"]):not([type="checkbox"]):not([disabled]),' +
            'select:not([disabled]),' +
            'textarea:not([disabled])'
        )).filter(function (el) {
            // Hanya elemen yang benar-benar terlihat
            return el.offsetWidth > 0 && el.offsetHeight > 0;
        });
    }

    /* ── Pindahkan fokus ke field +direction dari posisi saat ini ─────────── */
    function moveFocus(form, currentEl, direction) {
        var inputs = getFocusableInputs(form);
        var idx = inputs.indexOf(currentEl);
        if (idx === -1) return;
        var nextIdx = idx + direction;
        if (nextIdx < 0 || nextIdx >= inputs.length) return;

        var next = inputs[nextIdx];
        next.focus();

        // Pilih semua teks agar bisa langsung diketik ulang
        if (next.tagName.toLowerCase() !== 'select') {
            try { next.select(); } catch (ignore) {}
        }
    }

    /* ── Cek apakah kursor di ujung kanan teks ───────────────────────────── */
    function isAtEnd(el) {
        try {
            // selectionStart bisa null pada <input type="number"> di beberapa browser
            if (el.selectionStart === null || el.selectionStart === undefined) return true;
            return el.selectionStart >= el.value.length;
        } catch (e) {
            return true;
        }
    }

    /* ── Cek apakah kursor di ujung kiri teks ───────────────────────────── */
    function isAtStart(el) {
        try {
            if (el.selectionStart === null || el.selectionStart === undefined) return true;
            return el.selectionStart === 0;
        } catch (e) {
            return true;
        }
    }

    /* ── Cek apakah kursor di baris terakhir textarea ─────────────────────── */
    function isAtLastLine(el) {
        var afterCursor = el.value.substring(el.selectionStart);
        return afterCursor.indexOf('\n') === -1;
    }

    /* ── Cek apakah kursor di baris pertama textarea ─────────────────────── */
    function isAtFirstLine(el) {
        var beforeCursor = el.value.substring(0, el.selectionStart);
        return beforeCursor.indexOf('\n') === -1;
    }

    /* ── Handler utama keydown ───────────────────────────────────────────── */
    function onKeydown(e) {
        var el  = e.target;
        var tag = el.tagName.toLowerCase();

        if (!['input', 'select', 'textarea'].includes(tag)) return;
        if (el.type === 'hidden') return;

        var form = el.closest('form') || document.querySelector('#content-main form');
        if (!form) return;

        switch (e.key) {

            /* Enter → field berikutnya (kecuali di textarea) */
            case 'Enter':
                if (tag !== 'textarea') {
                    e.preventDefault();
                    moveFocus(form, el, 1);
                }
                break;

            /* → di ujung kanan → field berikutnya */
            case 'ArrowRight':
                if (tag === 'select') break; // jangan ganggu dropdown
                if (isAtEnd(el)) {
                    e.preventDefault();
                    moveFocus(form, el, 1);
                }
                break;

            /* ↓ di baris terakhir textarea → field berikutnya */
            case 'ArrowDown':
                if (tag === 'textarea') {
                    if (isAtLastLine(el) && isAtEnd(el)) {
                        e.preventDefault();
                        moveFocus(form, el, 1);
                    }
                }
                break;

            /* ← di ujung kiri → field sebelumnya */
            case 'ArrowLeft':
                if (tag === 'select') break;
                if (isAtStart(el)) {
                    e.preventDefault();
                    moveFocus(form, el, -1);
                }
                break;

            /* ↑ di baris pertama textarea → field sebelumnya */
            case 'ArrowUp':
                if (tag === 'textarea') {
                    if (isAtFirstLine(el) && isAtStart(el)) {
                        e.preventDefault();
                        moveFocus(form, el, -1);
                    }
                }
                break;
        }
    }

    /* ── Pasang event listener setelah DOM siap ──────────────────────────── */
    document.addEventListener('DOMContentLoaded', function () {
        // Pasang ke seluruh halaman — berlaku untuk form utama maupun inline
        document.addEventListener('keydown', onKeydown);
    });

}());
