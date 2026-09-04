from django import template
from django.utils.safestring import mark_safe

from api.chapter_blocks import highlight_footnote_refs

register = template.Library()


def _coerce_valid_numbers(value) -> set[int]:
    if value is None:
        return set()
    if isinstance(value, str):
        out: set[int] = set()
        for part in value.split(','):
            part = part.strip()
            if part.isdigit():
                out.add(int(part))
        return out
    if isinstance(value, (list, tuple, set)):
        out = set()
        for item in value:
            try:
                out.add(int(item))
            except (TypeError, ValueError):
                continue
        return out
    return set()


@register.filter
def fn_refs(text, valid_numbers):
    return mark_safe(
        highlight_footnote_refs(str(text or ''), _coerce_valid_numbers(valid_numbers)),
    )
