from flask import Blueprint
from flask_mongorest.methods import Create, BulkUpdate, List

class _DelayedApp(object):
    """
    Stores URL rules for later merging with application URL map.

    """

    def __init__(self):
        self.url_rules = []

    def add_url_rule(self, *args, **kwargs):
        self.url_rules.append((args, kwargs))


class MongoRest(object):
    def __init__(self, app=None, template_folder='templates', **kwargs):
        """
        Takes optional Flask application instance. If supplied, `init_app` will be
        called to update application url map.

        """

        self.url_prefix = kwargs.pop('url_prefix', '')
        self.template_folder = template_folder
        if app is not None:
            self.init_app(app, **kwargs)
        else:
            self.app = _DelayedApp()

    def init_app(self, app):
        """
        Provides delayed application instance initialization to support
        Flask application factory pattern. For further details on application
        factories see:

        http://flask.pocoo.org/docs/dev/patterns/appfactories/

        and

        http://mattupstate.com/python/2013/06/26/how-i-structure-my-flask-applications.html
        """

        app.register_blueprint(
            Blueprint(self.url_prefix, __name__, template_folder=self.template_folder))

        if hasattr(self, 'app') and isinstance(self.app, _DelayedApp):
                for args, kwargs in self.app.url_rules:
                    app.add_url_rule(*args, **kwargs)

        self.app = app

    def register(self, **kwargs):
        def decorator(klass):

            # Construct a url based on a 'name' kwarg with a fallback to a
            # Mongo document's name
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
                self.app.add_url_rule(url, defaults={'pk': None}, view_func=view_func,
                      methods=[List.method], **kwargs)
            if Create in klass.methods or BulkUpdate in klass.methods:
                methods = [x.method for x in klass.methods if x in (Create, BulkUpdate)]
                self.app.add_url_rule(url, view_func=view_func, methods=methods, **kwargs)

            methods = [x.method for x in klass.methods if x not in (List, BulkUpdate)]
            self.app.add_url_rule('%s<%s:%s>/' % (url, pk_type, 'pk'),
                view_func=view_func, methods=methods, **kwargs)

            return klass

        return decorator
