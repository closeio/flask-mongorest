from mongoengine import *

class DateTime(Document):
    datetime = DateTimeField()

class Language(Document):
    name = StringField()

class Person(Document):
    name = StringField()
    languages = ListField(ReferenceField(Language))
