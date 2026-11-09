from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Template filter to get item from dictionary."""
    if isinstance(dictionary, dict):
        return dictionary.get(key, {})
    return {}
