# -*- coding: utf-8 -*-
"""
scanner.py — Library analysis logic, completely GUI-free.

Produces three buckets:
  complete    — sequential 1..N (N > 1), all EPUBs present   → merge candidates
  singletons  — exactly one book with index 1                 → log for confirmation
  incomplete  — gaps in the index sequence                    → log missing indices
"""

from collections import defaultdict
import logging

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes (plain dicts kept for simplicity / Calibre compat)
# ---------------------------------------------------------------------------

def _series_url(db, book_ids):
    """
    Best-effort: return the URL identifier from the first book that has one.
    FanFicFare stores 'url' in identifiers; other tools may use 'uri'.
    Falls back to an empty string if nothing is found.
    """
    for bid in book_ids:
        try:
            idents = db.get_identifiers(bid, index_is_id=True) or {}
            for key in ('url', 'uri', 'webpage'):
                if key in idents and idents[key]:
                    return idents[key]
        except Exception:
            pass
    return ''


def _is_whole(f, tol=0.01):
    """Return True if *f* is within *tol* of a whole number."""
    return abs(f - round(f)) < tol


def scan_library(db, tol=0.01, require_epub=True):
    """
    Scan *db* (old Calibre LibraryDatabase API, i.e. gui.current_db).

    Returns a dict with three keys:
        'complete'   : list of SeriesGroup (ready to merge)
        'singletons' : list of SeriesGroup (only book 1)
        'incomplete' : list of SeriesGroup (gaps detected)

    SeriesGroup is a dict:
        series_name  : str
        authors      : tuple of str
        books        : list of (int index, int book_id), sorted by index
        url          : str  (best URL found across all books in the series)
        missing      : list of int   (only for incomplete groups)
        skip_reason  : str or None   (why this group was skipped)
    """
    complete   = []
    singletons = []
    incomplete = []

    # ---- Gather all book IDs that have a series set -----------------------
    try:
        # new_api search; fall back to iterating all IDs
        matching_ids = set(db.new_api.search('series:true'))
    except Exception:
        matching_ids = set()
        for bid in db.all_ids():
            try:
                if db.series(bid, index_is_id=True):
                    matching_ids.add(bid)
            except Exception:
                pass

    log.debug('SeriesMerge scanner: %d books with series metadata', len(matching_ids))

    # ---- Group by (authors_key, series_name) ------------------------------
    groups = defaultdict(list)   # key → [(series_index_float, book_id)]

    for bid in matching_ids:
        try:
            series_name = db.series(bid, index_is_id=True)
            if not series_name:
                continue
            series_idx = db.series_index(bid, index_is_id=True)
            if series_idx is None:
                continue

            # Author key: sorted tuple of individual author names
            raw_authors = db.authors(bid, index_is_id=True) or ''
            # Calibre stores authors as "Last, First & Last2, First2" — split on &
            author_list = tuple(sorted(
                a.strip() for a in raw_authors.replace(' & ', '&').split('&')
                if a.strip()
            ))
            key = (author_list, series_name)
            groups[key].append((float(series_idx), bid))
        except Exception as exc:
            log.warning('SeriesMerge scanner: error reading book %s: %s', bid, exc)

    # ---- Classify each group ----------------------------------------------
    for (authors, series_name), raw_books in groups.items():
        raw_books.sort(key=lambda x: x[0])

        url = _series_url(db, [bid for _, bid in raw_books])

        # Filter to whole-number indices only (skip .5 interstitials etc.)
        whole_books = [(idx, bid) for idx, bid in raw_books if _is_whole(idx, tol)]
        int_indices = [int(round(idx)) for idx, _ in whole_books]

        # Check EPUB availability
        skip_reason = None
        if require_epub:
            missing_epub = []
            for _, bid in whole_books:
                try:
                    fmts = [f.upper() for f in (db.formats(bid, index_is_id=True) or [])]
                    if 'EPUB' not in fmts:
                        missing_epub.append(bid)
                except Exception:
                    missing_epub.append(bid)
            if missing_epub:
                skip_reason = (
                    f'{len(missing_epub)} book(s) lack EPUB format'
                )

        group = dict(
            series_name  = series_name,
            authors      = authors,
            books        = whole_books,           # [(int_idx_as_float, book_id)]
            url          = url,
            missing      = [],
            skip_reason  = skip_reason,
        )

        if not int_indices:
            # nothing with whole-number indices — treat as incomplete
            group['missing'] = ['(no whole-number indices found)']
            incomplete.append(group)
            continue

        if int_indices == [1]:
            singletons.append(group)
            continue

        # Determine expected sequential range 1..max
        max_idx   = max(int_indices)
        expected  = list(range(1, max_idx + 1))
        idx_set   = set(int_indices)
        missing   = [i for i in expected if i not in idx_set]

        if missing:
            group['missing'] = missing
            incomplete.append(group)
        else:
            # Indices are exactly 1..N  ✓
            complete.append(group)

    log.info(
        'SeriesMerge scan complete: %d mergeable, %d singletons, %d incomplete',
        len(complete), len(singletons), len(incomplete),
    )
    return dict(complete=complete, singletons=singletons, incomplete=incomplete)
