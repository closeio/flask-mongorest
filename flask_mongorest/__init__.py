from flask import Blueprint
from flask_mongorest.methods import Create, BulkUpdate, List


class MongoRest(object):
    def __init__(self, app, **kwargs):
        self.app = app
        self.url_prefix = kwargs.pop('url_prefix', '')
        app.register_blueprint(Blueprint(self.url_prefix, __name__, template_folder='templates'))

    def register(self, **kwargs):
        def decorator(klass):
            # Construct a url based on a 'name' kwarg with a fallback to the
            # view's class name. Note that the name must be unique.
            name = kwargs.pop('name', klass.__name__)
            url = kwargs.pop('url', None)
            if not url:
                document_name = klass.resource.document.__name__.lower()
                url = '/%s/' % document_name

            # Insert the url prefix, if it exists
            if self.url_prefix:
                url = '%s%s' % (self.url_prefix, url)

            # Add url rules
            pk_type = kwargs.pop('pk_type', 'string')
            view_func = klass.as_view(name)
            if List in klass.methods:
                self.app.add_url_rule(url, defaults={'pk': None}, view_func=view_func, methods=[List.method], **kwargs)
            if Create in klass.methods or BulkUpdate in klass.methods:
                self.app.add_url_rule(url, view_func=view_func, methods=[x.method for x in klass.methods if x in (Create, BulkUpdate)], **kwargs)
            self.app.add_url_rule('%s<%s:%s>/' % (url, pk_type, 'pk'), view_func=view_func, methods=[x.method for x in klass.methods if x not in (List, BulkUpdate)], **kwargs)
            return klass

        return decorator

