from django import template

register = template.Library()

@register.filter(name='govno')
def ostatok(value, arg):
    m = value % int(arg)
    return 12 if m == 0 else m