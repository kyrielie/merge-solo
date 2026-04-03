# -*- coding: utf-8 -*-
"""
Persistent preferences for SeriesMerge, stored in Calibre's config directory.
Also contains the ConfigWidget shown in Calibre's Preferences ▸ Plugins dialog.
"""

from calibre.utils.config import JSONConfig
from PyQt5.Qt import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
                      QLineEdit, QGroupBox, QFormLayout, QSpinBox, QComboBox)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
prefs = JSONConfig('plugins/series_merge')

prefs.defaults['merged_series_index']    = 0.0   # series_index for the new anthology book
prefs.defaults['add_anthology_tag']      = True   # add "Anthology" tag to merged book
prefs.defaults['anthology_tag']          = 'Anthology'
prefs.defaults['keep_source_books']      = True   # don't delete originals after merge
prefs.defaults['mark_source_books']      = True   # mark source books with a visual tag
prefs.defaults['source_mark_tag']        = 'Merged into Anthology'
prefs.defaults['keepmetadatafiles']      = True   # pass to EpubMerge
prefs.defaults['use_series_name_title']  = True   # title of merged book = series name
prefs.defaults['log_dir']               = ''      # empty = calibre config dir
prefs.defaults['index_tolerance']        = 0.01   # float tolerance for "is this a whole number"
prefs.defaults['require_epub_for_all']   = True   # skip series if ANY book lacks EPUB format


# ---------------------------------------------------------------------------
# Config widget
# ---------------------------------------------------------------------------
class ConfigWidget(QWidget):

    def __init__(self):
        QWidget.__init__(self)
        layout = QVBoxLayout()
        self.setLayout(layout)

        # --- Merge behaviour ---
        merge_group = QGroupBox('Merge behaviour')
        merge_form  = QFormLayout()
        merge_group.setLayout(merge_form)

        self.cb_keep_sources = QCheckBox('Keep original books after merging')
        self.cb_keep_sources.setChecked(prefs['keep_source_books'])
        merge_form.addRow(self.cb_keep_sources)

        self.cb_mark_sources = QCheckBox('Tag source books as merged')
        self.cb_mark_sources.setChecked(prefs['mark_source_books'])
        merge_form.addRow(self.cb_mark_sources)

        self.le_mark_tag = QLineEdit(prefs['source_mark_tag'])
        merge_form.addRow(QLabel('  Tag text:'), self.le_mark_tag)

        self.cb_keepmeta = QCheckBox('Keep per-book metadata files inside merged EPUB '
                                     '(keepmetadatafiles — passed to EpubMerge)')
        self.cb_keepmeta.setChecked(prefs['keepmetadatafiles'])
        merge_form.addRow(self.cb_keepmeta)

        layout.addWidget(merge_group)

        # --- Anthology book metadata ---
        meta_group = QGroupBox('Merged (anthology) book metadata')
        meta_form  = QFormLayout()
        meta_group.setLayout(meta_form)

        self.cb_use_series_title = QCheckBox('Use series name as merged book title')
        self.cb_use_series_title.setChecked(prefs['use_series_name_title'])
        meta_form.addRow(self.cb_use_series_title)

        self.sb_series_index = QSpinBox()
        self.sb_series_index.setRange(-99, 99)
        self.sb_series_index.setValue(int(prefs['merged_series_index']))
        meta_form.addRow(QLabel('Series index for merged book:'), self.sb_series_index)

        self.cb_add_anth_tag = QCheckBox('Add anthology tag to merged book')
        self.cb_add_anth_tag.setChecked(prefs['add_anthology_tag'])
        meta_form.addRow(self.cb_add_anth_tag)

        self.le_anth_tag = QLineEdit(prefs['anthology_tag'])
        meta_form.addRow(QLabel('  Anthology tag text:'), self.le_anth_tag)

        layout.addWidget(meta_group)

        # --- Scan / safety options ---
        scan_group = QGroupBox('Scan options')
        scan_form  = QFormLayout()
        scan_group.setLayout(scan_form)

        self.cb_require_epub = QCheckBox('Skip series where ANY book is missing an EPUB format')
        self.cb_require_epub.setChecked(prefs['require_epub_for_all'])
        scan_form.addRow(self.cb_require_epub)

        layout.addWidget(scan_group)
        layout.addStretch()

    def commit(self):
        prefs['keep_source_books']    = self.cb_keep_sources.isChecked()
        prefs['mark_source_books']    = self.cb_mark_sources.isChecked()
        prefs['source_mark_tag']      = self.le_mark_tag.text().strip()
        prefs['keepmetadatafiles']    = self.cb_keepmeta.isChecked()
        prefs['use_series_name_title']= self.cb_use_series_title.isChecked()
        prefs['merged_series_index']  = float(self.sb_series_index.value())
        prefs['add_anthology_tag']    = self.cb_add_anth_tag.isChecked()
        prefs['anthology_tag']        = self.le_anth_tag.text().strip()
        prefs['require_epub_for_all'] = self.cb_require_epub.isChecked()
