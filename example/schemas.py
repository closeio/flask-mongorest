from cleancat import *

from example import documents

class Language(Schema):
    name = String()

class Person(Schema):
    name = String()
    languages = List(MongoEmbeddedReference(documents.Language, Language), required=False)
