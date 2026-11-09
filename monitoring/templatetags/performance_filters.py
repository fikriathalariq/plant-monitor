from django import template

register = template.Library()


@register.filter(name='calc_efficiency')
def calc_efficiency(ideal_time, rise_time):
    """
    Calculate efficiency as (ideal_time / rise_time) * 100.
    Returns the efficiency percentage or None if calculation is not possible.
    """
    if ideal_time is None or rise_time is None:
        return None
    if rise_time == 0:
        return None
    try:
        return (float(ideal_time) / float(rise_time)) * 100
    except (ValueError, TypeError, ZeroDivisionError):
        return None


@register.simple_tag
def calculate_efficiency(ideal_time, rise_time):
    """
    Template tag to calculate efficiency.
    Usage: {% calculate_efficiency avg_ideal_time avg_rise_time %}
    """
    return calc_efficiency(ideal_time, rise_time)
