# -*- coding: utf-8 -*-

import json
import copy
import datetime
import unittest
import example.app as example
from mongoengine.context_managers import query_counter
from mongoengine.errors import ValidationError

try:
    from mongoengine import SafeReferenceField
except ImportError:
    SafeReferenceField = None


# HACK:
# Because mongoengine doesn't allow you to customize the connection alias, and
# because flask_mongoengine uses a different DEFAULT_CONNECTION_NAME from
# mongoengine, we need to override this method to use flask_mongoengine's
# get_db() method instead of mongoengine's get_db() method.
try:
    from flask_mongoengine import get_db

    class query_counter(query_counter):
        def __init__(self):
            self.counter = 0
            self.db = get_db()
except ImportError:
    # Older versions of flask-mongoengine don't have this issue.
    pass


def response_success(response, code=None):
    if code is None:
        assert 200 <= response.status_code < 300, 'Received %d response: %s' % (response.status_code, response.data)
    else:
        assert code == response.status_code, 'Received %d response: %s' % (response.status_code, response.data)

def response_error(response, code=None):
    if code is None:
        assert 400 <= response.status_code < 500, 'Received %d response: %s' % (response.status_code, response.data)
    else:
        assert code == response.status_code, 'Received %d response: %s' % (response.status_code, response.data)

def compare_req_resp(req_obj, resp_obj):
    for k,v in req_obj.items():
        assert k in resp_obj.keys(), 'Key %r not in response (keys are %r)' % (k, resp_obj.keys())
        assert resp_obj[k] == v, 'Value for key %r should be %r but is %r' % (k, v, resp_obj[k])

def resp_json(resp):
    return json.loads(resp.get_data(as_text=True))


