# -*- coding: utf-8 -*-
"""
merger.py — Calls EpubMerge's do_merge() and adds the result to the library.

Mirrors the exact call pattern from fff_plugin.py's do_merge_anthology()
(lines ~2230–2247) so all EpubMerge user-preferences are honoured by default,
while we pass our own cover / title / tag overrides. Also respects FFF's 
metadata merging logic for standard fields (dates, authors, publisher).
"""

import os
import logging
from datetime import datetime

from calibre.ptempfile import PersistentTemporaryFile, PersistentTemporaryDirectory
from calibre.ebooks.metadata.book.base import Metadata

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def merge_series_group(group, db, epubmerge_plugin, plugin_prefs, log_lines):
    """
    Merge one series group.

    Parameters
    ----------
    group          : dict produced by scanner.scan_library()
    db             : gui.current_db   (old Calibre API)
    epubmerge_plugin : the live EpubMerge InterfaceAction object
    plugin_prefs   : the SeriesMerge JSONConfig prefs object
    log_lines      : list to append human-readable log strings to

    Returns
    -------
    (success: bool, new_book_id: int or None, message: str)
    """
    series_name = group['series_name']
    authors     = group['authors']
    books       = group['books']   # [(float_index, book_id)] sorted

    log_lines.append(f'\n=== Merging: "{series_name}" by {", ".join(authors)} ===')
    log_lines.append(f'    Books ({len(books)}): ' +
                     ', '.join(f'[{int(round(idx))}] id={bid}' for idx, bid in books))

    tdir = PersistentTemporaryDirectory(prefix='series_merge_')
    try:
        # ---- Collect EPUB paths -----------------------------------------
        epub_paths = []
        for idx, bid in books:
            fmt_path = db.format_abspath(bid, 'EPUB', index_is_id=True)
            if not fmt_path or not os.path.exists(fmt_path):
                msg = f'    ERROR: EPUB not found for book_id={bid} (index {int(round(idx))})'
                log_lines.append(msg)
                return False, None, msg
            epub_paths.append(fmt_path)

        # ---- Cover: use calibre cover of first book, then sub-book covers -
        cover_path = None

        # 1. Try the Calibre-stored cover of the first book
        first_bid = books[0][1]
        cal_cover = os.path.join(
            db.library_path,
            db.path(first_bid, index_is_id=True),
            'cover.jpg',
        )
        if os.path.exists(cal_cover):
            cover_path = cal_cover
        else:
            # 2. Try raw cover bytes from the DB
            cover_bytes = db.cover(first_bid, index_is_id=True, as_image=False)
            if cover_bytes:
                tmp_cover = PersistentTemporaryFile(suffix='.jpg', dir=tdir)
                tmp_cover.write(cover_bytes)
                tmp_cover.close()
                cover_path = tmp_cover.name

        # ---- Tags: union of all source books + optional anthology tag -----
        all_tags = set()
        for _, bid in books:
            raw = db.tags(bid, index_is_id=True) or ''
            all_tags.update(t.strip() for t in raw.split(',') if t.strip())
        
        if plugin_prefs.get('add_anthology_tag') and plugin_prefs.get('anthology_tag'):
            all_tags.add(plugin_prefs['anthology_tag'])
            
        # Apply EpubMerge's 'mergetags' preference
        mergetags_pref = plugin_prefs.get('mergetags', '') 
        if mergetags_pref:
            all_tags.update(t.strip() for t in mergetags_pref.split(',') if t.strip())

        # Remove status tags that don't apply to the anthology
        for drop in ('Completed', 'In-Progress'):
            all_tags.discard(drop)

        # ---- Title --------------------------------------------------------
        if plugin_prefs.get('use_series_name_title', True):
            title = series_name
        else:
            title = db.title(first_bid, index_is_id=True) or series_name

        # ---- URL / source -------------------------------------------------
        source_url = group.get('url', '')

        # ---- Generate Combined Comments -----------------------------------
        combined_comments = _build_anthology_comments(
            series_name=series_name, 
            books=books, 
            authors=authors, 
            db=db, 
            includecomments=plugin_prefs.get('includecomments', True),
            mergeword=plugin_prefs.get('mergeword', 'Anthology')
        )

        # ---- Temp output file ---------------------------------------------
        tmp_out = PersistentTemporaryFile(suffix='.epub', dir=tdir)
        tmp_out.close()
        outfile = tmp_out.name

        # ---- Build EpubMerge call -----------------------------------------
        mrg_args   = [outfile, epub_paths]
        mrg_kwargs = dict(
            tags              = sorted(all_tags),
            titleopt          = title,
            descopt           = combined_comments, 
            keepmetadatafiles = bool(plugin_prefs.get('keepmetadatafiles', True)),
            source            = source_url,
            coverjpgpath      = cover_path,
        )

        em_ver = epubmerge_plugin.interface_action_base_plugin.version
        if em_ver >= (2, 15, 3):
            mrg_kwargs['keepsingletocs'] = False   # sensible default for clean TOC

        log.debug('SeriesMerge do_merge args: %s kwargs_keys: %s',
                  [outfile, f'[{len(epub_paths)} files]'],
                  list(mrg_kwargs.keys()))

        epubmerge_plugin.do_merge(*mrg_args, **mrg_kwargs)

        if not os.path.exists(outfile) or os.path.getsize(outfile) == 0:
            msg = '    ERROR: EpubMerge produced an empty or missing output file.'
            log_lines.append(msg)
            return False, None, msg

        # ---- Add merged book to library & Merge Metadata ------------------
        # Build base Metadata from the first book, then calculate the rest
        mi = db.get_metadata(first_bid, index_is_id=True, get_cover=False)

        # 1. Aggregate Authors safely (preserving order, no duplicates)
        all_authors = []
        
        # 2. Setup variables for date and publisher aggregation
        min_pubdate = mi.pubdate
        max_timestamp = mi.timestamp
        publisher = mi.publisher
        pub_conflict = False

        # 3. Iterate through all books for dates, publishers, and authors
        for _, bid in books:
            b_mi = db.get_metadata(bid, index_is_id=True, get_cover=False)
            
            # Authors
            for a in (b_mi.authors or []):
                if a not in all_authors:
                    all_authors.append(a)

            # Dates (Earliest published, latest timestamp)
            if b_mi.pubdate:
                if not min_pubdate or b_mi.pubdate < min_pubdate:
                    min_pubdate = b_mi.pubdate
            if b_mi.timestamp:
                if not max_timestamp or b_mi.timestamp > max_timestamp:
                    max_timestamp = b_mi.timestamp

            # Publisher (Keep if consistent, drop if conflicting)
            if b_mi.publisher:
                if not publisher:
                    publisher = b_mi.publisher
                elif publisher != b_mi.publisher:
                    pub_conflict = True

        # 4. Apply the calculated metadata to the final object
        mi.title = title
        mi.authors = all_authors
        mi.tags = sorted(all_tags)
        mi.pubdate = min_pubdate
        mi.timestamp = max_timestamp
        mi.publisher = None if pub_conflict else publisher

        # EXPLICITLY REMOVE SERIES
        mi.series = None
        mi.series_index = None

        if source_url:
            mi.set_identifier('url', source_url)
            
        # Assign the generated comments to the Calibre DB metadata entry
        mi.comments = combined_comments 

        # add_books returns ([book_ids], [duplicate_ids])
        result  = db.add_books([outfile], ['epub'], [mi])
        new_ids = result[0] if result else []
        if not new_ids:
            msg = '    ERROR: db.add_books() returned no IDs.'
            log_lines.append(msg)
            return False, None, msg
        new_bid = new_ids[0]

        log_lines.append(f'    SUCCESS → new book_id={new_bid}, title="{title}"')

        # ---- Optionally mark source books ---------------------------------
        if plugin_prefs.get('mark_source_books') and plugin_prefs.get('source_mark_tag'):
            mark_tag = plugin_prefs['source_mark_tag']
            for _, bid in books:
                existing = set(
                    t.strip()
                    for t in (db.tags(bid, index_is_id=True) or '').split(',')
                    if t.strip()
                )
                existing.add(mark_tag)
                db.set_tags(bid, list(existing), index_is_id=True)
            log_lines.append(f'    Tagged {len(books)} source books with "{mark_tag}"')

        return True, new_bid, f'Merged {len(books)} books → "{title}"'

    except Exception as exc:
        import traceback
        msg = f'    EXCEPTION: {exc}'
        log_lines.append(msg)
        log_lines.append(traceback.format_exc())
        log.exception('SeriesMerge merge_series_group failed for "%s"', series_name)
        return False, None, str(exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_anthology_comments(series_name, books, authors, db, includecomments=True, mergeword='Anthology'):
    """Build a combined HTML description mimicking EpubMerge's native behavior."""
    
    # If there are multiple authors across the merge, include the author in the sub-book title
    if len(authors) > 1:
        booktitle = lambda t, a: f"{t} by {' & '.join(a)}"
    else:
        booktitle = lambda t, a: t

    comments_html = f"<p>{mergeword} containing:</p>"

    # Collect metadata for each book
    book_list = []
    for idx, bid in books:
        t = db.title(bid, index_is_id=True) or f'Book {int(round(idx))}'
        a = db.authors(bid, index_is_id=True) or []
        c = db.comments(bid, index_is_id=True) or ''
        book_list.append({'title': t, 'authors': a, 'comments': c})

    # Stitch comments together just like EpubMerge
    if includecomments:
        def bookcomments(x):
            bt = booktitle(x['title'], x['authors'])
            if x['comments']:
                return f"<p><b>{bt}</b></p>{x['comments']}"
            else:
                return f"<b>{bt}</b><br/>"

        comments_html += ('<div class="mergedbook">' +
                          '<hr></div><div class="mergedbook">'.join([bookcomments(x) for x in book_list]) +
                          '</div>')
    else:
        comments_html += '<br/>'.join([booktitle(x['title'], x['authors']) for x in book_list])

    return comments_html


# ---------------------------------------------------------------------------
# Log file writer
# ---------------------------------------------------------------------------

def write_log(log_lines, results, singletons, incomplete, log_dir=''):
    """
    Write a human-readable log file.

    Returns the path to the written log file.
    """
    from calibre.constants import config_dir
    if not log_dir:
        log_dir = os.path.join(config_dir, 'plugins')
    os.makedirs(log_dir, exist_ok=True)

    stamp    = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    log_path = os.path.join(log_dir, f'SeriesMerge_{stamp}.log')

    with open(log_path, 'w', encoding='utf-8') as f:
        f.write(f'SeriesMerge log — {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write('=' * 70 + '\n\n')

        # ---- Merge results ------------------------------------------------
        f.write('MERGED SERIES\n')
        f.write('-' * 40 + '\n')
        if results:
            for ok, new_bid, msg in results:
                status = 'OK  ' if ok else 'FAIL'
                f.write(f'[{status}] {msg}\n')
        else:
            f.write('(none merged this session)\n')
        f.write('\n')

        # ---- Singletons (only index 1 — confirm complete) -----------------
        f.write('SINGLETON SERIES — confirm complete (only book #1 found)\n')
        f.write('-' * 40 + '\n')
        if singletons:
            for g in singletons:
                name = g['series_name']
                auth = ', '.join(g['authors'])
                url  = g['url'] or '(no URL)'
                f.write(f'  Series : {name}\n')
                f.write(f'  Author : {auth}\n')
                f.write(f'  URL    : {url}\n\n')
        else:
            f.write('(none)\n')
        f.write('\n')

        # ---- Incomplete ---------------------------------------------------
        f.write('INCOMPLETE SERIES — missing books\n')
        f.write('-' * 40 + '\n')
        if incomplete:
            for g in incomplete:
                name    = g['series_name']
                auth    = ', '.join(g['authors'])
                url     = g['url'] or '(no URL)'
                missing = ', '.join(str(m) for m in g['missing'])
                reason  = g.get('skip_reason') or ''
                f.write(f'  Series  : {name}\n')
                f.write(f'  Author  : {auth}\n')
                f.write(f'  Missing : {missing}\n')
                f.write(f'  URL     : {url}\n')
                if reason:
                    f.write(f'  Note    : {reason}\n')
                f.write('\n')
        else:
            f.write('(none)\n')

        # ---- Full merge log -----------------------------------------------
        if log_lines:
            f.write('\nDETAILED MERGE LOG\n')
            f.write('-' * 40 + '\n')
            f.write('\n'.join(log_lines))

    return log_path