"""Small Markdown-to-Telegram HTML renderer with balanced, Unicode-safe chunks."""

from html import escape
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit

INLINE = re.compile(
    r"`([^`\n]+)`|\*\*(.+?)\*\*|__(.+?)__|~~(.+?)~~|(?<![\w*])\*(?=\S)([^*\n]+?)(?<!\s)\*(?![\w*])|(?<![\w_])_(?=\S)([^_\n]+?)(?<!\s)_(?![\w_])|\[([^\]\n]+)\]\(([^\s)]+)\)"
)


def inline(text, depth=0):
    if depth > 8:
        return escape(text)
    result = []
    start = 0
    for match in INLINE.finditer(text):
        result.append(escape(text[start : match.start()]))
        groups = match.groups()
        if groups[0] is not None:
            rendered = (
                "<code>" + escape(groups[0]) + "</code>"
                if depth == 0
                else escape(groups[0])
            )
        elif groups[1] is not None or groups[2] is not None:
            rendered = (
                "<b>"
                + inline(groups[1] if groups[1] is not None else groups[2], depth + 1)
                + "</b>"
            )
        elif groups[3] is not None:
            rendered = "<s>" + inline(groups[3], depth + 1) + "</s>"
        elif groups[4] is not None or groups[5] is not None:
            rendered = (
                "<i>"
                + inline(groups[4] if groups[4] is not None else groups[5], depth + 1)
                + "</i>"
            )
        else:
            label, url = groups[6:8]
            try:
                valid = (
                    urlsplit(url).scheme in ("https", "http")
                    and bool(urlsplit(url).netloc)
                    and not any(ord(c) < 32 for c in url)
                )
            except ValueError:
                valid = False
            rendered = (
                '<a href="'
                + escape(url, quote=True)
                + '">'
                + inline(label, depth + 1)
                + "</a>"
                if valid
                else escape(match.group())
            )
        result.append(rendered)
        start = match.end()
    result.append(escape(text[start:]))
    return "".join(result)


def format_chat_text(text):
    result = []
    code = None
    quote = []

    def flush_quote():
        if quote:
            result.append("<blockquote>" + "\n".join(quote) + "</blockquote>")
            quote.clear()

    for line in text.split("\n"):
        if re.match(r"^\s*```", line):
            flush_quote()
            if code is None:
                code = []
            else:
                result.append("<pre>" + escape("\n".join(code)) + "</pre>")
                code = None
            continue
        if code is not None:
            code.append(line)
            continue
        if re.match(r"^\s*>\s?", line):
            quote.append(inline(re.sub(r"^\s*>\s?", "", line), 1))
            continue
        flush_quote()
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if heading:
            result.append("<b>" + inline(heading.group(1), 1) + "</b>")
            continue
        line = re.sub(r"^(\s*)[-*+]\s+", r"\1• ", line)
        result.append(inline(line))
    flush_quote()
    if code is not None:
        result.append("<pre>" + escape("\n".join(code)) + "</pre>")
    return "\n".join(result)


class Chunker(HTMLParser):
    def __init__(self, limit):
        super().__init__(convert_charrefs=True)
        self.limit = limit
        self.stack = []
        self.parts = []
        self.current = []
        self.size = 0

    def handle_starttag(self, tag, attrs):
        opening = self.get_starttag_text()
        self.stack.append((tag, opening))
        self.current.append(opening)

    def handle_endtag(self, tag):
        self.current.append("</" + tag + ">")
        self.stack.pop()

    def flush(self):
        if self.size:
            self.parts.append(
                "".join(self.current)
                + "".join("</" + tag + ">" for tag, _ in reversed(self.stack))
            )
        self.current = [opening for _, opening in self.stack]
        self.size = 0

    def handle_data(self, data):
        # Telegram entity offsets use UTF-16 units. Never cut a surrogate pair or HTML entity.
        for char in data:
            units = 2 if ord(char) > 0xFFFF else 1
            if self.size + units > self.limit:
                self.flush()
            self.current.append(escape(char))
            self.size += units
            if char == "\n" and self.size >= self.limit * 0.8:
                self.flush()


def split_rich_text(text, limit=3500):
    if not 2 <= limit <= 4096:
        raise ValueError("Message limit must be 2–4096 UTF-16 units")
    parser = Chunker(limit)
    parser.feed(format_chat_text(text))
    parser.close()
    parser.flush()
    return parser.parts
