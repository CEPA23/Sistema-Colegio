from urllib.parse import urlencode


DEFAULT_STUDENT_ORDER = 'az'
STUDENT_ORDER_CHOICES = (
    ('az', 'Alfabetico A - Z'),
    ('za', 'Alfabetico Z - A'),
)
VALID_STUDENT_ORDERS = {value for value, _ in STUDENT_ORDER_CHOICES}


def resolve_student_order(request, param='student_order'):
    selected_order = (
        request.GET.get(param)
        or request.POST.get(param)
        or DEFAULT_STUDENT_ORDER
    ).lower()
    if selected_order not in VALID_STUDENT_ORDERS:
        return DEFAULT_STUDENT_ORDER
    return selected_order


def student_order_fields(prefix='', student_order=DEFAULT_STUDENT_ORDER):
    if prefix:
        prefix = prefix if prefix.endswith('__') else f'{prefix}__'

    fields = [
        f'{prefix}first_name',
        f'{prefix}last_name',
    ]
    if student_order == 'za':
        return [f'-{field}' for field in fields]
    return fields


def order_queryset_by_student_name(queryset, prefix='', student_order=DEFAULT_STUDENT_ORDER, extra_fields=None):
    order_fields = list(student_order_fields(prefix=prefix, student_order=student_order))
    if extra_fields:
        order_fields.extend(extra_fields)
    return queryset.order_by(*order_fields)


def student_order_context(request, student_order):
    query_params = request.GET.copy()
    query_params.pop('student_order', None)
    query_string = urlencode(list(query_params.lists()), doseq=True)

    return {
        'student_order': student_order,
        'student_order_choices': STUDENT_ORDER_CHOICES,
        'student_order_query_prefix': f'{query_string}&' if query_string else '',
    }
