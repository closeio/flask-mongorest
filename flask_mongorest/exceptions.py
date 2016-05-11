
class MongoRestException(Exception):
    def __init__(self, message):
        self._message = message

    def _get_message(self):
        return self._message

    def _set_message(self, message):
        self._message = message

    message = property(_get_message, _set_message)

class OperatorNotAllowed(MongoRestException):
    def __init__(self, operator_name):
        self.op_name = operator_name

    def __unicode__(self):
        return u'"'+self.op_name+'" is not a valid operator name.'

class InvalidFilter(MongoRestException):
    pass

class ValidationError(MongoRestException):
    pass

class UnknownFieldError(Exception):
    pass

