# -*- coding: utf-8 -*-
"""
dialogs.py — GUI dialogs for SeriesMerge.

MainDialog
  Three-tab view:
    • "Ready to Merge"  — complete sequential series with checkboxes
    • "Singletons"      — only index 1 present (confirm-complete list)
    • "Incomplete"      — gaps in sequence (log/fetch list)
  Buttons: Scan Library | Merge Selected | View Log | Close
"""

import os
from functools import partial

from PyQt5.Qt import (
    Qt, QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTabWidget, QWidget, QTableWidget, QTableWidgetItem,
    QTextEdit, QSplitter, QHeaderView, QProgressBar, QCheckBox,
    QAbstractItemView, QSizePolicy, pyqtSignal, QApplication,
    QDialogButtonBox, QMessageBox, QFont, QColor,
)

from calibre.gui2 import error_dialog, info_dialog, open_url
from calibre.gui2.dialogs.message_box import ViewLog

# PyQt5 < 5.15 exposes QHeaderView.Stretch directly; newer builds (used by
# Calibre 8+) moved all enum values into scoped sub-namespaces.
_STRETCH = getattr(QHeaderView, 'Stretch',
                   getattr(getattr(QHeaderView, 'ResizeMode', None), 'Stretch', 1))


# ---------------------------------------------------------------------------
# Tiny helper widgets
# ---------------------------------------------------------------------------

class _UrlItem(QTableWidgetItem):
    """Table cell that stores a URL and looks like a link."""
    def __init__(self, url):
        super().__init__(url or '—')
        self.url = url or ''
        if url:
            self.setForeground(QColor('#2255AA'))
            font = self.font()
            font.setUnderline(True)
            self.setFont(font)


# ---------------------------------------------------------------------------
# Scan-result table builders
# ---------------------------------------------------------------------------

def _fill_complete_table(table, groups):
    """Populate the 'Ready to Merge' table.  Column 0 has checkboxes."""
    cols = ['✓', 'Series', 'Author(s)', '# Books', 'Indices', 'URL']
    table.setColumnCount(len(cols))
    table.setHorizontalHeaderLabels(cols)
    table.setRowCount(len(groups))
    table.setSelectionBehavior(QAbstractItemView.SelectRows)

    for row, g in enumerate(groups):
        # Checkbox
        chk = QTableWidgetItem()
        chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        chk.setCheckState(Qt.Checked if not g.get('skip_reason') else Qt.Unchecked)
        table.setItem(row, 0, chk)

        indices_str = ', '.join(str(int(round(i))) for i, _ in g['books'])
        table.setItem(row, 1, QTableWidgetItem(g['series_name']))
        table.setItem(row, 2, QTableWidgetItem(', '.join(g['authors'])))
        table.setItem(row, 3, QTableWidgetItem(str(len(g['books']))))
        table.setItem(row, 4, QTableWidgetItem(indices_str))
        table.setItem(row, 5, _UrlItem(g.get('url', '')))

        if g.get('skip_reason'):
            for col in range(len(cols)):
                item = table.item(row, col)
                if item:
                    item.setForeground(QColor('gray'))
                    item.setToolTip(f'Skipped: {g["skip_reason"]}')

    table.horizontalHeader().setSectionResizeMode(1, _STRETCH)
    table.horizontalHeader().setSectionResizeMode(2, _STRETCH)
    table.setColumnWidth(0, 30)
    table.setColumnWidth(3, 60)
    table.setColumnWidth(4, 140)
    table.setSortingEnabled(True)


def _fill_singleton_table(table, groups):
    """Populate the 'Singletons' table."""
    cols = ['Series', 'Author(s)', 'Book title', 'URL']
    table.setColumnCount(len(cols))
    table.setHorizontalHeaderLabels(cols)
    table.setRowCount(len(groups))

    for row, g in enumerate(groups):
        _, bid = g['books'][0]
        table.setItem(row, 0, QTableWidgetItem(g['series_name']))
        table.setItem(row, 1, QTableWidgetItem(', '.join(g['authors'])))
        table.setItem(row, 2, QTableWidgetItem(f'book_id={bid}'))
        table.setItem(row, 3, _UrlItem(g.get('url', '')))

    table.horizontalHeader().setSectionResizeMode(0, _STRETCH)
    table.horizontalHeader().setSectionResizeMode(1, _STRETCH)
    table.setSortingEnabled(True)


