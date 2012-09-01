import os
import datetime

from flask import Flask
from flask.ext.mongoengine import MongoEngine
from flask.ext.mongorest import MongoRest
from flask.ext.mongorest.views import ResourceView
from flask.ext.mongorest.resources import Resource
from flask.ext.mongorest import operators as ops
from flask.ext.mongorest.methods import *
from flask.ext.mongorest.authentication import AuthenticationBase


app = Flask(__name__)

app.config.update(
    DEBUG = True,
    TESTING = True,
    MONGODB_HOST = 'localhost',
    MONGODB_PORT = '27017',
    MONGODB_DB = 'mongorest_example_app',
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

class UserResource(Resource):
    document = User

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
    user_lists = db.ListField(db.ListField(db.ReferenceField(User)))
    sections = db.ListField(db.EmbeddedDocumentField(Content))
    content = db.EmbeddedDocumentField(Content)
    is_published = db.BooleanField()

class PostResource(Resource):
    document = Post
    related_resources = {
        'content': ContentResource,
        'sections': ContentResource, #nested complex objects
    }
    filters = {
        'title': [ops.Exact, ops.Startswith],
        'author_id': [ops.Exact],
        'is_published': [ops.Boolean],
    }
    rename_fields = {
        'author': 'author_id',
    }

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

from flask.ext.wtf import TextField, length
class TestDocument(db.Document):
    name = db.StringField()
    other = db.StringField()
    dictfield = db.DictField()
    is_new = db.BooleanField()

from flask.ext.mongoengine.wtf.orm import model_form
TestBaseForm = model_form(TestDocument)

class TestForm(TestBaseForm):
    name = TextField(validators=[length(min=3, max=8)])

class TestResource(Resource):
    form = TestForm
    document = TestDocument

class TestFormResource(Resource):
    form = TestForm
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

@api.register(name='testform', url='/testform/')
class TestFormView(ResourceView):
    resource = TestFormResource
    methods = [Create, Update, Fetch, List]


@api.register(name='testfields', url='/testfields/')
class TestFieldsResource(ResourceView):
    resource = TestFieldsResource
    methods = [Create, Update, Fetch, List]


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
