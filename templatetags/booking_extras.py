from django import template
from decimal import Decimal, InvalidOperation

register = template.Library()

@register.filter
def multiply(value, arg):
    try:
        # Default None values to 0
        if value is None:
            value = 0
        if arg is None:
            arg = 0
        return Decimal(value) * Decimal(arg)
    except (InvalidOperation, TypeError, ValueError):
        return ''