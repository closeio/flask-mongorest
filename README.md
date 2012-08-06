Flask-MongoRest
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
    first_name = db.StringField()
    last_name = db.StringField()
    email = db.EmailField()

class UserResource(Resource):
    document = User

@api.register()
class UserView(ResourceView):
    resource = UserResource
    methods = [methods.Create, methods.Update, methods.Fetch, methods.List, methods.Delete]    
    
```
You can then submit GET, POST, PUT, and DELETE requests to the User endpoint located at '/user/'.

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


Contributing
============
Pull requests are greatly appreciated!
