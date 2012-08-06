
class MongoRestException(Exception):
    pass

class OperatorNotAllowed(MongoRestException):
    def __init__(self, operator_name):
        self.op_name = operator_name 
    def __unicode__(self):
        return u'"'+self.op_name+'" is not a valid operator name.'

class InvalidFilter(MongoRestException):
    pass
 
class ValidationError(MongoRestException):
    pass


