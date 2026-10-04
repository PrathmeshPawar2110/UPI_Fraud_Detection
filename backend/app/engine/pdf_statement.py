"""PDF statements (banks, PhonePe, Google Pay, Paytm) -> rows of cells for csv_import.parse_rows.

PDFs have no table structure, only text at positions. The steps are:
  1. Read every character with its position (pdfminer.six) and split each text line into
     segments wherever there's a gap wider than a space, so neighbouring columns don't merge.
  2. Group segments into visual lines (same page, same height on the page).
  3. Find the header: a line, or two stacked lines ("Withdrawal" over "Amt."), whose names
     include a date and an amount. Each header cell's horizontal span defines a column.
  4. A line with a date in the date column starts a payment; the lines just under it (wrapped
     narration, the time under the date, "UTR No." under the name) are added to the same cells.
     Repeated headers on later pages are skipped; footers are too far below to be attached.
Password-protected PDFs (most bank e-statements) need the password; it's used only to open the file.
"""

import io
import re
import time

from .csv_import import is_header, map_header, parse_date

MAX_PAGES = 100
TIME_BUDGET = 25.0  # seconds; a PDF that takes longer is refused instead of tying up the server


class PdfPasswordError(ValueError):
    """The PDF is locked (or the password was wrong)."""


def _segments(line, page_no, page_h):
    """Split one pdfminer text line into column pieces at gaps wider than ~0.6 em."""
    from pdfminer.layout import LTChar
    out, cur = [], None
    for ch in line:
        if not isinstance(ch, LTChar):
            if cur is not None:
                cur["text"] += ch.get_text()  # LTAnno: a space pdfminer inferred inside a word gap
            continue
        size = ch.size or 8
        if cur is not None and ch.x0 - cur["x1"] > 0.6 * size:
            out.append(cur)
            cur = None
        if cur is None:
            cur = {"page": page_no, "x0": ch.x0, "x1": ch.x1, "top": page_h - ch.y1, "h": ch.height or size, "text": ""}
        cur["text"] += ch.get_text()
        cur["x1"] = max(cur["x1"], ch.x1)
    if cur is not None:
        out.append(cur)
    for s in out:
        s["text"] = re.sub(r"\s+", " ", s["text"]).strip()
    return [s for s in out if s["text"]]


def _walk(obj):
    from pdfminer.layout import LTTextLineHorizontal
    if isinstance(obj, LTTextLineHorizontal):
        yield obj
        return
    if hasattr(obj, "__iter__"):
        for child in obj:
            yield from _walk(child)


def _lines(data: bytes, password: str | None) -> list[list[dict]]:
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams
    from pdfminer.pdfdocument import PDFEncryptionError, PDFPasswordIncorrect
    from pdfminer.pdfparser import PDFSyntaxError
    from pdfminer.psparser import PSException

    segs, start = [], time.monotonic()
    params = LAParams(char_margin=1.0, word_margin=0.1, line_margin=0.3, boxes_flow=None)
    try:
        for page_no, page in enumerate(extract_pages(io.BytesIO(data), password=password or "",
                                                     laparams=params, maxpages=MAX_PAGES)):
            if time.monotonic() - start > TIME_BUDGET:
                raise ValueError("This PDF is taking too long to read. Download a shorter period (fewer months) and try again.")
            for line in _walk(page):
                segs.extend(_segments(line, page_no, page.height))
    except PDFPasswordIncorrect as e:
        raise PdfPasswordError("Wrong password." if password else "This PDF is locked with a password.") from e
    except PDFEncryptionError as e:
        raise ValueError("This PDF uses a kind of encryption we can't open. Download it again without a password, or as Excel / CSV.") from e
    except (PDFSyntaxError, PSException) as e:
        raise ValueError("Couldn't read this PDF. Download it again, or use the Excel / CSV statement.") from e

    # group into visual lines: same page, tops within half a line height
    segs.sort(key=lambda s: (s["page"], s["top"], s["x0"]))
    lines: list[list[dict]] = []
    for s in segs:
        last = lines[-1] if lines else None
        if last and last[0]["page"] == s["page"] and abs(last[0]["top"] - s["top"]) < 0.5 * max(s["h"], last[0]["h"]):
            last.append(s)
        else:
            lines.append([s])
    for ln in lines:
        ln.sort(key=lambda s: s["x0"])
    return lines


