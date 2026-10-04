"""PDF statements (banks, PhonePe, Google Pay, Paytm) -> rows of cells for csv_import.parse_rows.

PDFs have no table structure, only text at positions. The steps are:
  1. Read every character with its position (pdfminer.six, without its slow layout analysis), group
     characters into visual lines, and split each line wherever there's a gap wider than a space,
     so neighbouring columns don't merge. Horizontal rules drawn across the page are noted too.
  2. Find the header: one line, or up to three stacked lines ("Withdrawal" / "Amount" / "(INR)", with
     "S No." centred on the middle line), whose names include a date and an amount. The version that
     names the most columns wins. Each header cell's horizontal span defines a column.
  3. Group the lines under it into payments. When the table draws a rule between rows (most bank
     statements), everything between two rules is one payment, including a payee name printed above
     the date. Otherwise a line with a date in the date column starts a payment and the lines just
     under it (wrapped narration, the time under the date, "UTR No." under the name) are added to it.
     Repeated headers, summaries and footers have no date in the date column, so they're dropped.
Cells keep their line breaks ("\\n"); the first line of a narration is often the payee's name.
Password-protected PDFs (most bank e-statements) need the password; it's used only to open the file.
"""

import io
import time
from bisect import bisect_right

from .csv_import import is_header, map_header, parse_date

MAX_PAGES = 100
TIME_BUDGET = 40.0  # seconds; a PDF that takes longer is refused instead of tying up the server


class PdfPasswordError(ValueError):
    """The PDF is locked (or the password was wrong)."""


def _page_items(layout):
    """Characters and flat horizontal rules on a page (looking inside figures too)."""
    from pdfminer.layout import LTChar, LTCurve, LTFigure
    chars, rules = [], []
    stack = [layout]
    while stack:
        obj = stack.pop()
        for o in obj:
            if isinstance(o, LTChar):
                if o.upright and o.get_text().strip():
                    chars.append(o)
            elif isinstance(o, LTFigure):
                stack.append(o)
            elif isinstance(o, LTCurve) and o.height <= 2 and o.width >= 0.4 * layout.width:
                rules.append(layout.height - (o.y0 + o.y1) / 2)  # LTLine and LTRect are LTCurves
    return chars, rules


def _rows_of(chars, page_no, page_h):
    """Group characters into visual lines, then split each line into column segments."""
    chars.sort(key=lambda c: (page_h - c.y1, c.x0))
    lines, cur = [], []
    for c in chars:
        top = page_h - c.y1
        if cur and abs(top - cur[0][0]) > 0.5 * max(c.size, cur[0][1].size):
            lines.append(cur)
            cur = []
        cur.append((top, c))
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:
        ln.sort(key=lambda tc: tc[1].x0)
        segs, seg = [], None
        for top, c in ln:
            size = c.size or 8
            if seg is not None and c.x0 - seg["x1"] > 0.6 * size:
                segs.append(seg)
                seg = None
            if seg is None:
                seg = {"page": page_no, "x0": c.x0, "x1": c.x1, "top": top, "h": c.height or size, "text": ""}
            elif c.x0 - seg["x1"] > 0.15 * size:
                seg["text"] += " "  # a word gap with no space character drawn
            seg["text"] += c.get_text()
            seg["x1"] = max(seg["x1"], c.x1)
        if seg is not None:
            segs.append(seg)
        for s in segs:
            s["text"] = " ".join(s["text"].split())
        segs = [s for s in segs if s["text"]]
        if segs:
            out.append(segs)
    return out


