# monitoring/templatetags/custom_filters.py
from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Template filter to get item from dictionary using key.
    Usage: {{ mydict|get_item:key }}
    """
    if dictionary is None:
        return {}
    return dictionary.get(key, {})

@register.filter
def lookup(dictionary, key):
    """
    Template filter to lookup dictionary value by key.
    Usage: {{ mydict|lookup:key }}
    """
    if dictionary is None:
        return None
    return dictionary.get(key)