def _stack(upper: list[dict], lower: list[dict]) -> list[dict]:
    """Join a two-line header: lower cells that sit under an upper cell are appended to it."""
    cells = [dict(c) for c in upper]
    for s in lower:
        over = [c for c in cells if min(c["x1"], s["x1"]) - max(c["x0"], s["x0"]) > 0]
        if over:
            c = over[0]
            c["text"] += " " + s["text"]
            c["x0"], c["x1"] = min(c["x0"], s["x0"]), max(c["x1"], s["x1"])
        else:
            cells.append(dict(s))
    return sorted(cells, key=lambda c: c["x0"])


def _column(seg: dict, cells: list[dict]) -> int:
    """The header cell this segment sits under: most horizontal overlap, else the nearest centre."""
    best, best_overlap = None, 0.0
    for i, c in enumerate(cells):
        ov = min(c["x1"], seg["x1"]) - max(c["x0"], seg["x0"])
        if ov > best_overlap:
            best, best_overlap = i, ov
    if best is not None:
        return best
    mid = (seg["x0"] + seg["x1"]) / 2
    return min(range(len(cells)), key=lambda i: abs((cells[i]["x0"] + cells[i]["x1"]) / 2 - mid))


def _is_date(text: str) -> bool:
    try:
        parse_date(text)
        return True
    except ValueError:
        return False


def pdf_rows(data: bytes, password: str | None, limit: int) -> list[list[str]]:
    lines = _lines(data, password)
    if not lines:
        raise ValueError("This PDF has no readable text (it may be a scanned picture). "
                         "Download the statement from your bank or app again, or as Excel / CSV.")
    header = None
    for i, ln in enumerate(lines[:200]):
        options = []
        for skip, cells in ((0, ln), (1, _stack(ln, lines[i + 1]) if i + 1 < len(lines) else None)):
            if cells and is_header(cols := map_header([c["text"] for c in cells])):
                options.append((len(cols), skip, cells, cols))
        if options:  # a two-line header ("Closing" over "Balance") wins if it names more columns
            _, skip, cells, cols = max(options, key=lambda o: o[0])
            header = (i + skip, cells, cols)
            break
    if not header:
        raise ValueError("Couldn't find the table of payments in this PDF (no column names like Date and Amount). "
                         "Try the Excel / CSV statement instead.")
    start, cells, cols = header
    names = [c["text"] for c in cells]
    date_col = cols["occurred_at"]

    rows, cur, prev = [names], None, None
    for ln in lines[start + 1:]:
        texts = [s["text"] for s in ln]
        if is_header(map_header(texts)):
            cur = None  # header repeated on a new page
            prev = ln
            continue
        placed: dict[int, list[str]] = {}
        for s in ln:
            placed.setdefault(_column(s, cells), []).append(s["text"])
        date_parts = placed.get(date_col, [])
        top, h = ln[0]["top"], max(s["h"] for s in ln)
        if date_parts and (_is_date(" ".join(date_parts)) or _is_date(date_parts[0])):
            cur = [""] * len(cells)
            rows.append(cur)
        elif cur is None or prev is None or ln[0]["page"] != prev[0]["page"] or top - prev[0]["top"] > 2.6 * h:
            cur = None  # summary lines, footers, page numbers
            prev = ln
            continue
        for col, parts in placed.items():
            cur[col] = (cur[col] + " " + " ".join(parts)).strip()
        prev = ln
        if len(rows) >= limit:
            break
    return rows
