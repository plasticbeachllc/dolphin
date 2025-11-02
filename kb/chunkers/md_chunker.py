from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple
import logging
import re
import bisect

from markdown_it import MarkdownIt
from markdown_it.token import Token
import yaml

from .token_utils import get_tokenizer, window_text_by_tokens, count_tokens
from .types import Chunk
from ..hashing import canonicalize_text


_log = logging.getLogger(__name__)


@dataclass(slots=True)
class _Section:
    """A logical Markdown section bounded by headings.

    Content excludes the heading line(s) (ATX or Setext) and front matter.
    start_line/end_line refer to the full section span in the original file,
    but content_start_line/content_end_line refer to the actual content lines
    that will be embedded (heading lines removed).
    """

    # Nearest headings to attach as metadata (None if absent)
    h1: Optional[str]
    h2: Optional[str]
    h3: Optional[str]

    # Section span in 1-based line numbers (inclusive)
    start_line: int
    end_line: int

    # Content slice (text and its starting line number)
    content_text: str
    content_start_line: int


def chunk_markdown(
    text: str,
    *,
    model: str = "small",
    token_target: int = 400,
    overlap_pct: float = 0.10,
) -> List[Chunk]:
    """Chunk a Markdown document into token-sized windows with heading metadata."""
    canonical = canonicalize_text(text)
    lines = canonical.splitlines(keepends=True)

    fm_offset, fm_title = _consume_front_matter_if_any(lines)

    # Scan sections on the slice after front matter, then adjust line numbers by fm_offset
    sections = list(_scan_sections(lines[fm_offset:], initial_h1=fm_title))
    if fm_offset:
        adjusted: List[_Section] = []
        for s in sections:
            adjusted.append(
                _Section(
                    h1=s.h1,
                    h2=s.h2,
                    h3=s.h3,
                    start_line=s.start_line + fm_offset,
                    end_line=s.end_line + fm_offset,
                    content_text=s.content_text,
                    content_start_line=s.content_start_line + fm_offset,
                )
            )
        sections = adjusted

    chunks: List[Chunk] = []
    overlap = max(0, int(token_target * overlap_pct))
    tok = get_tokenizer(model)

    for section in sections:
        if not section.content_text.strip():
            continue
        windows = window_text_by_tokens(
            section.content_text, model=model, target=token_target, overlap=overlap
        )

        # Build line-start offsets once per section
        line_offsets: List[int] = [0]
        for idx, ch in enumerate(section.content_text):
            if ch == "\n":
                line_offsets.append(idx + 1)

        for raw_text, start_char, end_char in windows:
            # Map char offsets to 1-based line numbers using binary search
            line_idx = bisect.bisect_right(line_offsets, start_char) - 1
            s_line = section.content_start_line + max(0, line_idx)
            e_line = s_line + raw_text.count("\n")

            # Trim window text before token counting and adjust line ranges by removed newlines
            lead_trim = len(raw_text) - len(raw_text.lstrip("\n"))
            trail_trim = len(raw_text) - len(raw_text.rstrip("\n"))
            trimmed_text = raw_text.strip("\n")
            if not trimmed_text:
                continue
            token_count = count_tokens(trimmed_text, tok)
            adj_start = s_line + (lead_trim)
            adj_end = max(adj_start, e_line - (trail_trim))

            chunks.append(
                Chunk(
                    text=trimmed_text,
                    start_line=adj_start,
                    end_line=adj_end,
                    token_count=token_count,
                    symbol_kind=None,
                    symbol_name=None,
                    symbol_path=None,
                    h1=section.h1,
                    h2=section.h2,
                    h3=section.h3,
                )
            )

    return chunks


# Helpers

def _consume_front_matter_if_any(lines: Sequence[str]) -> Tuple[int, Optional[str]]:
    """If YAML front matter exists at the top, return (offset_after_fm, title or None).

    Only treat a front-matter block as present when the first non-empty line is
    exactly '---' and the closing delimiter is exactly '---' or '...'. If YAML
    parses and includes a 'title', return it for initial H1.
    """
    if not lines:
        return 0, None
    # Find very first non-empty line
    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx >= len(lines) or lines[idx].strip() != "---":
        return 0, None

    start = idx
    MAX_FM_LINES = 200
    end: Optional[int] = None
    for i in range(start + 1, min(len(lines), start + 1 + MAX_FM_LINES)):
        s = lines[i].strip()
        if s in ("---", "..."):
            end = i
            break
    if end is None:
        return 0, None

    fm_text = "".join(lines[start + 1 : end])
    title: Optional[str] = None
    try:
        data = yaml.safe_load(fm_text) or {}
        if isinstance(data, dict):
            raw_title = data.get("title")
            if isinstance(raw_title, str) and raw_title.strip():
                title = raw_title.strip()
    except Exception:
        title = None

    return end + 1, title