class MongoRestTestCase(unittest.TestCase):

    def setUp(self):
        self.user_1 = {
            'email': '1@b.com',
            'first_name': 'alan',
            'last_name': 'baker',
            'datetime': '2012-10-09T10:00:00',
        }

        self.user_2 = {
            'email': '2@b.com',
            'first_name': 'olivia',
            'last_name': 'baker',
            'datetime': '2012-11-09T11:00:00',
        }

        self.post_1 = {
            'title': 'first post!',
            #author
            #editor
            'tags': ['tag1', 'tag2', 'tag3'],
            #user_lists
            'sections': [
                {'text': 'this is the first section of the first post.',
                 'lang': 'en'},
                {'text': 'this is the second section of the first post.',
                 'lang': 'de'},
                {'text': 'this is the third section of the first post.',
                 'lang': 'fr'},
            ],
            'content': {
                'text': 'this is the content for my first post.',
                'lang': 'cn',
            },
            'is_published': True,
        }

        self.post_2 = {
            'title': 'Second post',
            'is_published': False,
        }

        self.app = example.app.test_client()
        example.documents.User.drop_collection()
        example.documents.Post.drop_collection()
        example.TestDocument.drop_collection()
        example.A.drop_collection()
        example.B.drop_collection()
        example.C.drop_collection()
        example.MethodTestDoc.drop_collection()
        example.DictDoc.drop_collection()

        # create user 1
        resp = self.app.post('/user/', data=json.dumps(self.user_1))
        response_success(resp)
        self.user_1_obj = resp_json(resp)
        compare_req_resp(self.user_1, self.user_1_obj)

        # create user 2
        resp = self.app.post('/user/', data=json.dumps(self.user_2))
        response_success(resp)
        self.user_2_obj = resp_json(resp)
        compare_req_resp(self.user_2, self.user_2_obj)

    def tearDown(self):
        # delete user 1
        resp = self.app.delete('/user/%s/' % self.user_1_obj['id'])
        response_success(resp)
        resp = self.app.get('/user/%s/' % self.user_1_obj['id'])
        response_error(resp, code=404)

        # delete user 2
        resp = self.app.delete('/user/%s/' % self.user_2_obj['id'])
        response_success(resp)
        resp = self.app.get('/user/%s/' % self.user_2_obj['id'])
        response_error(resp, code=404)

    def test_update_user(self):
        self.user_1_obj['first_name'] = 'anthony'
        self.user_1_obj['datetime'] = datetime.datetime.utcnow().isoformat()
        resp = self.app.put('/user/%s/' % self.user_1_obj['id'], data=json.dumps(self.user_1_obj))
        response_success(resp)

        # check for request params in response, except for date (since the format will differ)
        data_to_check = copy.copy(self.user_1_obj)
        del data_to_check['datetime']
        data = resp_json(resp)
        compare_req_resp(data_to_check, data)

        # response from PUT should be completely identical as a subsequent GET
        # (including precision of datetimes)
        resp = self.app.get('/user/%s/' % self.user_1_obj['id'])
        data2 = resp_json(resp)
        self.assertEqual(data, data2)

    def test_unicode(self):
        """
        Make sure unicode data payloads are properly decoded.
        """
        self.user_1_obj['first_name'] = u'Jörg'

        # Don't encode unicode characters
        resp = self.app.put('/user/%s/' % self.user_1_obj['id'], data=json.dumps(self.user_1_obj, ensure_ascii=False))
        response_success(resp)
        data = resp_json(resp)
        compare_req_resp(self.user_1_obj, data)

        # Encode unicode characters as "\uxxxx" (default)
        resp = self.app.put('/user/%s/' % self.user_1_obj['id'], data=json.dumps(self.user_1_obj, ensure_ascii=True))
        response_success(resp)
        data = resp_json(resp)
        compare_req_resp(self.user_1_obj, data)

    def test_model_validation_unicode(self):
        # MongoEngine validation error (no schema)
        resp = self.app.post('/test/', data=json.dumps({
            'email': u'💩',
        }))
        response_error(resp)
        errors = resp_json(resp)
        self.assertTrue(errors == {
            'field-errors': {
                'email': u'Invalid email address: 💩'
            }
        } or errors == {
            # Workaround for
            # https://github.com/MongoEngine/mongoengine/pull/1384
            'field-errors': {
                'email': u'Invalid Mail-address: 💩'
            }
        })

        # Schema validation error
        resp = self.app.post('/user/', data=json.dumps({
            'email': 'test@example.com',
            'datetime': 'invalid',
        }))
        response_error(resp)
        errors = resp_json(resp)
        self.assertEqual(errors, {
            'errors': [],
            'field-errors': {
                'datetime': u'Invalid date 💩'
            }
        })

    def test_model_validation(self):
        resp = self.app.post('/user/', data=json.dumps({
            'email': 'invalid',
            'first_name': 'joe',
            'last_name': 'baker',
            'datetime':'2012-08-13T05:25:04.362Z',
            'datetime_local':'2012-08-13T05:25:04.362-03:30'
        }))
        response_error(resp)
        errors = resp_json(resp)
        self.assertTrue('field-errors' in errors)
        self.assertEqual(set(errors['field-errors']), set(['email']))

        resp = self.app.put('/user/%s/' % self.user_1_obj['id'], data=json.dumps({
            'email': 'invalid',
            'first_name': 'joe',
            'last_name': 'baker',
        }))
        response_error(resp)
        errors = resp_json(resp)
        self.assertTrue('field-errors' in errors)
        self.assertEqual(set(errors['field-errors']), set(['email']))

        resp = self.app.put('/user/%s/' % self.user_1_obj['id'], data=json.dumps({
            'emails': ['one@example.com', 'invalid', 'second@example.com', 'invalid2'],
        }))

        response_error(resp)
        errors = resp_json(resp)
        self.assertTrue('field-errors' in errors)
        self.assertEqual(set(errors['field-errors']), set(['emails']))
        self.assertEqual(set(errors['field-errors']['emails']['errors']), set(['1', '3']))

    def test_resource_fields(self):
        resp = self.app.post('/testfields/', data=json.dumps({
            'name': 'thename',
            'other': 'othervalue',
            'upper_name': 'INVALID',
        }))
        response_success(resp)
        obj = resp_json(resp)

        self.assertEqual(set(obj), set(['id', 'name', 'upper_name']))
        self.assertEqual(obj['name'], 'thename')
        self.assertEqual(obj['upper_name'], 'THENAME')

        resp = self.app.get('/test/%s/' % obj['id'])
        response_success(resp)
        obj = resp_json(resp)

        self.assertEqual(obj['name'], 'thename')
        # We can edit all the fields since we don't have a schema
        #self.assertEqual(obj['other'], None)

        resp = self.app.put('/test/%s/' % obj['id'], data=json.dumps({
            'other': 'new othervalue',
        }))
        response_success(resp)
        obj = resp_json(resp)
        self.assertEqual(obj['name'], 'thename')
        self.assertEqual(obj['other'], 'new othervalue')

        resp = self.app.put('/testfields/%s/' % obj['id'], data=json.dumps({
            'name': 'namevalue2',
            'upper_name': 'INVALID',
        }))
        response_success(resp)
        obj = resp_json(resp)
        self.assertEqual(obj['name'], 'namevalue2')
        self.assertEqual(obj['upper_name'], 'NAMEVALUE2')

    def test_restricted_auth(self):
        self.post_1['author_id'] = self.user_1_obj['id']
        self.post_1['editor'] = self.user_2_obj['id']
        self.post_1['user_lists'] = [self.user_1_obj['id'], self.user_2_obj['id']]

        resp = self.app.get('/user/')
        objs = resp_json(resp)['data']
        self.assertEqual(len(objs), 2)

        post = self.post_1.copy()

        # Try to create an already published Post
        post["is_published"] = True
        resp = self.app.post('/restricted/', data=json.dumps(post))
        # Not allowed, must be added in unpublished state
        response_success(resp, code=401)

        # Try again, but with is_published set to False
        post["is_published"] = False
        resp = self.app.post('/restricted/', data=json.dumps(post))
        # Should be OK
        response_success(resp, code=200)

        # Get data about the Post we just POSTed
        data = resp_json(resp)

        # Look at current number of posts through an unrestricted view
        resp = self.app.get('/posts/')
        tmp = resp_json(resp)
        nposts = len(tmp["data"])
        # Should see 2
        self.assertEqual(2, nposts)

        # extra data returned in get_objects
        self.assertEqual(tmp['more'], 'stuff')

        # Now look at posts through a restricted view
        resp = self.app.get('/restricted/')
        tmp = resp_json(resp)
        npubposts = len(tmp["data"])
        # Should only see 1 (published)
        self.assertEqual(1, npubposts)

        # Try to change the title
        post["title"] = "New title"
        resp = self.app.put('/restricted/%s/' % (str(data["id"],)),
                            data=json.dumps(post))
        # Works because we haven't published it yet
        response_success(resp, code=200)

        # Now let's publish it
        post["is_published"] = True
        resp = self.app.put('/restricted/%s/' % (str(data["id"],)),
                            data=json.dumps(post))
        # This works because the object we are changing is still
        # in the unpublished state before we update it
        response_success(resp, code=200)

        # Now change the title again
        post["title"] = "Another title"
        resp = self.app.put('/restricted/%s/' % (str(data["id"],)),
                            data=json.dumps(post))
        # Can't do it, object has already been published
        response_success(resp, code=401)

        # Try to delete this post
        resp = self.app.delete('/restricted/%s/' % (str(data["id"],)),
                               data=json.dumps(post))
        # Again, won't work because it was already published
        response_success(resp, code=401)

        # OK, let's create another post
        post = self.post_1.copy()

        # Create it in the unpublished state
        post["is_published"] = False
        resp = self.app.post('/restricted/', data=json.dumps(post))
        # Should work
        response_success(resp, code=200)

        data = resp_json(resp)

        # Now let's try and delete an unpublished post
        resp = self.app.delete('/restricted/%s/' % (data["id"],),
                               data=json.dumps(post))
        # Should work
        response_success(resp, code=200)

    def test_get(self):
        resp = self.app.get('/user/')
        objs = resp_json(resp)['data']
        self.assertEqual(len(objs), 2)

    def test_get_primary_user(self):
        self.post_1['author_id'] = self.user_1_obj['id']
        self.post_1['editor'] = self.user_2_obj['id']
        self.post_1['user_lists'] = [self.user_1_obj['id'], self.user_2_obj['id']]
        resp = self.app.post('/posts/', data=json.dumps(self.post_1))
        resp = self.app.get('/posts/?_include_primary_user=1')
        objs = resp_json(resp)['data']
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0]['title'], 'first post!')
        self.assertTrue(len(objs[0]['primary_user']) > 0)

    def test_get_empty_primary_user(self):
        resp = self.app.post('/posts/', data=json.dumps(self.post_2))
        resp = self.app.get('/posts/?_include_primary_user=1')
        objs = resp_json(resp)['data']
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0]['title'], 'Second post')
        self.assertEqual(objs[0]['primary_user'], None)

    def test_post(self):
        self.post_1['author_id'] = self.user_1_obj['id']
        self.post_1['editor'] = self.user_2_obj['id']
        self.post_1['user_lists'] = [self.user_1_obj['id'], self.user_2_obj['id']]
        resp = self.app.post('/posts/', data=json.dumps(self.post_1))
        response_success(resp)
        compare_req_resp(self.post_1, resp_json(resp))
        self.post_1_obj = resp_json(resp)
        resp = self.app.get('/posts/%s/' % self.post_1_obj['id'])
        response_success(resp)
        compare_req_resp(self.post_1_obj, resp_json(resp))

        self.post_1_obj['author_id'] = self.user_2_obj['id']
        resp = self.app.put('/posts/%s/' % self.post_1_obj['id'], data=json.dumps(self.post_1_obj))
        response_success(resp)
        jd = resp_json(resp)
        self.assertEqual(self.post_1_obj['author_id'], jd["author_id"])

        response_success(resp)
        compare_req_resp(self.post_1_obj, resp_json(resp))
        self.post_1_obj = resp_json(resp)

        resp = self.app.post('/posts/', data=json.dumps(self.post_2))
        response_success(resp)
        compare_req_resp(self.post_2, resp_json(resp))
        self.post_2_obj = resp_json(resp)

        #test filtering

        resp = self.app.get('/posts/?title__startswith=first')
        response_success(resp)
        data_list = resp_json(resp)['data']
        compare_req_resp(self.post_1_obj, data_list[0])

        resp = self.app.get('/posts/?title__startswith=second')
        response_success(resp)
        data_list = resp_json(resp)['data']
        self.assertEqual(data_list, [])

        resp = self.app.get('/posts/?title__in=%s,%s' % (self.post_1_obj['title'], self.post_2_obj['title']))
        response_success(resp)
        posts = resp_json(resp)
        self.assertEqual(len(posts['data']), 2)

        resp = self.app.get('/posts/?title__in=')
        response_success(resp)
        posts = resp_json(resp)
        self.assertEqual(len(posts['data']), 0)

        resp = self.app.get('/user/?datetime=%s' % '2012-10-09 10:00:00')
        response_success(resp)
        users = resp_json(resp)
        self.assertEqual(len(users['data']), 1)

        resp = self.app.get('/user/?datetime__gt=%s' % '2012-10-08 10:00:00')
        response_success(resp)
        users = resp_json(resp)
        self.assertEqual(len(users['data']), 2)

        resp = self.app.get('/user/?datetime__gte=%s' % '2012-10-09 10:00:00')
        response_success(resp)
        users = resp_json(resp)
        self.assertEqual(len(users['data']), 2)

        # test negation

        # exclude many
        resp = self.app.get('/posts/?title__not__in=%s,%s' % (self.post_1_obj['title'], self.post_2_obj['title']))
        response_success(resp)
        posts = resp_json(resp)
        self.assertEqual(len(posts['data']), 0)

        # exclude one
        resp = self.app.get('/posts/?title__not__in=%s' % (self.post_1_obj['title']))
        response_success(resp)
        posts = resp_json(resp)
        self.assertEqual(len(posts['data']), 1)

        resp = self.app.get('/posts/?author_id=%s' % self.user_2_obj['id'])
        response_success(resp)
        data_list = resp_json(resp)['data']
        compare_req_resp(self.post_1_obj, data_list[0])

        resp = self.app.get('/posts/?is_published=true')
        response_success(resp)
        data_list = resp_json(resp)['data']
        self.assertEqual(len(data_list), 1)
        compare_req_resp(self.post_1_obj, data_list[0])

        resp = self.app.get('/posts/?is_published=false')
        response_success(resp)
        data_list = resp_json(resp)['data']
        self.assertEqual(len(data_list), 1)
        compare_req_resp(self.post_2_obj, data_list[0])

        # default exact filtering
        resp = self.app.get('/posts/?title__exact=first post!')
        data_list_1 = resp_json(resp)['data']
        resp = self.app.get('/posts/?title=first post!')
        data_list_2 = resp_json(resp)['data']
        self.assertEqual(data_list_1, data_list_2)

        # test bulk update
        resp = self.app.put('/posts/?title__startswith=first', data=json.dumps({
            'description': 'Some description'
        }))
        response_success(resp)
        data = resp_json(resp)
        self.assertEqual(data['count'], 1)

        resp = self.app.put('/posts/', data=json.dumps({
            'description': 'Other description'
        }))
        response_success(resp)
        data = resp_json(resp)
        self.assertEqual(data['count'], 2)

        resp = self.app.get('/posts/')
        response_success(resp)
        data_list = resp_json(resp)['data']
        self.assertEqual(data_list[0]['description'], 'Other description')
        self.assertEqual(data_list[1]['description'], 'Other description')

        resp = self.app.put('/posts/', data=json.dumps({
            'description': 'X'*121 # too long
        }))
        response_error(resp)
        data = resp_json(resp)
        self.assertEqual(data['count'], 0)
        self.assertEqual(set(data['field-errors']), set(['description']))

    def test_post_auto_art_tag(self):
        # create a post by vangogh and an 'art' tag should be added automatically

        # create vangogh
        resp = self.app.post('/user/', data=json.dumps({
            'email': 'vincent@vangogh.com',
            'first_name': 'Vincent',
            'last_name': 'Vangogh',
        }))
        response_success(resp)
        author = resp_json(resp)['id']

        # create a post
        resp = self.app.post('/posts/', data=json.dumps(self.post_1))
        response_success(resp)
        post = resp_json(resp)

        resp = self.app.put('/posts/%s/' % post['id'], data=json.dumps({
            'author_id': author
        }))
        response_success(resp)
        post = resp_json(resp)
        post_obj = example.documents.Post.objects.get(pk=post['id'])
        self.assertTrue('art' in post_obj.tags)
        self.assertTrue('art' in post['tags'])

    @unittest.skipIf(not SafeReferenceField, "SafeReferenceField not available")
    def test_broken_reference(self):
        # create a new user
        resp = self.app.post('/user/', data=json.dumps({
            'email': '3@b.com',
            'first_name': 'steve',
            'last_name': 'wiseman',
            'datetime': '2012-11-09T11:00:00',
        }))
        response_success(resp)
        user_3 = resp_json(resp)

        post = self.post_1.copy()
        post['author_id'] = self.user_1_obj['id']
        post['editor'] = self.user_2_obj['id']
        post['user_lists'] = [user_3['id']]
        resp = self.app.post('/posts/', data=json.dumps(post))
        response_success(resp)
        compare_req_resp(post, resp_json(resp))

        post = resp_json(resp)

        # remove the user and see if its reference is cleaned up properly
        resp = self.app.delete('/user/%s/' % user_3['id'])
        response_success(resp)

        resp = self.app.get('/posts/%s/' % post['id'])
        response_success(resp)

        self.assertEqual(resp_json(resp)['user_lists'], [])

        post['user_lists'] = []
        compare_req_resp(post, resp_json(resp))

    def test_dummy_auth(self):
        resp = self.app.get('/auth/')
        response_success(resp, code=401)

    def test_pagination(self):
        # create 101 posts
        post = self.post_1.copy()
        for i in range(1,102):
            post['title'] = 'Post #%d' %i
            resp = self.app.post('/posts/', data=json.dumps(post))
            response_success(resp)

        resp = self.app.get('/posts/?_limit=10')
        response_success(resp)
        data = resp_json(resp)
        self.assertEqual(len(data['data']), 10)
        self.assertEqual(data['has_more'], True)

        resp = self.app.get('/posts/?_skip=100')
        response_success(resp)
        data = resp_json(resp)
        self.assertEqual(len(data['data']), 1)
        self.assertEqual(data['has_more'], False)

        resp = self.app.get('/posts/?_limit=1')
        response_success(resp)
        data = resp_json(resp)
        self.assertEqual(len(data['data']), 1)
        self.assertEqual(data['has_more'], True)

        resp = self.app.get('/posts/?_limit=0')
        response_success(resp)
        data = resp_json(resp)
        self.assertEqual(len(data['data']), 0)
        self.assertEqual(data['has_more'], True)

        resp = self.app.get('/posts/?_skip=100&_limit=1')
        response_success(resp)
        data = resp_json(resp)
        self.assertEqual(len(data['data']), 1)
        self.assertEqual(data['has_more'], False)

        # default limit
        resp = self.app.get('/posts/')
        response_success(resp)
        data = resp_json(resp)
        self.assertEqual(len(data['data']), 100)

        # _limit > max_limit
        resp = self.app.get('/posts/?_limit=101')
        response_error(resp, code=400)
        data = resp_json(resp)
        self.assertEqual(data['error'], 'The limit you set is larger than the maximum limit for this resource (max_limit = 100).')

        # respect custom max_limit
        resp = self.app.get('/posts10/?_limit=11')
        response_error(resp, code=400)
        data = resp_json(resp)
        self.assertEqual(data['error'], 'The limit you set is larger than the maximum limit for this resource (max_limit = 10).')

        resp = self.app.get('/posts10/')
        response_success(resp)
        data = resp_json(resp)
        self.assertEqual(len(data['data']), 10)

        resp = self.app.get('/posts10/?_limit=5')
        response_success(resp)
        data = resp_json(resp)
        self.assertEqual(len(data['data']), 5)

        resp = self.app.get('/posts250/?_limit=251')
        response_error(resp, code=400)
        data = resp_json(resp)
        self.assertEqual(data['error'], 'The limit you set is larger than the maximum limit for this resource (max_limit = 250).')

        resp = self.app.get('/posts250/')
        response_success(resp)
        data = resp_json(resp)
        self.assertEqual(len(data['data']), 100)

        resp = self.app.get('/posts250/?_limit=10')
        response_success(resp)
        data = resp_json(resp)
        self.assertEqual(len(data['data']), 10)

    def test_garbage_args(self):
        resp = self.app.get('/posts/?_limit=garbage')
        response_error(resp, code=400)
        self.assertEqual(resp_json(resp)['error'],
                         '_limit must be an integer (got "garbage" instead).')

        resp = self.app.get('/posts/?_skip=garbage')
        response_error(resp, code=400)
        self.assertEqual(resp_json(resp)['error'],
                         '_skip must be an integer (got "garbage" instead).')

        resp = self.app.get('/posts/?_skip=-1')
        response_error(resp, code=400)
        self.assertEqual(resp_json(resp)['error'],
                         '_skip must be a non-negative integer (got "-1" instead).')

    def test_fields(self):
        resp = self.app.get('/user/%s/?_fields=email' % self.user_1_obj['id'])
        response_success(resp)
        user = resp_json(resp)
        self.assertEqual(set(user), set(['email']))

        resp = self.app.get('/user/%s/?_fields=first_name,last_name' % self.user_1_obj['id'])
        response_success(resp)
        user = resp_json(resp)
        self.assertEqual(set(user), set(['first_name', 'last_name']))

        # Make sure all fields can still be posted.
        test_user_data = {
            'email': 'u@example.com',
            'first_name': 'first',
            'last_name': 'first',
            'balance': 54,
        }

        resp = self.app.post('/user/?_fields=id', data=json.dumps(test_user_data))
        response_success(resp)
        user = resp_json(resp)
        self.assertEqual(set(user), set(['id']))

    def test_invalid_json(self):
        resp = self.app.post('/user/', data='{\"}')
        response_error(resp, code=400)
        resp = resp_json(resp)
        self.assertEqual(resp['error'], 'The request contains invalid JSON.')

    def test_chunked_request(self):
        resp = self.app.post('/a/', data=json.dumps({ 'txt': 'test' }), headers={'Transfer-Encoding': 'chunked'})
        response_error(resp, code=400)
        self.assertEqual(resp_json(resp), { 'error': 'Chunked Transfer-Encoding is not supported.' })

    # Original MongoEngine does not support assigning a string ID to a dbref
    # reference -- we'd have to use a schema.
    @unittest.skipIf(not SafeReferenceField, "SafeReferenceField not available")
    def test_dbref_vs_objectid(self):
        resp = self.app.post('/a/', data=json.dumps({ "txt": "some text 1" }))
        response_success(resp)
        a1 = resp_json(resp)

        resp = self.app.post('/a/', data=json.dumps({ "txt": "some text 2" }))
        response_success(resp)
        a2 = resp_json(resp)

        resp = self.app.post('/b/', data=json.dumps({ "ref": a1['id'], "txt": "text" }))
        response_success(resp)
        dbref_obj = resp_json(resp)

        resp = self.app.post('/c/', data=json.dumps({ "ref": a1['id'], "txt": "text" }))
        response_success(resp)
        objectid_obj = resp_json(resp)

        # compare objects with a dbref reference and an objectid reference
        resp = self.app.get('/b/{0}/'.format(dbref_obj['id']))
        response_success(resp)
        dbref_obj = resp_json(resp)

        resp = self.app.get('/c/{0}/'.format(objectid_obj['id']))
        response_success(resp)
        objectid_obj = resp_json(resp)

        self.assertEqual(dbref_obj['ref'], objectid_obj['ref'])
        self.assertEqual(dbref_obj['txt'], objectid_obj['txt'])

        # make sure both dbref and objectid are updated correctly
        resp = self.app.put('/b/{0}/'.format(dbref_obj['id']), data=json.dumps({ "ref": a2['id'] }))
        response_success(resp)

        resp = self.app.put('/c/{0}/'.format(objectid_obj['id']), data=json.dumps({ "ref": a2['id'] }))
        response_success(resp)

        resp = self.app.get('/b/{0}/'.format(dbref_obj['id']))
        response_success(resp)
        dbref_obj = resp_json(resp)

        resp = self.app.get('/c/{0}/'.format(objectid_obj['id']))
        response_success(resp)
        objectid_obj = resp_json(resp)

        self.assertEqual(dbref_obj['ref'], a2['id'])
        self.assertEqual(dbref_obj['ref'], objectid_obj['ref'])
        self.assertEqual(dbref_obj['txt'], objectid_obj['txt'])

    def test_view_methods(self):
        doc = example.ViewMethodTestDoc.objects.create(txt='doc1')

        resp = self.app.get('/test_view_method/%s/' % doc.pk)
        response_success(resp)
        self.assertEqual(resp_json(resp), {'method': 'Fetch'})

        resp = self.app.get('/test_view_method/')
        response_success(resp)
        self.assertEqual(resp_json(resp), {'method': 'List'})

        resp = self.app.post('/test_view_method/', data=json.dumps({
            'txt': 'doc2'
        }))
        response_success(resp)
        self.assertEqual(resp_json(resp), {'method': 'Create'})

        resp = self.app.put('/test_view_method/%s/' % doc.pk, data=json.dumps({
            'txt': 'doc1new'
        }))
        response_success(resp)
        self.assertEqual(resp_json(resp), {'method': 'Update'})

        resp = self.app.put('/test_view_method/', data=json.dumps({
            'txt': 'doc'
        }))
        response_success(resp)
        self.assertEqual(resp_json(resp), {'method': 'BulkUpdate'})

        resp = self.app.delete('/test_view_method/%s/' % doc.pk, data=json.dumps({
            'txt': 'doc'
        }))
        response_success(resp)
        self.assertEqual(resp_json(resp), {'method': 'Delete'})

    def test_methods_success(self):
        doc1 = example.MethodTestDoc.objects.create(txt='doc1')
        doc2 = example.MethodTestDoc.objects.create(txt='doc2')

        resp = self.app.get('/fetch_only/%s/' % doc1.pk)
        response_success(resp)

        resp = self.app.get('/list_only/')
        response_success(resp)

        resp = self.app.post('/create_only/', data=json.dumps({
            'txt': 'created'
        }))
        response_success(resp)

        resp = self.app.put('/update_only/%s/' % doc2.pk, data=json.dumps({
            'txt': 'works'
        }))
        response_success(resp)

        resp = self.app.put('/bulk_update_only/', data=json.dumps({
            'txt': 'both work'
        }))
        response_success(resp)

        resp = self.app.delete('/delete_only/%s/' % doc1.pk)
        response_success(resp)

    def test_fetch_method_permissions(self):
        doc1 = example.MethodTestDoc.objects.create(txt='doc1')

        # fetch
        resp = self.app.get('/fetch_only/%s/' % doc1.pk)
        response_success(resp)

        # list
        resp = self.app.get('/fetch_only/')
        response_error(resp, code=404)

        # create
        resp = self.app.post('/fetch_only/', data=json.dumps({
            'txt': 'doesnt work'
        }))
        response_error(resp, code=404)

        # put
        resp = self.app.put('/fetch_only/%s/' % doc1.pk, data=json.dumps({
            'txt': 'doesnt work'
        }))
        response_error(resp, code=405)

        # bulk put
        resp = self.app.put('/fetch_only/', data=json.dumps({
            'txt': 'doesnt work'
        }))
        response_error(resp, code=404)

        # delete
        resp = self.app.delete('/fetch_only/%s/' % doc1.pk)
        response_error(resp, code=405)

    def test_list_method_permissions(self):
        doc1 = example.MethodTestDoc.objects.create(txt='doc1')

        # list
        resp = self.app.get('/list_only/')
        response_success(resp)

        # fetch
        resp = self.app.get('/list_only/%s/' % doc1.pk)
        response_error(resp, code=405)

        # create
        resp = self.app.post('/list_only/', data=json.dumps({
            'txt': 'doesnt work'
        }))
        response_error(resp, code=405)

        # put
        resp = self.app.put('/list_only/%s/' % doc1.pk, data=json.dumps({
            'txt': 'doesnt work'
        }))
        response_error(resp, code=405)

        # bulk put
        resp = self.app.put('/list_only/', data=json.dumps({
            'txt': 'doesnt work'
        }))
        response_error(resp, code=405)

        # delete
        resp = self.app.delete('/list_only/%s/' % doc1.pk)
        response_error(resp, code=405)

    def test_create_method_permissions(self):
        doc1 = example.MethodTestDoc.objects.create(txt='doc1')

        # create
        resp = self.app.post('/create_only/', data=json.dumps({
            'txt': 'works'
        }))
        response_success(resp)

        # list
        resp = self.app.get('/create_only/')
        response_error(resp, code=405)

        # fetch
        resp = self.app.get('/create_only/%s/' % doc1.pk)
        response_error(resp, code=405)

        # put
        resp = self.app.put('/create_only/%s/' % doc1.pk, data=json.dumps({
            'txt': 'doesnt work'
        }))
        response_error(resp, code=405)

        # bulk put
        resp = self.app.put('/create_only/', data=json.dumps({
            'txt': 'doesnt work'
        }))
        response_error(resp, code=405)

        # delete
        resp = self.app.delete('/create_only/%s/' % doc1.pk)
        response_error(resp, code=405)

    def test_update_method_permissions(self):
        doc1 = example.MethodTestDoc.objects.create(txt='doc1')

        # put
        resp = self.app.put('/update_only/%s/' % doc1.pk, data=json.dumps({
            'txt': 'doesnt work'
        }))
        response_success(resp)

        # create
        resp = self.app.post('/update_only/', data=json.dumps({
            'txt': 'works'
        }))
        response_error(resp, code=404)

        # list
        resp = self.app.get('/update_only/')
        response_error(resp, code=404)

        # fetch
        resp = self.app.get('/update_only/%s/' % doc1.pk)
        response_error(resp, code=405)

        # bulk put
        resp = self.app.put('/update_only/', data=json.dumps({
            'txt': 'doesnt work'
        }))
        response_error(resp, code=404)

        # delete
        resp = self.app.delete('/update_only/%s/' % doc1.pk)
        response_error(resp, code=405)

    def test_bulk_update_method_permissions(self):
        doc1 = example.MethodTestDoc.objects.create(txt='doc1')

        # bulk put
        resp = self.app.put('/bulk_update_only/', data=json.dumps({
            'txt': 'works'
        }))
        response_success(resp)

        # put
        resp = self.app.put('/bulk_update_only/%s/' % doc1.pk, data=json.dumps({
            'txt': 'doesnt work'
        }))
        response_error(resp, code=405)

        # create
        resp = self.app.post('/bulk_update_only/', data=json.dumps({
            'txt': 'works'
        }))
        response_error(resp, code=405)

        # list
        resp = self.app.get('/bulk_update_only/')
        response_error(resp, code=405)

        # fetch
        resp = self.app.get('/bulk_update_only/%s/' % doc1.pk)
        response_error(resp, code=405)

        # delete
        resp = self.app.delete('/bulk_update_only/%s/' % doc1.pk)
        response_error(resp, code=405)

    def test_delete_method_permissions(self):
        doc1 = example.MethodTestDoc.objects.create(txt='doc1')

        # delete
        resp = self.app.delete('/delete_only/%s/' % doc1.pk)
        response_success(resp)

        # bulk put
        resp = self.app.put('/delete_only/', data=json.dumps({
            'txt': 'works'
        }))
        response_error(resp, code=404)

        # put
        resp = self.app.put('/delete_only/%s/' % doc1.pk, data=json.dumps({
            'txt': 'doesnt work'
        }))
        response_error(resp, code=405)

        # create
        resp = self.app.post('/delete_only/', data=json.dumps({
            'txt': 'works'
        }))
        response_error(resp, code=404)

        # list
        resp = self.app.get('/delete_only/')
        response_error(resp, code=404)

        # fetch
        resp = self.app.get('/delete_only/%s/' % doc1.pk)
        response_error(resp, code=405)

    def test_request_bad_accept(self):
        """Make sure we gracefully handle requests where an invalid Accept header is sent."""
        resp = self.app.get('/user/%s/' % self.user_1_obj['id'], headers={ 'Accept': 'whatever' })
        response_error(resp)
        self.assertEqual(resp.data, b'Invalid Accept header requested')

    def test_bulk_update_limit(self):
        """
        Make sure that the limit on the number of objects that can be
        bulk-updated at once works.
        """
        limit = example.PostResource.bulk_update_limit

        for i in range(limit+1):
            resp = self.app.post('/posts/', data=json.dumps({
                'title': 'Title %d' % i,
                'is_published': False
            }))
            response_success(resp)

        # bulk update all posts
        resp = self.app.put('/posts/', data=json.dumps({
            'title': 'Title'
        }))
        response_error(resp, code=400)
        self.assertEqual(resp_json(resp), {
            'errors': [
                "It's not allowed to update more than 10 objects at once"
            ]
        })
        self.assertEqual(11, example.documents.Post.objects.filter(title__ne='Title').count())


