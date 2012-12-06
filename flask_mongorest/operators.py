class Operator(object):
    op = 'exact'

    def prepare_queryset_kwargs(self, field, value, negate):
        return {field+'__'+self.op:value}

    def apply(self, queryset, field, value, negate=False):
        kwargs = self.prepare_queryset_kwargs(field, value, negate)
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
    
class IExact(Operator):
    op = 'iexact'

class In(Operator):
    op = 'in'

    def prepare_queryset_kwargs(self, field, value, negate):
        # only use 'in' or 'nin' if multiple values are specified
        if ',' in value:
            value = value.split(',')
            self.op = (not negate and self.op) or 'nin'
        else:
            self.op = (not negate and 'exact') or 'ne'
        return super(In, self).prepare_queryset_kwargs(field, value, negate)

    def apply(self, queryset, field, value, negate=False):
        kwargs = self.prepare_queryset_kwargs(field, value, negate)
        return queryset.filter(**kwargs)


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

    def prepare_queryset_kwargs(self, field, value, negate):
        if value == 'false':
            bool_value = False
        else:
            bool_value = True
        return {field:bool_value}

