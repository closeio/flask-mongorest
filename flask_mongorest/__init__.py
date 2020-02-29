from flask import Blueprint
from flask_mongorest.methods import *

def register_class(app, klass, **kwargs):
    # Construct a url based on a 'name' kwarg with a fallback to the
    # view's class name. Note that the name must be unique.
    name = kwargs.pop('name', klass.__name__)
    view_func = klass.as_view(name)
    url = kwargs.pop('url', None)
    if not url:
        document_name = klass.resource.document.__name__.lower()
        url = f'/{document_name}/'

    # Insert the url prefix, if it exists
    url_prefix = kwargs.pop('url_prefix', '')
    if url_prefix:
        url = f'{url_prefix}{url}'

    # Add url rules
    klass_methods = set(klass.methods)
    if Create in klass_methods and BulkCreate in klass_methods:
        raise ValueError('Use either Create or BulkCreate!')

    for x in klass_methods & {Fetch, Update, Delete}:
        endpoint = view_func.__name__ + x.__name__
        app.add_url_rule(
            f'{url}<string:pk>/', defaults={'short_mime': None},
            view_func=view_func, methods=[x.method], endpoint=endpoint, **kwargs
        )

    for x in klass_methods & {Create, BulkFetch, BulkCreate, BulkUpdate, BulkDelete}:
        endpoint = view_func.__name__ + x.__name__
        app.add_url_rule(
            url, defaults={'pk': None, 'short_mime': None},
            view_func=view_func, methods=[x.method], endpoint=endpoint, **kwargs
        )

    if Download in klass.methods:
        endpoint = view_func.__name__ + Download.__name__
        app.add_url_rule(
            f'{url}download/<string:short_mime>/', defaults={'pk': None, 'short_mime': 'gz'},
            view_func=view_func, methods=[Download.method], endpoint=endpoint, **kwargs
        )

class MongoRest(object):
    def __init__(self, app, **kwargs):
        self.app = app
        self.url_prefix = kwargs.pop('url_prefix', '')
        app.register_blueprint(Blueprint(self.url_prefix, __name__, template_folder='templates'))

    def register(self, **kwargs):
        def decorator(klass):
            register_class(self.app, klass, **kwargs)
            return klass

        return decorator

