import json
import datetime
from bson.dbref import DBRef
from bson.objectid import ObjectId
from mongoengine.base import BaseDocument

callable = lambda o: hasattr(o, '__call__')

class MongoEncoder(json.JSONEncoder):
    def default(self, value, **kwargs):
        if isinstance(value, ObjectId):
            return unicode(value)
        elif isinstance(value, DBRef):
            return value.id
        elif callable(value):
            return value()
        if isinstance(value, datetime.datetime):
            return value.isoformat()
        return json.JSONEncoder.default(value, **kwargs)