def _fill_incomplete_table(table, groups):
    """Populate the 'Incomplete' table."""
    cols = ['Series', 'Author(s)', 'Have', 'Missing', 'URL']
    table.setColumnCount(len(cols))
    table.setHorizontalHeaderLabels(cols)
    table.setRowCount(len(groups))

    for row, g in enumerate(groups):
        have_str    = ', '.join(str(int(round(i))) for i, _ in g['books'])
        missing_str = ', '.join(str(m) for m in g['missing'])
        table.setItem(row, 0, QTableWidgetItem(g['series_name']))
        table.setItem(row, 1, QTableWidgetItem(', '.join(g['authors'])))
        table.setItem(row, 2, QTableWidgetItem(have_str))
        item = QTableWidgetItem(missing_str)
        item.setForeground(QColor('#CC3300'))
        table.setItem(row, 3, item)
        table.setItem(row, 4, _UrlItem(g.get('url', '')))

    table.horizontalHeader().setSectionResizeMode(0, _STRETCH)
    table.horizontalHeader().setSectionResizeMode(1, _STRETCH)
    table.setSortingEnabled(True)


# ---------------------------------------------------------------------------
# Main Dialog
# ---------------------------------------------------------------------------

class MainDialog(QDialog):

    def __init__(self, parent, plugin_action):
        QDialog.__init__(self, parent)
        self.plugin_action = plugin_action
        self.setWindowTitle('SeriesMerge — Automatic Series Merger')
        self.resize(900, 620)

        self._scan_results  = None   # filled after scan
        self._merge_results = []     # (ok, new_id, msg) from merge runs
        self._log_lines     = []
        self._log_path      = None

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ---- top status label ----------------------------------------
        self.status_label = QLabel('Click "Scan Library" to begin.')
        self.status_label.setStyleSheet('font-weight: bold; padding: 4px;')
        layout.addWidget(self.status_label)

        # ---- progress bar --------------------------------------------
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # ---- tab widget ----------------------------------------------
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self._build_complete_tab()
        self._build_singleton_tab()
        self._build_incomplete_tab()

        # ---- log area ------------------------------------------------
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumHeight(130)
        self.log_edit.setFont(QFont('Courier', 9))
        self.log_edit.setPlaceholderText('Merge log will appear here…')
        layout.addWidget(self.log_edit)

        # ---- buttons -------------------------------------------------
        btn_layout = QHBoxLayout()

        self.btn_scan = QPushButton('🔍  Scan Library')
        self.btn_scan.setMinimumWidth(140)
        self.btn_scan.clicked.connect(self._on_scan)
        btn_layout.addWidget(self.btn_scan)

        self.btn_select_all = QPushButton('Select All')
        self.btn_select_all.clicked.connect(self._on_select_all)
        self.btn_select_all.setEnabled(False)
        btn_layout.addWidget(self.btn_select_all)

        self.btn_deselect = QPushButton('Deselect All')
        self.btn_deselect.clicked.connect(self._on_deselect_all)
        self.btn_deselect.setEnabled(False)
        btn_layout.addWidget(self.btn_deselect)

        btn_layout.addStretch()

        self.btn_merge = QPushButton('▶  Merge Selected')
        self.btn_merge.setMinimumWidth(150)
        self.btn_merge.setStyleSheet('QPushButton { font-weight: bold; }')
        self.btn_merge.setEnabled(False)
        self.btn_merge.clicked.connect(self._on_merge)
        btn_layout.addWidget(self.btn_merge)

        self.btn_log = QPushButton('📄  Open Log File')
        self.btn_log.setEnabled(False)
        self.btn_log.clicked.connect(self._on_open_log)
        btn_layout.addWidget(self.btn_log)

        self.btn_close = QPushButton('Close')
        self.btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def _build_complete_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        lbl = QLabel(
            'Series with sequential indices 1 → N (all EPUBs present).  '
            'Tick the ones you want to merge, then click <b>Merge Selected</b>.'
        )
        lbl.setWordWrap(True)
        v.addWidget(lbl)
        self.tbl_complete = QTableWidget()
        self.tbl_complete.cellDoubleClicked.connect(self._on_cell_double_click)
        v.addWidget(self.tbl_complete)
        self.tabs.addTab(w, '✅  Ready to Merge (0)')

    def _build_singleton_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        lbl = QLabel(
            'Only book #1 found for these series.  '
            'Check the URL to confirm whether additional books exist.'
        )
        lbl.setWordWrap(True)
        v.addWidget(lbl)
        self.tbl_singletons = QTableWidget()
        self.tbl_singletons.cellDoubleClicked.connect(self._on_cell_double_click)
        v.addWidget(self.tbl_singletons)
        self.tabs.addTab(w, '📖  Singletons / Confirm Complete (0)')

    def _build_incomplete_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        lbl = QLabel(
            'These series have gaps.  '
            'The <b>Missing</b> column shows which index numbers are absent.  '
            'Double-click a URL cell to open it.'
        )
        lbl.setWordWrap(True)
        v.addWidget(lbl)
        self.tbl_incomplete = QTableWidget()
        self.tbl_incomplete.cellDoubleClicked.connect(self._on_cell_double_click)
        v.addWidget(self.tbl_incomplete)
        self.tabs.addTab(w, '⚠️  Incomplete (0)')

    # ------------------------------------------------------------------
    # Slot: Scan
    # ------------------------------------------------------------------

    def _on_scan(self):
        from calibre_plugins.series_merge.scanner import scan_library
        from calibre_plugins.series_merge.config  import prefs

        epubmerge = self.plugin_action.get_epubmerge_plugin()
        if not epubmerge:
            error_dialog(
                self, 'EpubMerge not found',
                'EpubMerge 1.3.1+ must be installed and enabled.\n'
                'Install it via Preferences ▸ Plugins.',
                show=True,
            )
            return

        self.btn_scan.setEnabled(False)
        self.btn_merge.setEnabled(False)
        self.btn_select_all.setEnabled(False)
        self.btn_deselect.setEnabled(False)
        self.status_label.setText('Scanning library…')
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)   # indeterminate
        QApplication.processEvents()

        try:
            db = self.plugin_action.gui.current_db
            results = scan_library(
                db,
                tol=float(prefs['index_tolerance']),
                require_epub=bool(prefs['require_epub_for_all']),
            )
        except Exception as exc:
            import traceback
            error_dialog(self, 'Scan failed', str(exc),
                         det_msg=traceback.format_exc(), show=True)
            self.btn_scan.setEnabled(True)
            self.progress.setVisible(False)
            self.status_label.setText('Scan failed — see error.')
            return

        self._scan_results = results
        self.progress.setVisible(False)

        # ---- populate tables -----------------------------------------
        complete   = results['complete']
        singletons = results['singletons']
        incomplete = results['incomplete']

        _fill_complete_table(self.tbl_complete,   complete)
        _fill_singleton_table(self.tbl_singletons, singletons)
        _fill_incomplete_table(self.tbl_incomplete, incomplete)

        self.tabs.setTabText(0, f'✅  Ready to Merge ({len(complete)})')
        self.tabs.setTabText(1, f'📖  Singletons / Confirm Complete ({len(singletons)})')
        self.tabs.setTabText(2, f'⚠️  Incomplete ({len(incomplete)})')

        self.status_label.setText(
            f'Scan complete — {len(complete)} mergeable, '
            f'{len(singletons)} singletons, {len(incomplete)} incomplete.'
        )

        has_complete = len(complete) > 0
        self.btn_merge.setEnabled(has_complete)
        self.btn_select_all.setEnabled(has_complete)
        self.btn_deselect.setEnabled(has_complete)
        self.btn_scan.setEnabled(True)

    # ------------------------------------------------------------------
    # Slot: Merge
    # ------------------------------------------------------------------

    def _on_merge(self):
        from calibre_plugins.series_merge.merger import merge_series_group, write_log
        from calibre_plugins.series_merge.config  import prefs

        if not self._scan_results:
            return

        # Collect checked rows
        complete = self._scan_results['complete']
        selected = []
        for row in range(self.tbl_complete.rowCount()):
            chk = self.tbl_complete.item(row, 0)
            if chk and chk.checkState() == Qt.Checked:
                # rows may be sorted differently; match by series_name text
                series_cell = self.tbl_complete.item(row, 1)
                if series_cell:
                    name = series_cell.text()
                    for g in complete:
                        if g['series_name'] == name:
                            selected.append(g)
                            break

        if not selected:
            info_dialog(self, 'Nothing selected',
                        'Tick at least one series in the "Ready to Merge" tab.',
                        show=True, show_copy_button=False)
            return

        # Confirm
        reply = QMessageBox.question(
            self,
            'Confirm merge',
            f'Merge {len(selected)} series into anthology EPUBs?\n\n'
            f'This will add new books to your library.\n'
            + ('Source books will be kept.' if prefs['keep_source_books']
               else 'Source books will NOT be deleted (safe — only new books are created).'),
            QMessageBox.Yes | QMessageBox.Cancel,
        )
        if reply != QMessageBox.Yes:
            return

        epubmerge = self.plugin_action.get_epubmerge_plugin()
        if not epubmerge:
            error_dialog(self, 'EpubMerge not found',
                         'EpubMerge 1.3.1+ is required.', show=True)
            return

        self.btn_merge.setEnabled(False)
        self.btn_scan.setEnabled(False)
        self.progress.setRange(0, len(selected))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self._log_lines  = []
        self._merge_results = []
        QApplication.processEvents()

        db = self.plugin_action.gui.current_db

        for i, group in enumerate(selected):
            self.status_label.setText(
                f'Merging {i+1}/{len(selected)}: {group["series_name"]}…'
            )
            QApplication.processEvents()

            ok, new_bid, msg = merge_series_group(
                group, db, epubmerge, prefs, self._log_lines
            )
            self._merge_results.append((ok, new_bid, msg))
            status = '✅' if ok else '❌'
            self.log_edit.append(f'{status} {msg}')
            self.progress.setValue(i + 1)
            QApplication.processEvents()

        # ---- Write log file ------------------------------------------
        try:
            log_dir = prefs.get('log_dir', '') or ''
            self._log_path = write_log(
                self._log_lines,
                self._merge_results,
                self._scan_results.get('singletons', []),
                self._scan_results.get('incomplete', []),
                log_dir=log_dir,
            )
            self.log_edit.append(f'\n📄 Full log saved to:\n   {self._log_path}')
            self.btn_log.setEnabled(True)
        except Exception as exc:
            self.log_edit.append(f'⚠️  Could not write log file: {exc}')

        # ---- Refresh the Calibre GUI ----------------------------------
        try:
            self.plugin_action.gui.library_view.model().books_added(1)
            self.plugin_action.gui.iactions['Edit Metadata'].refresh_books_after_metadata_edit(
                set(), False
            )
        except Exception:
            pass
        try:
            self.plugin_action.gui.current_db.refresh()
            self.plugin_action.gui.library_view.model().refresh()
        except Exception:
            pass

        n_ok   = sum(1 for ok, _, _ in self._merge_results if ok)
        n_fail = len(self._merge_results) - n_ok
        self.status_label.setText(
            f'Done — {n_ok} merged successfully, {n_fail} failed.  '
            f'See log for details.'
        )
        self.progress.setVisible(False)
        self.btn_scan.setEnabled(True)
        if n_ok < len(selected):
            self.btn_merge.setEnabled(True)

    # ------------------------------------------------------------------
    # Slot: URL double-click opens browser
    # ------------------------------------------------------------------

    def _on_cell_double_click(self, row, col):
        sender = self.sender()
        item = sender.item(row, col)
        if isinstance(item, _UrlItem) and item.url:
            from PyQt5.Qt import QDesktopServices, QUrl
            QDesktopServices.openUrl(QUrl(item.url))

    # ------------------------------------------------------------------
    # Slot: checkbox helpers
    # ------------------------------------------------------------------

    def _on_select_all(self):
        for row in range(self.tbl_complete.rowCount()):
            chk = self.tbl_complete.item(row, 0)
            if chk:
                chk.setCheckState(Qt.Checked)

    def _on_deselect_all(self):
        for row in range(self.tbl_complete.rowCount()):
            chk = self.tbl_complete.item(row, 0)
            if chk:
                chk.setCheckState(Qt.Unchecked)

    # ------------------------------------------------------------------
    # Slot: open log file
    # ------------------------------------------------------------------

    def _on_open_log(self):
        if self._log_path and os.path.exists(self._log_path):
            from PyQt5.Qt import QDesktopServices, QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._log_path))
