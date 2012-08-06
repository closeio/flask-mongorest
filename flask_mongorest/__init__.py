from functools import wraps
from flask_mongorest.methods import Create, Update, Fetch, List, Delete


class MongoRest(object):
    def __init__(self, app, **kwargs):
        self.app = app
        self.url_prefix = kwargs.pop('url_prefix', '')

    def register(self, **kwargs):
        def decorator(klass):
            document_name = klass.resource.document.__name__.lower()
            name = kwargs.pop('name', document_name)
            url = kwargs.pop('url', '/%s/' % document_name)
            if self.url_prefix:
                url = '%s%s' % (self.url_prefix, url)
            pk_type = kwargs.pop('pk_type', 'string')
            view_func = klass.as_view(name)
            if List in klass.methods: 
                self.app.add_url_rule(url, defaults={'pk': None}, view_func=view_func, methods=[List.method])
            if Create in klass.methods:
                self.app.add_url_rule(url, view_func=view_func, methods=[Create.method])
            self.app.add_url_rule('%s<%s:%s>/' % (url, pk_type, 'pk'), view_func=view_func, methods=[x.method for x in klass.methods])
            return klass
        return decorator


