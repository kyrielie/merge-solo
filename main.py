# -*- coding: utf-8 -*-
"""
main.py — SeriesMergeAction, the InterfaceAction that Calibre loads.

Design notes
------------
• We chose an InterfaceAction (custom GUI plugin) over Action Chains because:
    - We need full access to the live DB API (search, metadata read/write,
      format paths, add_books) across an arbitrary number of books.
    - We call EpubMerge's do_merge() directly, exactly as FanFicFare does,
      so we inherit all of EpubMerge's own stored preferences automatically.
    - Action Chains is great for simple single-book workflows triggered from
      the book list; it can't scan the whole library, aggregate series data,
      or make conditional decisions across groups of books.

• The plugin is intentionally self-contained (no extra pip packages).
• EpubMerge version gate mirrors FanFicFare: require >= 1.3.1.
"""

import logging

from calibre.gui2.actions import InterfaceAction

log = logging.getLogger(__name__)


class SeriesMergeAction(InterfaceAction):

    name = 'SeriesMerge'

    # Toolbar button spec: (text, icon, tooltip, keyboard shortcut)
    action_spec = (
        'Series Merge',
        None,
        'Scan library and merge sequential series EPUBs via EpubMerge',
        (),   # empty tuple = allow shortcut assignment, none pre-set
    )

    action_type = 'global'

    def genesis(self):
        """Called once when Calibre loads the plugin."""
        # Use a stock Calibre icon; replace with a custom one if desired by
        # placing images/icon.png inside the ZIP.
        try:
            icon = self.get_resources('images/icon.png')
            if icon:
                from calibre.gui2 import choose_images
                from PyQt5.Qt import QIcon, QPixmap
                pm = QPixmap()
                pm.loadFromData(icon)
                self.qaction.setIcon(QIcon(pm))
        except Exception:
            pass   # no icon is fine

        self.qaction.triggered.connect(self._open_dialog)

    def initialization_complete(self):
        pass

    # ------------------------------------------------------------------
    # Public helper — used by dialogs.py
    # ------------------------------------------------------------------

    def get_epubmerge_plugin(self):
        """Return the live EpubMerge plugin object, or None."""
        if 'EpubMerge' in self.gui.iactions:
            plugin = self.gui.iactions['EpubMerge']
            if plugin.interface_action_base_plugin.version >= (1, 3, 1):
                return plugin
        return None

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def _open_dialog(self):
        from calibre_plugins.series_merge.dialogs import MainDialog
        d = MainDialog(self.gui, self)
        d.exec_()