class MongoRestSchemaTestCase(unittest.TestCase):

    def setUp(self):
        self.app = example.app.test_client()
        example.documents.Language.drop_collection()
        example.documents.Person.drop_collection()

    def tearDown(self):
        pass

    def test_person(self):
        resp = self.app.post('/person/', data=json.dumps({
            'name': 'John',
            'languages': [
                { 'name': 'English' },
                { 'name': 'German' },
            ]
        }))
        response_success(resp)
        person = resp_json(resp)

        person_id = person['id']

        self.assertEqual(len(person['languages']), 2)
        self.assertEqual(person['name'], 'John')
        self.assertEqual(person['languages'][0]['name'], 'English')
        self.assertEqual(person['languages'][1]['name'], 'German')

        english_id = person['languages'][0]['id']
        german_id = person['languages'][1]['id']

        # No change (same data)
        resp = self.app.put('/person/%s/' % person_id, data=json.dumps({
            'name': 'John',
            'languages': [
                { 'id': english_id, 'name': 'English' },
                { 'id': german_id, 'name': 'German' },
            ]
        }))
        response_success(resp)
        person = resp_json(resp)
        self.assertEqual(len(person['languages']), 2)
        self.assertEqual(person['name'], 'John')
        self.assertEqual(person['languages'][0]['id'], english_id)
        self.assertEqual(person['languages'][1]['id'], german_id)
        self.assertEqual(person['languages'][0]['name'], 'English')
        self.assertEqual(person['languages'][1]['name'], 'German')

        # No change (omitted fields of related document)
        resp = self.app.put('/person/%s/' % person_id, data=json.dumps({
            'name': 'John',
            'languages': [
                { 'id': english_id },
                { 'id': german_id },
            ]
        }))
        response_success(resp)
        person = resp_json(resp)
        self.assertEqual(len(person['languages']), 2)
        self.assertEqual(person['name'], 'John')
        self.assertEqual(person['languages'][0]['id'], english_id)
        self.assertEqual(person['languages'][1]['id'], german_id)
        self.assertEqual(person['languages'][0]['name'], 'English')
        self.assertEqual(person['languages'][1]['name'], 'German')

        # Also no change (empty data)
        resp = self.app.put('/person/%s/' % person_id, data=json.dumps({ }))
        response_success(resp)
        person = resp_json(resp)
        self.assertEqual(len(person['languages']), 2)
        self.assertEqual(person['name'], 'John')
        self.assertEqual(person['languages'][0]['id'], english_id)
        self.assertEqual(person['languages'][1]['id'], german_id)
        self.assertEqual(person['languages'][0]['name'], 'English')
        self.assertEqual(person['languages'][1]['name'], 'German')

        # Change value
        resp = self.app.put('/person/%s/' % person_id, data=json.dumps({
            'languages': [
                { 'id': english_id, 'name': 'English' },
                { 'id': german_id, 'name': 'French' },
            ]
        }))
        response_success(resp)
        person = resp_json(resp)
        self.assertEqual(len(person['languages']), 2)
        self.assertEqual(person['name'], 'John')
        self.assertEqual(person['languages'][0]['id'], english_id)
        self.assertEqual(person['languages'][1]['id'], german_id)
        self.assertEqual(person['languages'][0]['name'], 'English')
        self.assertEqual(person['languages'][1]['name'], 'French')

        # Insert item / rename back
        resp = self.app.put('/person/%s/' % person_id, data=json.dumps({
            'languages': [
                { 'id': english_id },
                { 'name': 'Spanish' },
                { 'id': german_id, 'name': 'German' },
            ]
        }))
        response_success(resp)
        person = resp_json(resp)
        self.assertEqual(len(person['languages']), 3)
        self.assertEqual(person['name'], 'John')
        self.assertEqual(person['languages'][0]['id'], english_id)
        self.assertEqual(person['languages'][2]['id'], german_id)
        self.assertEqual(person['languages'][0]['name'], 'English')
        self.assertEqual(person['languages'][1]['name'], 'Spanish')
        self.assertEqual(person['languages'][2]['name'], 'German')

        # Remove item
        resp = self.app.put('/person/%s/' % person_id, data=json.dumps({
            'languages': [
                { 'id': german_id },
            ]
        }))
        response_success(resp)
        person = resp_json(resp)
        self.assertEqual(len(person['languages']), 1)
        self.assertEqual(person['name'], 'John')
        self.assertEqual(person['languages'][0]['id'], german_id)
        self.assertEqual(person['languages'][0]['name'], 'German')

        # Assign back (item is still in the database)
        resp = self.app.put('/person/%s/' % person_id, data=json.dumps({
            'languages': [
                { 'id': german_id },
                { 'id': english_id },
            ]
        }))
        response_success(resp)
        person = resp_json(resp)
        self.assertEqual(len(person['languages']), 2)
        self.assertEqual(person['name'], 'John')
        self.assertEqual(person['languages'][0]['id'], german_id)
        self.assertEqual(person['languages'][0]['name'], 'German')
        self.assertEqual(person['languages'][1]['id'], english_id)
        self.assertEqual(person['languages'][1]['name'], 'English')

        # Test invalid ID
        resp = self.app.put('/person/%s/' % person_id, data=json.dumps({
            'languages': [
                { 'id': 'INVALID' },
            ]
        }))
        response_error(resp)

    def test_datetime(self):
        resp = self.app.post('/datetime/', data=json.dumps({
            'datetime': '2010-01-01T00:00:00',
        }))
        response_success(resp)
        datetime = resp_json(resp)
        self.assertEqual(datetime['datetime'], '2010-01-01T00:00:00')

        with query_counter() as c:
            resp = self.app.put('/datetime/%s/' % datetime['id'], data=json.dumps({
                'datetime': '2010-01-02T00:00:00',
            }))
            response_success(resp)
            datetime = resp_json(resp)
            self.assertEqual(datetime['datetime'], '2010-01-02T00:00:00')

            self.assertEqual(c, 3) # query, update, query (reload)

        with query_counter() as c:
            resp = self.app.put('/datetime/%s/' % datetime['id'], data=json.dumps({
                'datetime': '2010-01-02T00:00:00',
            }))
            response_success(resp)
            datetime = resp_json(resp)
            self.assertEqual(datetime['datetime'], '2010-01-02T00:00:00')

            # Ideally this would be one query since we're not modifying, but
            # in the generic case the save method may have other side effects
            # and we don't know if the object was modified, so we currently
            # always reload.
            self.assertEqual(c, 2) # 2x query (with reload)

        # Same as above, with no body
        with query_counter() as c:
            resp = self.app.put('/datetime/%s/' % datetime['id'], data=json.dumps({
            }))
            response_success(resp)
            datetime = resp_json(resp)
            self.assertEqual(datetime['datetime'], '2010-01-02T00:00:00')

            self.assertEqual(c, 2) # 2x query (with reload)

    def test_receive_bad_json(self):
        """
        Python is stupid and by default lets us accept an invalid JSON. Test
        that flask-mongorest handles it correctly.
        """

        # test create
        resp = self.app.post('/dict_doc/', data=json.dumps({
            'dict': {
                'nan': float('NaN'),
                'inf': float('inf'),
                '-inf': float('-inf'),
            }
        }))
        response_error(resp, code=400)
        self.assertEqual(resp_json(resp), { 'error': 'The request contains invalid JSON.' })

        # test update
        resp = self.app.post('/dict_doc/', data=json.dumps({
            'dict': { 'aaa': 'bbb' }
        }))
        response_success(resp)
        resp = self.app.put('/dict_doc/%s/' % resp_json(resp)['id'], data=json.dumps({
            'dict': {
                'nan': float('NaN'),
                'inf': float('inf'),
                '-inf': float('-inf'),
            }
        }))
        response_error(resp, code=400)
        self.assertEqual(resp_json(resp), { 'error': 'The request contains invalid JSON.' })

    def test_send_bad_json(self):
        """
        Make sure that - even if we store invalid JSON in databse, we error out
        instead of sending invalid data to the user.
        """
        doc = example.DictDoc.objects.create(dict={
            'NaN': float('NaN'),
            'inf': float('inf'),
            '-inf': float('-inf'),
        })

        # test fetch
        self.assertRaises(ValueError, self.app.get, '/dict_doc/%s/' % doc.id)

        # test list
        self.assertRaises(ValueError, self.app.get, '/dict_doc/')

class InternalTestCase(unittest.TestCase):
    """
    Test internal methods.
    """

    def test_serialize_mongoengine_validation_error(self):
        from flask_mongorest.views import serialize_mongoengine_validation_error

        error = ValidationError(errors={
            'a': ValidationError('Invalid value')
        })
        result = serialize_mongoengine_validation_error(error)
        self.assertEqual(result, {
            'field-errors': {
                'a': 'Invalid value',
            }
        })

        error = ValidationError('Invalid value')
        result = serialize_mongoengine_validation_error(error)
        self.assertEqual(result, {
            'error': 'Invalid value'
        })

        error = ValidationError(errors={
            'a': 'Invalid value'
        })
        result = serialize_mongoengine_validation_error(error)
        self.assertEqual(result, {
            'field-errors': {
                'a': 'Invalid value',
            }
        })


if __name__ == '__main__':
    unittest.main()

