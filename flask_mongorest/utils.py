import json
import decimal
import datetime
from bson.dbref import DBRef
from bson.objectid import ObjectId
from mongoengine.base import BaseDocument

isbound = lambda m: getattr(m, 'im_self', None) is not None

def isint(int_str):
    try:
        int(int_str)
        return True
    except ValueError:
        return False

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

def cmp_fields(ordering):
    # Takes a list of fields and directions and returns a
    # comparison function for sorted() to perform client-side
    # sorting.
    # Example: sorted(objs, cmp_fields([('date_created', -1)]))
    def _cmp(x, y):
        for field, direction in ordering:
            result = cmp(getattr(x, field), getattr(y, field)) * direction
            if result:
                return result
        return 0
    return _cmp
