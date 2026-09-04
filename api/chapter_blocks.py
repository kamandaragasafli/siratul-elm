"""Fəsil mətni ↔ structured blocks ↔ Quill HTML."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

ALIGN_MAP = {
    'ql-align-center': 'center',
    'ql-align-right': 'right',
    'ql-align-justify': 'justified',
}


def _inline_md_to_runs(text: str) -> list[dict]:
    """**qalın**, *italik* → runs."""
    runs: list[dict] = []
    i = 0
    while i < len(text):
        if text.startswith('**', i):
            end = text.find('**', i + 2)
            if end > i + 2:
                runs.append({'text': text[i + 2 : end], 'bold': True})
                i = end + 2
                continue
        if text[i] == '*' and (i + 1 >= len(text) or text[i + 1] != '*'):
            end = text.find('*', i + 1)
            if end > i + 1:
                runs.append({'text': text[i + 1 : end], 'italic': True})
                i = end + 1
                continue
        nxt = text.find('**', i)
        nxt_i = text.find('*', i)
        candidates = [n for n in (nxt, nxt_i) if n >= 0]
        end_at = min(candidates) if candidates else len(text)
        chunk = text[i:end_at]
        if chunk:
            if runs and not runs[-1].get('bold') and not runs[-1].get('italic'):
                runs[-1]['text'] += chunk
            else:
                runs.append({'text': chunk})
        i = end_at if end_at > i else i + 1
    return runs or [{'text': text or ''}]


def plain_to_blocks(text: str) -> list[dict]:
    if not (text or '').strip():
        return []
    blocks: list[dict] = []
    for raw_line in text.replace('\r\n', '\n').split('\n'):
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if line.startswith('### '):
            blocks.append({'type': 'heading2', 'text': line[4:].strip()})
        elif line.startswith('## '):
            blocks.append({'type': 'heading2', 'text': line[3:].strip()})
        elif line.startswith('# '):
            blocks.append({'type': 'heading1', 'text': line[2:].strip()})
        elif line.startswith('> '):
            blocks.append({'type': 'quote', 'text': line[2:].strip()})
        else:
            blocks.append(
                {
                    'type': 'paragraph',
                    'align': 'justified',
                    'runs': _inline_md_to_runs(line),
                },
            )
    return blocks


def blocks_to_plain_text(blocks: list | None) -> str:
    if not blocks:
        return ''
    parts: list[str] = []
    for node in blocks:
        if not isinstance(node, dict):
            continue
        t = node.get('type')
        if t == 'heading1':
            parts.append(f"# {node.get('text', '')}")
        elif t == 'heading2':
            parts.append(f"## {node.get('text', '')}")
        elif t == 'quote':
            parts.append(f"> {node.get('text', '')}")
        elif t == 'listItem':
            prefix = '• ' if node.get('listStyle') == 'bullet' else '1. '
            runs = node.get('runs') or [{'text': ''}]
            parts.append(prefix + ''.join(r.get('text', '') for r in runs))
        elif t == 'paragraph':
            runs = node.get('runs') or [{'text': ''}]
            parts.append(''.join(r.get('text', '') for r in runs))
        elif t == 'footnotes':
            parts.append('---')
            for entry in parse_footnote_entries(node.get('entries') or node.get('items') or []):
                if entry.get('text'):
                    parts.append(f"*{entry['n']}. {entry['text']}*")
    return '\n'.join(parts)


def _runs_to_html(runs: list[dict]) -> str:
    out: list[str] = []
    for r in runs or []:
        t = html.escape(r.get('text') or '')
        if r.get('bold') and r.get('italic'):
            t = f'<strong><em>{t}</em></strong>'
        elif r.get('bold'):
            t = f'<strong>{t}</strong>'
        elif r.get('italic'):
            t = f'<em>{t}</em>'
        out.append(t)
    return ''.join(out) or '<br>'


def blocks_to_html(blocks: list | None) -> str:
    if not blocks:
        return '<p><br></p>'
    parts: list[str] = []
    for node in blocks:
        if not isinstance(node, dict):
            continue
        t = node.get('type')
        if t == 'heading1':
            parts.append(f"<h1>{html.escape(node.get('text') or '')}</h1>")
        elif t == 'heading2':
            parts.append(f"<h2>{html.escape(node.get('text') or '')}</h2>")
        elif t == 'quote':
            parts.append(f"<blockquote>{html.escape(node.get('text') or '')}</blockquote>")
        elif t == 'listItem':
            tag = 'ol' if node.get('listStyle') == 'number' else 'ul'
            inner = _runs_to_html(node.get('runs') or [])
            parts.append(f'<{tag}><li>{inner}</li></{tag}>')
        elif t == 'paragraph':
            align = node.get('align') or 'justified'
            cls = ''
            if align == 'center':
                cls = ' class="ql-align-center"'
            elif align == 'right':
                cls = ' class="ql-align-right"'
            elif align == 'justified':
                cls = ' class="ql-align-justify"'
            parts.append(f'<p{cls}>{_runs_to_html(node.get("runs") or [])}</p>')
    return ''.join(parts) or '<p><br></p>'


def extract_footnotes(blocks: list | None) -> tuple[list[dict], list[dict], str]:
    """Mətn blokları və footnotes siyahısını ayır."""
    body: list[dict] = []
    entries: list[dict] = []
    heading = 'Qeydlər və istinadlar'
    for node in blocks or []:
        if not isinstance(node, dict):
            continue
        if node.get('type') == 'footnotes':
            raw = node.get('entries') or node.get('items') or []
            entries = parse_footnote_entries(raw)
            heading = (node.get('heading') or heading).strip() or heading
        else:
            body.append(node)
    return body, entries, heading


def parse_footnote_entries(raw: list | None) -> list[dict]:
    """Panel / blocks → [{n, text}, …] — köhnə string[] dəstəyi."""
    if not raw:
        return []
    parsed: list[dict] = []
    for i, item in enumerate(raw):
        if isinstance(item, dict):
            try:
                n = int(item.get('n') or 0)
            except (TypeError, ValueError):
                continue
            text = str(item.get('text') or '').strip()
            if n >= 1:
                parsed.append({'n': n, 'text': text})
        else:
            text = str(item or '').strip()
            if text:
                parsed.append({'n': i + 1, 'text': text})
    by_n: dict[int, str] = {}
    for entry in parsed:
        by_n[entry['n']] = entry['text']
    return [{'n': n, 'text': t} for n, t in sorted(by_n.items())]


def footnote_valid_numbers(entries: list[dict] | None) -> set[int]:
    return {int(e['n']) for e in (entries or []) if e.get('text') and str(e.get('text', '')).strip()}


def footnote_max_number(entries: list[dict] | None) -> int:
    nums = footnote_valid_numbers(entries)
    return max(nums) if nums else 0


def merge_footnotes(
    body_blocks: list[dict],
    entries: list | None,
    heading: str = 'Qeydlər və istinadlar',
) -> list[dict]:
    blocks = list(body_blocks or [])
    clean_entries = [e for e in parse_footnote_entries(entries) if e.get('text')]
    if clean_entries:
        blocks.append(
            {
                'type': 'footnotes',
                'heading': heading or 'Qeydlər və istinadlar',
                'entries': clean_entries,
            },
        )
    return blocks


def highlight_footnote_refs(text: str, valid_numbers: set[int] | None) -> str:
    """Mobil önizləmə — [N] istinadlarını vurğula."""
    raw = text or ''
    valid = valid_numbers or set()
    if not valid or not raw:
        return html.escape(raw)

    def repl(match: re.Match[str]) -> str:
        n = int(match.group(1))
        if n in valid:
            return f'<span class="rp-fn-ref">[{n}]</span>'
        return html.escape(match.group(0))

    return re.sub(r'\[(\d{1,2})\]', repl, html.escape(raw))


def chapter_editor_data(blocks: list | None, content: str) -> tuple[str, list[dict], str]:
    if blocks:
        body, entries, heading = extract_footnotes(blocks)
        return blocks_to_html(body), entries, heading
    return blocks_to_html(plain_to_blocks(content)), [], 'Qeydlər və istinadlar'


def chapter_editor_html(blocks: list | None, content: str) -> str:
    html, _, _ = chapter_editor_data(blocks, content)
    return html


class _QuillHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.blocks: list[dict] = []
        self._stack: list[dict] = []
        self._para_align = 'justified'
        self._runs: list[dict] = []
        self._run_bold = False
        self._run_italic = False
        self._list_style: str | None = None
        self._in_li = False

    def _flush_runs(self):
        if self._runs:
            text = ''.join(r.get('text', '') for r in self._runs)
            if text.strip() or len(self._runs) == 1:
                self.blocks.append(
                    {
                        'type': 'paragraph',
                        'align': self._para_align,
                        'runs': self._runs,
                    },
                )
        self._runs = []
        self._para_align = 'justified'

    def _append_text(self, data: str):
        if not data:
            return
        if self._in_li:
            if self._runs and self._runs[-1].get('bold') == self._run_bold and self._runs[-1].get(
                'italic',
            ) == self._run_italic:
                self._runs[-1]['text'] += data
            else:
                run: dict = {'text': data}
                if self._run_bold:
                    run['bold'] = True
                if self._run_italic:
                    run['italic'] = True
                self._runs.append(run)
            return
        if self._runs and self._runs[-1].get('bold') == self._run_bold and self._runs[-1].get(
            'italic',
        ) == self._run_italic:
            self._runs[-1]['text'] += data
        else:
            run = {'text': data}
            if self._run_bold:
                run['bold'] = True
            if self._run_italic:
                run['italic'] = True
            self._runs.append(run)

    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs)
        cls = attrs_d.get('class', '')
        if tag in ('h1',):
            self._flush_runs()
            self._stack.append({'kind': 'h1', 'text': ''})
        elif tag in ('h2',):
            self._flush_runs()
            self._stack.append({'kind': 'h2', 'text': ''})
        elif tag == 'blockquote':
            self._flush_runs()
            self._stack.append({'kind': 'quote', 'text': ''})
        elif tag == 'ol':
            self._flush_runs()
            self._list_style = 'number'
        elif tag == 'ul':
            self._flush_runs()
            self._list_style = 'bullet'
        elif tag == 'li':
            self._flush_runs()
            self._in_li = True
            self._runs = []
        elif tag == 'p':
            self._flush_runs()
            self._para_align = 'justified'
            for c in cls.split():
                if c in ALIGN_MAP:
                    self._para_align = ALIGN_MAP[c]
        elif tag in ('strong', 'b'):
            self._run_bold = True
        elif tag in ('em', 'i'):
            self._run_italic = True
        elif tag == 'br':
            self._append_text('\n')

    def handle_endtag(self, tag):
        if tag in ('h1', 'h2', 'blockquote'):
            if self._stack:
                item = self._stack.pop()
                text = (item.get('text') or '').strip()
                if text:
                    if item['kind'] == 'h1':
                        self.blocks.append({'type': 'heading1', 'text': text})
                    elif item['kind'] == 'h2':
                        self.blocks.append({'type': 'heading2', 'text': text})
                    elif item['kind'] == 'quote':
                        self.blocks.append({'type': 'quote', 'text': text})
        elif tag in ('strong', 'b'):
            self._run_bold = False
        elif tag in ('em', 'i'):
            self._run_italic = False
        elif tag == 'li':
            if self._runs:
                self.blocks.append(
                    {
                        'type': 'listItem',
                        'listStyle': self._list_style or 'bullet',
                        'level': 0,
                        'runs': self._runs,
                    },
                )
            self._runs = []
            self._in_li = False
        elif tag == 'p':
            self._flush_runs()
        elif tag in ('ol', 'ul'):
            self._list_style = None

    def handle_data(self, data):
        if self._stack:
            self._stack[-1]['text'] = self._stack[-1].get('text', '') + data
        else:
            self._append_text(data)

    def close(self):
        super().close()
        self._flush_runs()


def html_to_blocks(raw_html: str) -> list[dict]:
    html_text = (raw_html or '').strip()
    if not html_text or html_text in ('<p><br></p>', '<p></p>'):
        return []
    parser = _QuillHTMLParser()
    parser.feed(html_text)
    parser.close()
    return parser.blocks


def html_to_plain_text(raw_html: str) -> str:
    return blocks_to_plain_text(html_to_blocks(raw_html))
