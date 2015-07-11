Flask-MongoRest [![Build Status](https://secure.travis-ci.org/closeio/flask-mongorest.png?branch=master)](http://travis-ci.org/closeio/flask-mongorest)
===============
A Restful API framework wrapped around MongoEngine.

Setup
=====

``` python
from flask import Flask
from flask.ext.mongoengine import MongoEngine
from flask.ext.mongorest import MongoRest
from flask.ext.mongorest.views import ResourceView
from flask.ext.mongorest.resources import Resource
from flask.ext.mongorest import operators as ops
from flask.ext.mongorest import methods  


app = Flask(__name__)

app.config.update(
    MONGODB_HOST = 'localhost',
    MONGODB_PORT = '27017',
    MONGODB_DB = 'mongorest_example_app',
)

db = MongoEngine(app)
api = MongoRest(app)

class User(db.Document):
    email = db.EmailField(unique=True, required=True)

class Content(db.EmbeddedDocument):
    text = db.StringField()

class ContentResource(Resource):
    document = Content

class Post(db.Document):
    title = db.StringField(max_length=120, required=True)
    author = db.ReferenceField(User)
    content = db.EmbeddedDocumentField(Content)

class PostResource(Resource):
    document = Post
    related_resources = {
        'content': ContentResource,
    }
    filters = {
        'title': [ops.Exact, ops.Startswith],
        'author_id': [ops.Exact],
    }
    rename_fields = {
        'author': 'author_id',
    }

@api.register(name='posts', url='/posts/')
class PostView(ResourceView):
    resource = PostResource
    methods = [methods.Create, methods.Update, methods.Fetch, methods.List]
```

With this app, following cURL commands could be used:
```
Create a Post:
curl -H "Content-Type: application/json" -X POST -d \
'{"title": "First post!", "author_id": "author_id_from_a_previous_api_call", "content": {"text": "this is our test post content"}}' http://0.0.0.0:5000/posts/
{
  "id": "1",
  "title": "First post!",
  "author_id": "author_id_from_a_previous_api_call",
  "content": {
    "text": "this is our test post content"
  }
} 
```
Get a Post:
```
curl http://0.0.0.0:5000/posts/1/
{
  "id": "1",
  "title": "First post!",
  "author_id": "author_id_from_a_previous_api_call",
  "content": {
    "text": "this is our test post content"
  }
} 
```
List all Posts or filter by the title:
```
curl http://0.0.0.0:5000/posts/ or curl http://0.0.0.0:5000/posts/?title__startswith=First%20post
{
  "data": [
    {
      "id": "1",
      "title": "First post!",
      "author_id": "author_id_from_a_previous_api_call",
      "content": {
        "text": "this is our test post content"
      }
    },
    ... other posts
  ]
}
```
Delete a Post:
```
curl -X DELETE http://0.0.0.0:5000/posts/1/
# Fails since PostView.methods does not allow Delete
```

Request Params
==============

**_skip** and **_limit** => utilize the built-in functions of mongodb.

**_fields** => limit the response's fields to those named here (comma separated).

**_order_by** => order results if this string is present in the Resource.allowed_ordering list.  


Resource Configuration
======================

**rename_fields** => dict of renaming rules.  Useful for mapping _id fields such as "organization": "organization_id"

**filters** => filter results of a List request using the allowed filters which are used like `/user/?id__gt=2` or `/user/?email__exact=a@b.com`

**related_resources** => nested resource serialization for reference/embedded fields of a document

**child_document_resources** => Suppose you have a Person base class which has Male and Female subclasses.  These subclasses and their respective resources share the same MongoDB collection, but have different fields and serialization characteristics.  This dictionary allows you to map class instances to their respective resources to be used during serialization.

Authentication
==============
The AuthenticationBase class provides the ability for application's to implement their own API auth.  Two common patterns are shown below along with a BaseResourceView which can be used as the parent View of all of your app's resources.
``` python
class SessionAuthentication(AuthenticationBase):
    def authorized(self):
        return current_user.is_authenticated()

class ApiKeyAuthentication(AuthenticationBase):
    """
    @TODO ApiKey document and key generation left to the specific implementation
    """
    def authorized(self):
        if 'AUTHORIZATION' in request.headers:
            authorization = request.headers['AUTHORIZATION'].split()
            if len(authorization) == 2 and authorization[0].lower() == 'basic':
                try:
                    authorization_parts = base64.b64decode(authorization[1]).partition(':')
                    key = smart_unicode(authorization_parts[0])
                    api_key = ApiKey.objects.get(key__exact=key)
                    if api_key.user:
                        login_user(api_key.user)
                        setattr(current_user, 'api_key', api_key)
                    return True
                except (TypeError, UnicodeDecodeError, ApiKey.DoesNotExist):
                    pass
        return False

class BaseResourceView(ResourceView):
    authentication_methods = [SessionAuthentication, ApiKeyAuthentication]
```

Running the test suite
======================
This package uses nosetests for automated testing. Just run `python setup.py nosetests` to run the tests. No setup or any other prep needed.

Contributing
============
Pull requests are greatly appreciated!
