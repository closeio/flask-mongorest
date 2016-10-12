import os

from flask import Flask, request
from flask_mongoengine import MongoEngine
from flask_mongorest import MongoRest
from flask_mongorest.views import ResourceView
from flask_mongorest.resources import Resource
from flask_mongorest import operators as ops
from flask_mongorest.methods import *
from flask_mongorest.authentication import AuthenticationBase

from example import schemas, documents


app = Flask(__name__)

app.url_map.strict_slashes = False

app.config.update(
    DEBUG = True,
    TESTING = True,
    MONGODB_SETTINGS = {
        'HOST': 'localhost',
        'PORT': 27017,
        'DB': 'mongorest_example_app',
        'TZ_AWARE': False,
    },
)

db = MongoEngine(app)
api = MongoRest(app)

class UserResource(Resource):
    document = documents.User
    schema = schemas.User
    filters = {
        'datetime': [ops.Exact]
    }

@api.register()
class UserView(ResourceView):
    resource = UserResource
    methods = [Create, Update, Fetch, List, Delete]

class ContentResource(Resource):
    document = documents.Content

class PostResource(Resource):
    document = documents.Post
    schema = schemas.Post
    related_resources = {
        'content': ContentResource,
        'sections': ContentResource, #nested complex objects
        #'author': UserResource,
        #'editor': UserResource,
        #'user_lists': UserResource,
        'primary_user': UserResource,
    }
    filters = {
        'title': [ops.Exact, ops.Startswith, ops.In(allow_negation=True)],
        'author_id': [ops.Exact],
        'is_published': [ops.Boolean],
    }
    rename_fields = {
        'author': 'author_id',
    }
    bulk_update_limit = 10

    def get_objects(self, **kwargs):
        qs, has_more = super(PostResource, self).get_objects(**kwargs)
        return qs, has_more, {'more': 'stuff'}

    def get_fields(self):
        fields = super(PostResource, self).get_fields()
        if '_include_primary_user' in request.args:
            fields = set(fields) | set(['primary_user'])
        return fields

    def update_object(self, obj, data=None, save=True, parent_resources=None):
        data = data or self.data
        if data.get('author'):
            author = data['author']
            if author.email == 'vincent@vangogh.com':
                obj.tags.append('art')
        return super(PostResource, self).update_object(obj, data, save, parent_resources)

@api.register(name='posts', url='/posts/')
class PostView(ResourceView):
    resource = PostResource
    methods = [Create, Update, BulkUpdate, Fetch, List, Delete]

class LimitedPostResource(Resource):
    document = documents.Post
    related_resources = {
        'content': ContentResource,
    }

@api.register(name='limited_posts', url='/limited_posts/')
class LimitedPostView(ResourceView):
    resource = LimitedPostResource
    methods = [Create, Update, Fetch, List]

class DummyAuthenication(AuthenticationBase):
    def authorized(self):
        return False

@api.register(name='auth', url='/auth/')
class DummyAuthView(ResourceView):
    resource = PostResource
    methods = [Create, Update, Fetch, List, Delete]
    authentication_methods = [DummyAuthenication]

@api.register(name='restricted', url='/restricted/')
class RestrictedPostView(ResourceView):
    """This class allows us to put restrictions in place regarding
       who/what can be read, changed, added or deleted"""
    resource = PostResource
    methods = [Create, Update, Fetch, List, Delete]

    # Can't read a post if it isn't published
    def has_read_permission(self, request, qs):
        return qs.filter(is_published=True)

    # Can't add a post in a published state
    def has_add_permission(self, request, obj):
        return not obj.is_published

    # Can't change a post if it is published
    def has_change_permission(self, request, obj):
        return not obj.is_published

    # Can't delete a post if it is published
    def has_delete_permission(self, request, obj):
        return not obj.is_published

class TestDocument(db.Document):
    name = db.StringField()
    other = db.StringField()
    dictfield = db.DictField()
    is_new = db.BooleanField()
    email = db.EmailField()

class TestResource(Resource):
    document = TestDocument

class TestFieldsResource(Resource):
    document = TestDocument
    fields = ['id', 'name', 'upper_name']

    def upper_name(self, obj):
        return obj.name.upper()

