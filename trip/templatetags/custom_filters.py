from django import template
from calendar import month_name

register = template.Library()

@register.filter
def rangelist(start, end):
    """Returns a list of numbers from start to end (inclusive)"""
    return range(int(start), int(end) + 1)

@register.filter
def get_months(value):
    """Returns a list of tuples with month numbers and names"""
    return [(i, month_name[i]) for i in range(1, 13)]
