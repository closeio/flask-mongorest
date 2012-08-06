class Operator(object):
    op = 'exact'

    def apply(self, queryset, field, value, negate=False):
        kwargs = {field+'__'+self.op:value} 
        if negate:
            return queryset.exclude(**kwargs)
        qs = queryset.filter(**kwargs)
        return qs

class Ne(Operator):
    op = 'ne'

class Lt(Operator):
    op = 'lt'

class Lte(Operator):
    op = 'lte'

class Gt(Operator):
    op = 'gt'

class Gte(Operator):
    op = 'gte'

class Exact(Operator):
    op = 'exact'

class Contains(Operator):
    op = 'contains'

class Startswith(Operator):
    op = 'startswith'

class Endswith(Operator):
    op = 'endswith'

