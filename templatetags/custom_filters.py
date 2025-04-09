from django import template
from calendar import month_name

register = template.Library()

@register.filter
def get_months(value):
    """Returns a list of tuples with month numbers and names"""
    return [(i, month_name[i]) for i in range(1, 13)]

@register.filter
def rangelist(value, arg):
    """Returns a list of numbers from value to arg"""
    return range(int(value), int(arg))