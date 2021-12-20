import typing


class Create:
    method = "POST"


class Update:
    method = "PUT"


class BulkUpdate:
    method = "PUT"


class Fetch:
    method = "GET"


class List:
    method = "GET"


class Delete:
    method = "DELETE"


# type alias
METHODS_TYPE = typing.Union[Create, Update, BulkUpdate, Fetch, List, Delete]
