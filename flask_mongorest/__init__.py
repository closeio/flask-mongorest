import re
from flask import Blueprint
from flask_mongorest.methods import Create, BulkUpdate, List


def to_underscore(name):

    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


class MongoRest(object):
    def __init__(self, app, **kwargs):
        self.app = app
        self.url_prefix = kwargs.pop('url_prefix', '')
        app.register_blueprint(Blueprint(self.url_prefix, __name__, template_folder='templates'))

    def register(self, **kwargs):
        def decorator(klass):

            # Construct a url based on a 'name' kwarg with a fallback to a Mongo document's name
            document_name = klass.resource.document.__name__.lower()
            name = kwargs.pop('name', document_name)
            url = kwargs.pop('url', '/%s/' % document_name)
            endpoint = to_underscore(klass.__name__)
            # Insert the url prefix, if it exists
            if self.url_prefix:
                url = '%s%s' % (self.url_prefix, url)

            # Add url rules
            pk_type = kwargs.pop('pk_type', 'string')
            view_func = klass.as_view(name)
            if List in klass.methods:
                self.app.add_url_rule(url, defaults={'pk': None}, endpoint=endpoint, view_func=view_func, methods=[List.method], **kwargs)
            if Create in klass.methods or BulkUpdate in klass.methods:
                self.app.add_url_rule(url, view_func=view_func, endpoint=endpoint, methods=[x.method for x in klass.methods if x in (Create, BulkUpdate)], **kwargs)
            self.app.add_url_rule('%s<%s:%s>/' % (url, pk_type, 'pk'), endpoint=endpoint, view_func=view_func, methods=[x.method for x in klass.methods if x not in (List, BulkUpdate)], **kwargs)
            return klass

        return decorator

