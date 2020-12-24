"""
Flask-MongoRest operators.

Operators are the building blocks that Resource filters are built upon.
Their role is to generate and apply the right filters to a provided
queryset. For example:

    GET /post/?title__startswith=John

Such request would result in calling this module's `Startswith` operator
like so:

    new_queryset = Startswith().apply(queryset, 'title', 'John')

Where the original queryset would be `BlogPost.objects.all()` and the
new queryset would be equivalent to:

    BlogPost.objects.filter(title__startswith='John')

It's also easy to create your own Operator subclass and use it in your
Resource. For example, if you have an endpoint listing students and you
want to filter them by the range of their scores like so:

    GET /student/?score__range=0,10

Then you can create a Range Operator:

    class Range(Operator):
        op = 'range'
        def prepare_queryset_kwargs(self, field, value, negate=False):
            # For the sake of simplicity, we won't support negate here,
            # i.e. /student/?score__not__range=0,10 won't work.
            lower, upper = value.split(',')
            return {
                field + '__lte': upper,
                field + '__gte': lower
            }

Then you include it in your Resource's filters:

    class StudentResource(Resource):
        document = documents.Student
        filters = {
            'score': [Range]
        }

And this way, the request we mentioned above would result in:

    Student.objects.filter(score__lte=upper, score__gte=lower)
"""

class Operator(object):
    """Base class that all the other operators should inherit from."""

    op = 'exact'
    typ = 'string'

    # Can be overridden via constructor.
    allow_negation = False

    def __init__(self, allow_negation=False):
        self.allow_negation = allow_negation

    # Lets us specify filters as an instance if we want to override the
    # default arguments (in addition to specifying them as a class).
    def __call__(self):
        return self

    def prepare_queryset_kwargs(self, field, value, negate):
        if negate:
            return {'__'.join(filter(None, [field, 'not', self.op])): value}
        else:
            return {'__'.join(filter(None, [field, self.op])): value}

    def apply(self, queryset, field, value, negate=False):
        kwargs = self.prepare_queryset_kwargs(field, value, negate)
        return queryset.filter(**kwargs)

def try_float(value):
    try:
        return float(value)
    except ValueError:
        return value

class Ne(Operator):
    op = 'ne'

class Lt(Operator):
    op = 'lt'
    typ = 'number'

    def prepare_queryset_kwargs(self, field, value, negate):
        return {'__'.join(filter(None, [field, self.op])): try_float(value)}

class Lte(Operator):
    op = 'lte'
    typ = 'number'

    def prepare_queryset_kwargs(self, field, value, negate):
        return {'__'.join(filter(None, [field, self.op])): try_float(value)}

class Gt(Operator):
    op = 'gt'
    typ = 'number'

    def prepare_queryset_kwargs(self, field, value, negate):
        return {'__'.join(filter(None, [field, self.op])): try_float(value)}

class Gte(Operator):
    op = 'gte'
    typ = 'number'

    def prepare_queryset_kwargs(self, field, value, negate):
        return {'__'.join(filter(None, [field, self.op])): try_float(value)}

class Exact(Operator):
    op = 'exact'

    def prepare_queryset_kwargs(self, field, value, negate):
        # Using <field>__exact causes mongoengine to generate a regular
        # expresison query, which we'd like to avoid.
        if negate:
            return {'%s__ne' % field: value}
        else:
            return {field: value}

class IExact(Operator):
    op = 'iexact'

class In(Operator):
    op = 'in'
    typ = 'array'

    def prepare_queryset_kwargs(self, field, value, negate):
        # this is null if the user submits an empty in expression (like
        # "user__in=")
        value = value or []

        # only use 'in' or 'nin' if multiple values are specified
        if ',' in value:
            value = value.split(',')
            op = negate and 'nin' or self.op
        else:
            op = negate and 'ne' or ''
        return {'__'.join(filter(None, [field, op])): value}

class Contains(Operator):
    op = 'contains'

class IContains(Operator):
    op = 'icontains'

class Startswith(Operator):
    op = 'startswith'

class IStartswith(Operator):
    op = 'istartswith'

class Endswith(Operator):
    op = 'endswith'

class IEndswith(Operator):
    op = 'iendswith'

class Boolean(Operator):
    op = 'exact'
    typ = 'boolean'

    def prepare_queryset_kwargs(self, field, value, negate):
        if value == 'false':
            bool_value = False
        else:
            bool_value = True

        if negate:
            bool_value = not bool_value

        return {field: bool_value}

