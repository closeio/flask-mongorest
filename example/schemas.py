# -*- coding: utf-8 -*-

from cleancat import *
from cleancat.mongo import MongoEmbeddedReference, MongoReference

from example import documents


class User(Schema):
    email = Email(required=False)
    first_name = String(required=False)
    last_name = String(required=False)
    emails = List(Email(), required=False)
    datetime = DateTime(regex_message=u"Invalid date 💩", required=False)
    datetime_local = DateTime(required=False)
    balance = Integer(required=False)


class Content(Schema):
    text = String()
    lang = String()


class Post(Schema):
    title = String()
    description = String(required=False)
    author = MongoReference(documents.User, required=False)
    editor = MongoReference(documents.User, required=False)
    tags = List(String(), required=False)
    user_lists = List(MongoReference(documents.User), required=False)
    sections = List(MongoEmbeddedReference(documents.Content, Content), required=False)
    content = MongoEmbeddedReference(documents.Content, Content, required=False)
    is_published = Bool()


class Language(Schema):
    name = String()


class Person(Schema):
    name = String()
    languages = List(
        MongoEmbeddedReference(documents.Language, Language), required=False
    )


class DateTime(Schema):
    datetime = DateTime()
