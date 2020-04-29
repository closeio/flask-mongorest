import sys
import inspect

class Fetch:
    method = 'GET'

class Create:
    method = 'POST'

class Update:
    method = 'PUT'

class Delete:
    method = 'DELETE'


class BulkFetch:
    method = 'GET'

class BulkCreate:
    method = 'POST'

class BulkUpdate:
    method = 'PUT'

class BulkDelete:
    method = 'DELETE'


class Download:
    method = 'GET'

members = inspect.getmembers(sys.modules[__name__], inspect.isclass)
__all__ = [m[0] for m in members]
