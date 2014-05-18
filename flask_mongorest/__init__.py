from flask import Blueprint
from flask_mongorest.methods import Create, BulkUpdate, List

class DelayedApp(object):
    def __init__(self):
        self.url_rules = []

    def add_url_rule(self, *args, **kwargs):
        self.url_rules.append((args, kwargs))

class MongoRest(object):

    def __init__(self, app=None, **kwargs):
        self.url_prefix = kwargs.pop('url_prefix', '')
        self.template_folder = kwargs.pop('template_folder', 'templates')
        if app is not None:
            self.init_app(app, **kwargs)
        else:
            self.app = DelayedApp()

    def init_app(self, app):
        app.register_blueprint(
            Blueprint(self.url_prefix,
                      __name__,
                      template_folder=self.template_folder))
        if hasattr(self, 'app'):
            if isinstance(self.app, DelayedApp):
                for args, kwargs in self.app.url_rules:
                    app.add_url_rule(*args, **kwargs)
        self.app = app

    def register(self, **kwargs):
        def decorator(klass):

            # Construct a url based on a 'name' kwarg with a fallback to a Mongo document's name
            document_name = klass.resource.document.__name__.lower()
            name = kwargs.pop('name', document_name)
            url = kwargs.pop('url', '/%s/' % document_name)

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
