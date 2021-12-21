from typing import Union

from flask import Blueprint, Flask

from flask_mongorest import BulkUpdate, Create, List


class DelayedApp:
    """
    Store URL rules for later merging with an application URL map.
    """

    def __init__(self):
        self.url_rules = []

    def add_url_rule(self, *args, **kwargs):
        self.url_rules.append((args, kwargs))


def register_class(app: Union[DelayedApp, Flask], klass, *, url_prefix, **kwargs):
    # Construct a url based on a 'name' kwarg with a fallback to the
    # view's class name. Note that the name must be unique.
    name = kwargs.pop("name", klass.__name__)
    url = kwargs.pop("url", None)
    if not url:
        document_name = klass.resource.document.__name__.lower()
        url = f"/{document_name}/"

    # Insert the url prefix, if it exists
    if url_prefix:
        url = f"{url_prefix}{url}"

    # Add url rules
    pk_type = kwargs.pop("pk_type", "string")
    view_func = klass.as_view(name)
    if List in klass.methods:
        app.add_url_rule(
            url,
            defaults={"pk": None},
            view_func=view_func,
            methods=[List.method],
            **kwargs,
        )
    if Create in klass.methods or BulkUpdate in klass.methods:
        app.add_url_rule(
            url,
            view_func=view_func,
            methods=[x.method for x in klass.methods if x in (Create, BulkUpdate)],
            **kwargs,
        )
    app.add_url_rule(
        f"{url}<{pk_type}:pk>/",
        view_func=view_func,
        methods=[x.method for x in klass.methods if x not in (List, BulkUpdate)],
        **kwargs,
    )


class MongoRest:
    def __init__(self, app=None, url_prefix="", template_folder="templates"):
        self.url_prefix = url_prefix
        self.template_folder = template_folder
        self._delayed_app = DelayedApp()
        self._registered_apps = []

        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """
        Provide delayed application instance initialization to support
        Flask application factory pattern. For further details on application
        factories see: https://flask.palletsprojects.com/en/2.0.x/extensiondev/
        """
        app.register_blueprint(
            Blueprint(self.url_prefix, __name__, template_folder=self.template_folder)
        )

        for args, kwargs in self._delayed_app.url_rules:
            app.add_url_rule(*args, **kwargs)

        self._registered_apps.append(app)

    def register(self, **kwargs):
        def decorator(klass):
            for app in [self._delayed_app] + self._registered_apps:
                register_class(app, klass, url_prefix=self.url_prefix, **kwargs)
            return klass

        return decorator
