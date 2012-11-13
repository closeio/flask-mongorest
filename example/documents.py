from mongoengine import *

class Language(Document):
    name = StringField()

class Person(Document):
    name = StringField()
    languages = ListField(ReferenceField(Language))