def _scan_sections(lines: Sequence[str], *, initial_h1: Optional[str] = None) -> Iterator[_Section]:
    """Yield _Section objects from a sequence of Markdown lines using markdown-it.

    Uses markdown-it-py to parse headings and obtain source line maps. We carve
    the text into sections bounded by headings and attach nearest H1–H3.
    """
    if not lines:
        return

    text = "".join(lines)
    md = MarkdownIt()
    tokens: List[Token] = md.parse(text)

    # Gather headings: (level, title, start_line0, end_line0)
    headings: List[Tuple[int, str, int, int]] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "heading_open" and tok.map:
            level = int(tok.tag[1]) if tok.tag.startswith("h") and tok.tag[1:].isdigit() else 0
            title = ""
            if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                title = tokens[i + 1].content.strip()
            start_line0, end_line0 = tok.map
            headings.append((level, title, start_line0, end_line0))
            i += 2
            continue
        i += 1

    N = len(lines)

    def emit_section(h1: Optional[str], h2: Optional[str], h3: Optional[str], start0: int, end0: int, heading_end0: Optional[int] = None) -> Optional[_Section]:
        if start0 >= end0:
            return None
        content_start0 = heading_end0 if heading_end0 is not None else start0
        content_text = "".join(lines[content_start0:end0])
        start_line1 = start0 + 1
        end_line1 = end0
        content_start_line1 = content_start0 + 1
        return _Section(h1=h1, h2=h2, h3=h3, start_line=start_line1, end_line=end_line1, content_text=content_text, content_start_line=content_start_line1)

    current_h1 = initial_h1
    current_h2: Optional[str] = None
    current_h3: Optional[str] = None

    if headings:
        pre = emit_section(current_h1, current_h2, current_h3, 0, headings[0][2], None)
        if pre:
            yield pre

    for idx, (level, title, h_start0, h_end0) in enumerate(headings):
        if level == 1:
            current_h1, current_h2, current_h3 = title, None, None
        elif level == 2:
            current_h2, current_h3 = title, None
        elif level == 3:
            current_h3 = title
        # H4–H6 are boundaries only
        next_start0 = headings[idx + 1][2] if idx + 1 < len(headings) else N
        sec = emit_section(current_h1, current_h2, current_h3, h_start0, next_start0, heading_end0=h_end0)
        if sec:
            yield sec

    if not headings:
        only = emit_section(current_h1, current_h2, current_h3, 0, N, None)
        if only:
            yield only


def _map_char_span_to_line_range(
    section_text: str,
    start_char: int,
    end_char: int,
    content_start_line: int,
) -> Tuple[int, int]:
    """Map a [start_char, end_char) span to (start_line, end_line) using line-start offsets.

    start_line/end_line are 1-based and inclusive.
    """
    # Build line-start offsets once per section_text (could be cached if needed)
    line_offsets: List[int] = [0]
    for idx, ch in enumerate(section_text):
        if ch == "\n":
            line_offsets.append(idx + 1)

    # start_line is the line containing start_char; end_line is based on number of newlines in slice
    line_idx = bisect.bisect_right(line_offsets, start_char) - 1
    start_line = content_start_line + max(0, line_idx)
    slice_text = section_text[start_char:end_char]
    end_line = start_line + slice_text.count("\n")
    return start_line, end_line


def _is_atx_heading(line: str) -> Optional[Tuple[int, str]]:
    """Return (level, heading_text) if line is an ATX heading, else None."""
    s = line.rstrip("\r\n")
    m = re.match(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$", s)
    if not m:
        return None
    level = len(m.group(1))
    heading_text = m.group(2).strip()
    return level, heading_text


def _is_setext_underline(line: str) -> Optional[int]:
    """Return 1 for '=', 2 for '-' if line is a Setext underline, else None.

    Guards:
    - ignore if line contains '|' (likely a table header)
    - require at least one '=' or '-' and nothing else but whitespace
    """
    s = line.strip()
    if "|" in s:
        return None
    if not s:
        return None
    if set(s) == {"="}:
        return 1
    if set(s) == {"-"}:
        return 2
    return None


def _toggle_fence_if_any(line: str, in_fence: bool, fence_marker: str) -> Tuple[bool, str]:
    """Detect fence start/stop and return updated (in_fence, fence_marker)."""
    stripped = line.lstrip()
    if not in_fence:
        if stripped.startswith("```"):
            return True, "```"
        if stripped.startswith("~~~"):
            return True, "~~~"
        return in_fence, fence_marker
    else:
        if stripped.startswith(fence_marker):
            return False, ""
        return in_fence, fence_marker
