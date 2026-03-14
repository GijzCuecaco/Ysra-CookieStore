from django import template

register = template.Library()

@register.filter
def split(value, separator=","):
    """
    Splits a string into a list based on a separator.
    Usage: {{ string|split:"," }}
    """
    if not value:
        return []
    return value.split(separator)

@register.filter
def strip(value):
    """
    Strips whitespace from the beginning and end of a string.
    Usage: {{ string|strip }}
    """
    if not value:
        return value
    return value.strip()
