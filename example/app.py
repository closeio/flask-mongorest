import os

from urlparse import urlparse
from flask import Flask, request
from flask.ext.mongoengine import MongoEngine
from flask.ext.mongoengine.wtf.orm import model_form
from flask.ext.mongorest import MongoRest
from flask.ext.mongorest.views import ResourceView
from flask.ext.mongorest.resources import Resource
from flask.ext.mongorest import operators as ops
from flask.ext.mongorest.methods import *
from flask.ext.mongorest.authentication import AuthenticationBase
from flask.ext.wtf import TextField, length

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
        'TZ_AWARE': True,
    },
)

db = MongoEngine(app)
api = MongoRest(app)

class User(db.Document):
    email = db.EmailField(unique=True, required=True)
    first_name = db.StringField(max_length=50)
    last_name = db.StringField(max_length=50)
    emails = db.ListField(db.EmailField())
    datetime = db.DateTimeField()
    datetime_local = db.DateTimeField()
    balance = db.IntField() # in cents

class UserResource(Resource):
    document = User
    filters = {
        'datetime': [ops.Exact]
    }
    uri_prefix = "/user/"

@api.register()
class UserView(ResourceView):
    resource = UserResource
    methods = [Create, Update, Fetch, List, Delete]

class Content(db.EmbeddedDocument):
    text = db.StringField()
    lang = db.StringField(max_length=3)

class ContentResource(Resource):
    document = Content

class Post(db.Document):
    title = db.StringField(max_length=120, required=True)
    description = db.StringField(max_length=120, required=False)
    author = db.ReferenceField(User)
    editor = db.ReferenceField(User)
    tags = db.ListField(db.StringField(max_length=30))
    user_lists = db.ListField(db.SafeReferenceField(User))
    sections = db.ListField(db.EmbeddedDocumentField(Content))
    content = db.EmbeddedDocumentField(Content)
    is_published = db.BooleanField()

    def primary_user(self):
        return self.user_lists[0] if self.user_lists else None

class PostResource(Resource):
    document = Post
    related_resources = {
        'content': ContentResource,
        'sections': ContentResource, #nested complex objects
        'author': UserResource,
        'editor': UserResource,
        'user_lists': UserResource,
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

    def get_fields(self):
        fields = super(PostResource, self).get_fields()
        if '_include_primary_user' in request.args:
            fields = set(fields) | set(['primary_user'])
        return fields

    def update_object(self, obj, data=None, save=True, parent_resources=None):
        data = data or self.data
        if data.get('author'):
            author_uri = urlparse(data['author']).path
            author_id = author_uri.lstrip(UserResource.uri_prefix)
            author = User.objects.get(pk=author_id)
            if author.email == 'vincent@vangogh.com':
                obj.tags.append('art')
        return super(PostResource, self).update_object(obj, data, save, parent_resources)

@api.register(name='posts', url='/posts/')
class PostView(ResourceView):
    resource = PostResource
    methods = [Create, Update, BulkUpdate, Fetch, List, Delete]

class LimitedPostResource(Resource):
    document = Post
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

TestBaseForm = model_form(TestDocument)

class TestForm(TestBaseForm):
    name = TextField(validators=[length(min=3, max=8)])

class TestResource(Resource):
    form = TestForm
    document = TestDocument

class TestFormResource(Resource):
    form = TestForm
    document = TestDocument
    uri_prefix = "/testform/"

class TestFieldsResource(Resource):
    document = TestDocument
    fields = ['id', 'name', 'upper_name']

    def upper_name(self, obj):
        return obj.name.upper()

@api.register(name='test', url='/test/')
class TestView(ResourceView):
    resource = TestResource
    methods = [Create, Update, Fetch, List]

@api.register(name='testform', url='/testform/')
class TestFormView(ResourceView):
    resource = TestFormResource
    methods = [Create, Update, Fetch, List, BulkUpdate]


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
class AView(ResourceView):
    resource = BResource
    methods = [Create, Update, BulkUpdate, Fetch, List, Delete]

@api.register(url='/c/')
class AView(ResourceView):
    resource = CResource
    methods = [Create, Update, BulkUpdate, Fetch, List, Delete]


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)

