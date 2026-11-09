/**
 * machine_admin_clipboard.js
 * Adds "Copy Selected to Clipboard" functionality to the Machines changelist admin.
 * Reads checked rows, extracts cell text, formats as TSV (Tab-Separated Values),
 * then copies to clipboard — ready to paste into Excel or Google Sheets.
 */

(function () {
    "use strict";

    function getCheckedRows() {
        // Only look at the action-select checkbox inside `td.action-checkbox`, NOT all checkboxes in the row.
        // Without this, list_editable checkboxes (e.g. is_active) would cause each row to be returned twice.
        const checkboxes = document.querySelectorAll(
            '#result_list tbody tr td.action-checkbox input[type="checkbox"]:checked'
        );
        return Array.from(checkboxes).map(cb => cb.closest('tr'));
    }


    function getHeaderLabels() {
        // Grab column headers from the changelist table
        const headers = document.querySelectorAll('#result_list thead th');
        const labels = [];
        headers.forEach(th => {
            // Skip the checkbox-column header by class (same strategy as cells)
            if (th.classList.contains('action-checkbox-column')) return;
            // Prefer text from the sort link if present (avoids picking up arrow icons)
            const sortLink = th.querySelector('a');
            const text = sortLink ? sortLink.innerText.trim() : th.innerText.trim();
            labels.push(text);
        });
        return labels;
    }

    function getCellText(td) {
        // Get plain text from a cell, stripping HTML
        // For checkboxes (is_active column), extract checked state
        const checkbox = td.querySelector('input[type="checkbox"]');
        if (checkbox) {
            return checkbox.checked ? 'Yes' : 'No';
        }
        // For select (list_editable fields like is_active rendered as select)
        const select = td.querySelector('select');
        if (select) {
            const selectedOption = select.options[select.selectedIndex];
            if (selectedOption) {
                const val = selectedOption.value;
                if (val === '1' || val === 'true' || val === 'True') return 'Yes';
                if (val === '0' || val === 'false' || val === 'False') return 'No';
                return selectedOption.innerText.trim();
            }
        }
        return td.innerText.trim().replace(/\n/g, ' ');
    }

    function buildTSV(rows) {
        // Build header row
        const headers = getHeaderLabels();
        let lines = [headers.join('\t')];

        rows.forEach(row => {
            // IMPORTANT: Django admin renders the first data column (list_display_links field)
            // as a <th scope="row"> inside tbody, NOT a <td>.
            // We must query BOTH td and th to capture all cells.
            const cells_els = row.querySelectorAll('td, th');
            const cells = [];
            cells_els.forEach(cell => {
                // Skip the action-checkbox td (the row selector checkbox)
                if (cell.classList.contains('action-checkbox')) return;
                cells.push(getCellText(cell));
            });
            if (cells.length > 0) {
                lines.push(cells.join('\t'));
            }
        });

        return lines.join('\n');
    }

    function showToast(message, isSuccess) {
        let toast = document.getElementById('machine-copy-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'machine-copy-toast';
            toast.style.cssText = `
                position: fixed;
                bottom: 30px;
                right: 30px;
                padding: 12px 24px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 600;
                color: white;
                z-index: 9999;
                box-shadow: 0 4px 12px rgba(0,0,0,0.25);
                transition: opacity 0.4s ease;
                opacity: 0;
            `;
            document.body.appendChild(toast);
        }
        toast.style.backgroundColor = isSuccess ? '#28a745' : '#dc3545';
        toast.innerText = message;
        toast.style.opacity = '1';

        setTimeout(() => {
            toast.style.opacity = '0';
        }, 3000);
    }

    function copySelectedRows() {
        const rows = getCheckedRows();

        if (rows.length === 0) {
            showToast('⚠️ Tidak ada baris yang dipilih!', false);
            return;
        }

        const tsv = buildTSV(rows);

        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(tsv).then(() => {
                showToast(`✅ ${rows.length} baris berhasil disalin! (Ctrl+V ke Excel/Sheets)`, true);
            }).catch(err => {
                console.error('Clipboard error:', err);
                showToast('❌ Gagal menyalin ke clipboard.', false);
            });
        } else {
            // Fallback for older browsers
            const textarea = document.createElement('textarea');
            textarea.value = tsv;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.focus();
            textarea.select();
            try {
                document.execCommand('copy');
                showToast(`✅ ${rows.length} baris berhasil disalin! (Ctrl+V ke Excel/Sheets)`, true);
            } catch (err) {
                showToast('❌ Gagal menyalin ke clipboard.', false);
            }
            document.body.removeChild(textarea);
        }
    }

    function injectCopyButton() {
        const actionBar = document.querySelector('.object-tools');
        if (!actionBar) return;

        // Avoid duplicates
        if (document.getElementById('machine-copy-btn')) return;

        const btn = document.createElement('a');
        btn.id = 'machine-copy-btn';
        btn.href = '#';
        btn.innerText = '📋 Copy Selected to Clipboard';
        btn.style.cssText = `
            display: inline-block;
            padding: 8px 16px;
            background: #17a2b8;
            color: white !important;
            border-radius: 4px;
            font-size: 13px;
            font-weight: 600;
            text-decoration: none;
            margin-left: 8px;
            transition: background 0.2s;
        `;
        btn.addEventListener('mouseenter', () => {
            btn.style.background = '#138496';
        });
        btn.addEventListener('mouseleave', () => {
            btn.style.background = '#17a2b8';
        });
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            copySelectedRows();
        });

        const li = document.createElement('li');
        li.appendChild(btn);
        actionBar.appendChild(li);
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', injectCopyButton);
    } else {
        injectCopyButton();
    }
})();
