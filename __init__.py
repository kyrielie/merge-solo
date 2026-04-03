# -*- coding: utf-8 -*-
# SeriesMerge Calibre Plugin
# Automatically merges sequential series EPUBs via EpubMerge

from calibre.customize import InterfaceActionBase

__license__   = 'GPL v3'
__docformat__ = 'restructuredtext en'


class SeriesMergePlugin(InterfaceActionBase):
    name                    = 'SeriesMerge'
    description             = ('Scans your Calibre library and merges EPUBs that belong to '
                                "the same author's series with sequential indices (1, 2, 3…). "
                                'Logs incomplete series and singletons for review.')
    supported_platforms     = ['windows', 'osx', 'linux']
    author                  = 'Custom'
    version                 = (1, 0, 0)
    minimum_calibre_version = (5, 0, 0)

    # actual_plugin uses the calibre_plugins.<import-name>.<module>:<class> form.
    # Calibre synthesises the calibre_plugins.series_merge namespace from
    # plugin-import-name-series_merge.txt, so all sibling .py files are
    # reachable as calibre_plugins.series_merge.<module>.
    actual_plugin = 'calibre_plugins.series_merge.main:SeriesMergeAction'

    def is_customizable(self):
        return True

    def config_widget(self):
        # Deferred import so GUI libs aren't loaded on the command line
        from calibre_plugins.series_merge.config import ConfigWidget
        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.commit()
