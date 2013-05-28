import json
import decimal
import datetime
from bson.dbref import DBRef
from bson.objectid import ObjectId
from mongoengine.base import BaseDocument

isbound = lambda m: getattr(m, 'im_self', None) is not None

class MongoEncoder(json.JSONEncoder):
    def default(self, value, **kwargs):
        if isinstance(value, ObjectId):
            return unicode(value)
        elif isinstance(value, DBRef):
            return value.id
        if isinstance(value, datetime.datetime):
            return value.isoformat()
        if isinstance(value, datetime.date):
            return value.strftime("%Y-%m-%d")
        if isinstance(value, decimal.Decimal):
            return str(value)
        return super(MongoEncoder, self).default(value, **kwargs)