@api.register(name='test', url='/test/')
class TestView(ResourceView):
    resource = TestResource
    methods = [Create, Update, Fetch, List]


@api.register(name='testfields', url='/testfields/')
class TestFieldsResource(ResourceView):
    resource = TestFieldsResource
    methods = [Create, Update, Fetch, List]

class LanguageResource(Resource):
    document = documents.Language

class PersonResource(Resource):
    document = documents.Person
    schema = schemas.Person
    related_resources = {
        'languages': LanguageResource,
    }
    save_related_fields = ['languages']

@api.register(name='person', url='/person/')
class PersonView(ResourceView):
    resource = PersonResource
    methods = [Create, Update, Fetch, List]

# extra resources for testing max_limit
class Post10Resource(PostResource):
    max_limit = 10

class Post250Resource(PostResource):
    max_limit = 250

@api.register(name='posts10', url='/posts10/')
class Post10View(ResourceView):
    resource = Post10Resource
    methods = [Create, Update, BulkUpdate, Fetch, List, Delete]

@api.register(name='posts250', url='/posts250/')
class Post250View(ResourceView):
    resource = Post250Resource
    methods = [Create, Update, BulkUpdate, Fetch, List, Delete]

# Documents, resources, and views for testing differences between db refs and object ids
class A(db.Document):
    txt = db.StringField()

class B(db.Document):
    ref = db.ReferenceField(A, dbref=True)
    txt = db.StringField()

class C(db.Document):
    ref = db.ReferenceField(A)
    txt = db.StringField()

class AResource(Resource):
    document = A

class BResource(Resource):
    document = B

class CResource(Resource):
    document = C

@api.register(url='/a/')
class AView(ResourceView):
    resource = AResource
    methods = [Create, Update, BulkUpdate, Fetch, List, Delete]

@api.register(url='/b/')
class BView(ResourceView):
    resource = BResource
    methods = [Create, Update, BulkUpdate, Fetch, List, Delete]

@api.register(url='/c/')
class CView(ResourceView):
    resource = CResource
    methods = [Create, Update, BulkUpdate, Fetch, List, Delete]


# Documents, resources, and views for testing method permissions
class MethodTestDoc(db.Document):
    txt = db.StringField()

class MethodTestResource(Resource):
    document = MethodTestDoc

@api.register(url='/create_only/')
class CreateOnlyView(ResourceView):
    resource = MethodTestResource
    methods = [Create]

@api.register(url='/update_only/')
class UpdateOnlyView(ResourceView):
    resource = MethodTestResource
    methods = [Update]

@api.register(url='/bulk_update_only/')
class BulkUpdateOnlyView(ResourceView):
    resource = MethodTestResource
    methods = [BulkUpdate]

@api.register(url='/fetch_only/')
class FetchOnlyView(ResourceView):
    resource = MethodTestResource
    methods = [Fetch]

@api.register(url='/list_only/')
class ListOnlyView(ResourceView):
    resource = MethodTestResource
    methods = [List]

@api.register(url='/delete_only/')
class DeleteOnlyView(ResourceView):
    resource = MethodTestResource
    methods = [Delete]

class ViewMethodTestDoc(db.Document):
    txt = db.StringField()

class ViewMethodTestResource(Resource):
    document = ViewMethodTestDoc

@api.register(url='/test_view_method/')
class TestViewMethodView(ResourceView):
    resource = ViewMethodTestResource
    methods = [Create, Update, BulkUpdate, Fetch, List, Delete]

    def _dispatch_request(self, *args, **kwargs):
        super(TestViewMethodView, self)._dispatch_request(*args, **kwargs)
        return { 'method': self._resource.view_method.__name__ }

class DateTimeResource(Resource):
    document = documents.DateTime
    schema = schemas.DateTime

@api.register(name='datetime', url='/datetime/')
class DateTimeView(ResourceView):
    resource = DateTimeResource
    methods = [Create, Update, Fetch, List]


# Document, resource, and view for testing invalid JSON
class DictDoc(db.Document):
    dict = db.DictField()

class DictDocResource(Resource):
    document = DictDoc

@api.register(url='/dict_doc/')
class DictDocView(ResourceView):
    resource = DictDocResource
    methods = [Fetch, List, Create, Update]


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)