def _read(data: bytes, password: str | None):
    from pdfminer.converter import PDFPageAggregator
    from pdfminer.pdfdocument import PDFDocument, PDFEncryptionError, PDFPasswordIncorrect
    from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
    from pdfminer.pdfpage import PDFPage
    from pdfminer.pdfparser import PDFParser, PDFSyntaxError
    from pdfminer.psparser import PSException

    lines, rules, start = [], {}, time.monotonic()
    try:
        doc = PDFDocument(PDFParser(io.BytesIO(data)), password=password or "")
        rsrc = PDFResourceManager()
        device = PDFPageAggregator(rsrc, laparams=None)  # raw characters: much faster than layout analysis
        interp = PDFPageInterpreter(rsrc, device)
        for page_no, page in enumerate(PDFPage.create_pages(doc)):
            if page_no >= MAX_PAGES:
                break
            if time.monotonic() - start > TIME_BUDGET:
                raise ValueError("This PDF is taking too long to read. Download a shorter period (fewer months) and try again.")
            interp.process_page(page)
            layout = device.get_result()
            chars, page_rules = _page_items(layout)
            lines.extend(_rows_of(chars, page_no, layout.height))
            rules[page_no] = sorted(set(round(r, 1) for r in page_rules))
    except PDFPasswordIncorrect as e:
        raise PdfPasswordError("Wrong password." if password else "This PDF is locked with a password.") from e
    except PDFEncryptionError as e:
        raise ValueError("This PDF uses a kind of encryption we can't open. Download it again without a password, or as Excel / CSV.") from e
    except (PDFSyntaxError, PSException) as e:
        raise ValueError("Couldn't read this PDF. Download it again, or use the Excel / CSV statement.") from e
    return lines, rules


def _stack(lines: list[list[dict]]) -> list[dict]:
    """Join a header printed over several lines: a cell that sits under another is appended to it."""
    cells = [dict(c) for c in lines[0]]
    for ln in lines[1:]:
        for s in ln:
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


def _find_header(lines):
    for i, ln in enumerate(lines[:400]):
        options = []
        for n in (1, 2, 3):  # the header may be printed over up to three lines
            group = lines[i:i + n]
            if len(group) < n or group[-1][0]["page"] != ln[0]["page"] or group[-1][0]["top"] - ln[0]["top"] > 4 * ln[0]["h"]:
                break
            cells = _stack(group)
            cols = map_header([c["text"] for c in cells])
            if is_header(cols):
                options.append((len(cols), -n, i + n - 1, cells, cols))
        if options:
            _, _, last, cells, cols = max(options, key=lambda o: (o[0], o[1]))
            return last, cells, cols
    raise ValueError("Couldn't find the table of payments in this PDF (no column names like Date and Amount). "
                     "Try the Excel / CSV statement instead.")


def pdf_rows(data: bytes, password: str | None, limit: int) -> list[list[str]]:
    lines, rules = _read(data, password)
    if not lines:
        raise ValueError("This PDF has no readable text (it may be a scanned picture). "
                         "Download the statement from your bank or app again, or as Excel / CSV.")
    head, cells, cols = _find_header(lines)
    date_col = cols["occurred_at"]
    rows = [[c["text"] for c in cells]]

    def place(ln):
        placed: dict[int, list[str]] = {}
        for s in ln:
            placed.setdefault(_column(s, cells), []).append(s["text"])
        return {k: " ".join(v) for k, v in placed.items()}

    def anchor(placed) -> bool:
        parts = placed.get(date_col, "")
        return bool(parts) and (_is_date(parts) or _is_date(parts.split(" ")[0]))

    def add(rec, placed):
        for col, text in placed.items():
            rec[col] = (rec[col] + "\n" + text) if rec[col] else text

    # Split the lines after the header into blocks between horizontal rules (one block per page when
    # the table draws none). In a ruled table a block is one payment; text above its date belongs to it.
    body = [(ln, place(ln)) for ln in lines[head + 1:]]
    anchors = sum(anchor(p) for _, p in body)
    ruled = sum(len(r) for r in rules.values()) >= max(3, anchors / 2)  # a rule between (most) rows
    blocks, key = [], None
    for ln, placed in body:
        page, top = ln[0]["page"], ln[0]["top"]
        k = (page, bisect_right(rules.get(page, []), top) if ruled else 0)
        if k != key:
            blocks.append([])
            key = k
        blocks[-1].append((ln, placed))

    for block in blocks:
        cur, prev, pending = None, None, []
        for ln, placed in block:
            if is_header(map_header(list(placed.values()))):
                cur, pending = None, []  # header repeated on a new page
            elif anchor(placed):
                cur = [""] * len(cells)
                rows.append(cur)
                if ruled:
                    for p in pending:  # e.g. the payee name printed above the date
                        add(cur, p)
                pending = []
                add(cur, placed)
            elif cur is not None and (ruled or (ln[0]["top"] - prev[0]["top"] <= 2.6 * max(s["h"] for s in ln))):
                add(cur, placed)
            elif cur is None:
                pending.append(placed)
            else:
                cur = None  # summary lines, footers, page numbers
            prev = ln
            if len(rows) > limit:
                return rows
    return rows
