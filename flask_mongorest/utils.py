import json
import decimal
import datetime
from bson.dbref import DBRef
from bson.objectid import ObjectId
import mongoengine

isbound = lambda m: getattr(m, 'im_self', None) is not None

def isint(int_str):
    try:
        int(int_str)
        return True
    except (TypeError, ValueError):
        return False

class MongoEncoder(json.JSONEncoder):
    def default(self, value, **kwargs):
        if isinstance(value, ObjectId):
            return str(value)
        if isinstance(value, DBRef):
            return value.id
        if isinstance(value, datetime.datetime):
            return value.isoformat()
        if isinstance(value, datetime.date):
            return value.strftime("%Y-%m-%d")
        if isinstance(value, decimal.Decimal):
            return str(value)
        return super(MongoEncoder, self).default(value, **kwargs)

try:
    cmp
except NameError: # Python 3
    cmp = lambda a, b: (a>b)-(a<b)

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

def equal(a, b):
    """
    Compares two objects. In addition to the "==" operator, this function
    ensures that the data of two mongoengine objects is the same. Also, it
    assumes that a UTC-TZ-aware datetime is equal to an unaware datetime if
    the date and time components match.
    """

    # When comparing dicts (we serialize documents using to_dict) or lists
    # we may encounter datetime instances in the values, so compare them item
    # by item.
    if isinstance(a, dict) and isinstance(b, dict):
        if sorted(a.keys()) != sorted(b.keys()):
            return False
        for k, v in a.items():
            if not equal(b[k], v):
                return False
        return True

    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all([equal(m, n) for (m, n) in zip(a, b)])

    # Two mongoengine objects are equal if their ID is equal. However,
    # in this case we want to check if the data is equal. Note this
    # doesn't look into mongoengine documents which are nested within
    # mongoengine documents.
    if isinstance(a, mongoengine.Document) and isinstance(b, mongoengine.Document):
        # Don't evaluate lazy documents
        if getattr(a, '_lazy', False) and getattr(b, '_lazy', False):
            return True
        return equal(dict(a.to_mongo()), dict(b.to_mongo()))

    # Since comparing an aware and unaware datetime results in an
    # exception and we may assign unaware datetimes to objects that
    # previously had an aware datetime, we convert aware datetimes
    # to their unaware equivalent before comparing.
    if isinstance(a, datetime.datetime) and isinstance(b, datetime.datetime):
        # This doesn't cover all the cases, but it covers the most
        # important case where the utcoffset is 0.
        if a.utcoffset() is not None and a.utcoffset() == datetime.timedelta(0):
            a = a.replace(tzinfo=None)
        if b.utcoffset() is not None and b.utcoffset() == datetime.timedelta(0):
            b = b.replace(tzinfo=None)

    try:
        return a == b
    except: # Exception during comparison, mainly datetimes.
        return False
