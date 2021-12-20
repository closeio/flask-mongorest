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
METHODS_TYPE = typing.Union[
    typing.Type[Create],
    typing.Type[Update],
    typing.Type[BulkUpdate],
    typing.Type[Fetch],
    typing.Type[List],
    typing.Type[Delete],
]
