from flask import Blueprint

from flask_mongorest.methods import BulkUpdate, Create, List


def register_class(app, klass, *, url_prefix, **kwargs):
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
    def __init__(self, app, **kwargs):
        self.app = app
        self.url_prefix = kwargs.pop("url_prefix", "")
        app.register_blueprint(
            Blueprint(self.url_prefix, __name__, template_folder="templates")
        )

    def register(self, **kwargs):
        def decorator(klass):
            register_class(self.app, klass, url_prefix=self.url_prefix, **kwargs)
            return klass

        return decorator
