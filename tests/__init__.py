import json
import copy
import datetime
import unittest
import example.app as example
from mongoengine.context_managers import query_counter

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
    for k,v in req_obj.iteritems():
        assert k in resp_obj.keys(), 'Key %r not in response (keys are %r)' % (k, resp_obj.keys())
        assert resp_obj[k] == v, 'Value for key %r should be %r but is %r' % (k, v, resp_obj[k])


class MongoRestTestCase(unittest.TestCase):

    def setUp(self):
        self.user_1 = {
            'email': '1@b.com',
            'first_name': 'alan',
            'last_name': 'baker',
            'datetime': '2012-10-09T10:00:00+00:00',
        }

        self.user_2 = {
            'email': '2@b.com',
            'first_name': 'olivia',
            'last_name': 'baker',
            'datetime': '2012-11-09T11:00:00+00:00',
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
        example.User.drop_collection()
        example.Post.drop_collection()
        example.TestDocument.drop_collection()
        example.A.drop_collection()
        example.B.drop_collection()
        example.C.drop_collection()
        example.MethodTestDoc.drop_collection()

        # create user 1
        resp = self.app.post('/user/', data=json.dumps(self.user_1))
        assert "Location" in resp.headers
        loc1 = resp.headers["Location"]
        assert "/user/" in loc1
        assert loc1.startswith("http")
        response_success(resp)
        self.user_1_obj = json.loads(resp.data)
        self.user_1_loc = loc1
        compare_req_resp(self.user_1, self.user_1_obj)

        # create user 2
        resp = self.app.post('/user/', data=json.dumps(self.user_2))
        loc2 = resp.headers["Location"]
        assert "/user/" in loc2
        assert loc2.startswith("http")
        response_success(resp)
        self.user_2_obj = json.loads(resp.data)
        self.user_2_loc = loc2
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
        compare_req_resp(data_to_check, json.loads(resp.data))
        resp = json.loads(resp.data)

        # response from PUT should be completely identical as a subsequent GET
        # (including precision of datetimes)
        resp2 = json.loads(self.app.get('/user/%s/' % self.user_1_obj['id']).data)
        self.assertEqual(resp, resp2)

    def test_model_validation(self):
        resp = self.app.post('/user/', data=json.dumps({
            'email': 'invalid',
            'first_name': 'joe',
            'last_name': 'baker',
            'datetime':'2012-08-13T05:25:04.362Z',
            'datetime_local':'2012-08-13T05:25:04.362-03:30'
        }))
        response_error(resp)
        errors = json.loads(resp.data)
        self.assertEqual(errors.keys(), ['field-errors'])
        self.assertEqual(errors['field-errors'].keys(), ['email'])

        resp = self.app.put('/user/%s/' % self.user_1_obj['id'], data=json.dumps({
            'email': 'invalid',
            'first_name': 'joe',
            'last_name': 'baker',
        }))
        response_error(resp)
        errors = json.loads(resp.data)
        self.assertEqual(errors.keys(), ['field-errors'])
        self.assertEqual(errors['field-errors'].keys(), ['email'])

        resp = self.app.put('/user/%s/' % self.user_1_obj['id'], data=json.dumps({
            'emails': ['one@example.com', 'invalid', 'second@example.com', 'invalid2'],
        }))

        response_error(resp)
        errors = json.loads(resp.data)
        self.assertEqual(errors.keys(), ['field-errors'])
        self.assertEqual(errors['field-errors'].keys(), ['emails'])
        self.assertEqual(errors['field-errors']['emails'].keys(), ['1', '3'])

    def test_form_validation(self):
        resp = self.app.post('/testform/', data=json.dumps({
            'name': 'x',
        }))
        response_error(resp)
        errors = json.loads(resp.data)
        self.assertEqual(errors.keys(), ['field-errors'])
        self.assertEqual(errors['field-errors'].keys(), ['name'])

        resp = self.app.post('/testform/', data=json.dumps({
            'name': 'okay',
        }))
        assert "Location" in resp.headers
        loc = resp.headers["Location"]
        assert "/testform/" in loc
        response_success(resp)
        data = json.loads(resp.data)
        self.assertEqual(data['name'], 'okay')

        resp = self.app.post('/testform/', data=json.dumps({
            'name': 'okay',
            'dictfield': {
                'field1': 'value1',
                'field2': ['one', 'two', 'three'],
                'field3': 123,
            }
        }))
        response_success(resp)
        data = json.loads(resp.data)
        self.assertEqual(data['name'], 'okay')
        self.assertEqual(data['dictfield'], {
            'field1': 'value1',
            'field2': ['one', 'two', 'three'],
            'field3': 123,
        })

        # Test boolean fields
        resp = self.app.post('/testform/', data=json.dumps({
            'name': 'okay',
            'is_new': True
        }))
        response_success(resp)
        data = json.loads(resp.data)
        self.assertEqual(data['is_new'], True)

        resp = self.app.post('/testform/', data=json.dumps({
            'name': 'okay',
            'is_new': False
        }))
        response_success(resp)
        data = json.loads(resp.data)
        self.assertEqual(data['is_new'], False)

    def test_resource_fields(self):
        resp = self.app.post('/testfields/', data=json.dumps({
            'name': 'thename',
            'other': 'othervalue',
            'upper_name': 'INVALID',
        }))
        response_success(resp)
        obj = json.loads(resp.data)

        self.assertEqual(set(obj.keys()), set(['id', 'name', 'upper_name']))
        self.assertEqual(obj['name'], 'thename')
        self.assertEqual(obj['upper_name'], 'THENAME')

        resp = self.app.get('/test/%s/' % obj['id'])
        response_success(resp)
        obj = json.loads(resp.data)

        self.assertEqual(obj['name'], 'thename')
        self.assertEqual(obj['other'], None)

        resp = self.app.put('/test/%s/' % obj['id'], data=json.dumps({
            'other': 'new othervalue',
        }))
        response_success(resp)
        obj = json.loads(resp.data)
        self.assertEqual(obj['name'], 'thename')
        self.assertEqual(obj['other'], 'new othervalue')

        resp = self.app.put('/testfields/%s/' % obj['id'], data=json.dumps({
            'name': 'namevalue2',
            'upper_name': 'INVALID',
        }))
        response_success(resp)
        obj = json.loads(resp.data)
        self.assertEqual(obj['name'], 'namevalue2')
        self.assertEqual(obj['upper_name'], 'NAMEVALUE2')

    def test_form(self):
        resp = self.app.post('/testform/', data=json.dumps({
            'name': 'name1',
            'other': 'other1',
        }))
        response_success(resp)
        test_1 = json.loads(resp.data)

        resp = self.app.post('/testform/', data=json.dumps({
            'name': 'name2',
            'other': 'other2',
        }))
        response_success(resp)
        test_2 = json.loads(resp.data)

        resp = self.app.put('/testform/', data=json.dumps({
            'other': 'new',
        }))
        response_success(resp)

        resp = self.app.get('/testform/%s/' % test_1['id'])
        test_1 = json.loads(resp.data)
        self.assertEqual(test_1['name'], 'name1')
        self.assertEqual(test_1['other'], 'new')

        resp = self.app.get('/testform/%s/' % test_2['id'])
        test_2 = json.loads(resp.data)
        self.assertEqual(test_2['name'], 'name2')
        self.assertEqual(test_2['other'], 'new')

    def test_restricted_auth(self):
        self.post_1['author_id'] = self.user_1_obj['id']
        self.post_1['editor'] = self.user_2_obj['id']
        self.post_1['user_lists'] = [self.user_1_obj['id'], self.user_2_obj['id']]

        resp = self.app.get('/user/')
        objs = json.loads(resp.data)['data']
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
        data = json.loads(resp.data)

        # Look at current number of posts through an unrestricted view
        resp = self.app.get('/posts/')
        tmp = json.loads(resp.data)
        nposts = len(tmp["data"])
        # Should see 2
        self.assertEqual(2, nposts)

        # extra data returned in get_objects
        self.assertEqual(tmp['more'], 'stuff')

        # Now look at posts through a restricted view
        resp = self.app.get('/restricted/')
        tmp = json.loads(resp.data)
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

        data = json.loads(resp.data)

        # Now let's try and delete an unpublished post
        resp = self.app.delete('/restricted/%s/' % (data["id"],),
                               data=json.dumps(post))
        # Should work
        response_success(resp, code=200)

    def test_get(self):
        resp = self.app.get(example.UserResource.uri_prefix) # /users/
        objs = json.loads(resp.data)['data']
        self.assertEqual(len(objs), 2)

    def test_get_primary_user(self):
        self.post_1['author_id'] = self.user_1_loc
        self.post_1['editor'] = self.user_2_loc
        self.post_1['user_lists'] = [self.user_1_loc, self.user_2_loc]
        resp = self.app.post('/posts/', data=json.dumps(self.post_1))
        resp = self.app.get('/posts/?_include_primary_user=1')
        objs = json.loads(resp.data)['data']
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0]['title'], 'first post!')
        self.assertTrue(len(objs[0]['primary_user']) > 0)

    def test_get_empty_primary_user(self):
        resp = self.app.post('/posts/', data=json.dumps(self.post_2))
        resp = self.app.get('/posts/?_include_primary_user=1')
        objs = json.loads(resp.data)['data']
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0]['title'], 'Second post')
        self.assertEqual(objs[0]['primary_user'], None)

    def test_post(self):
        self.post_1['author_id'] = self.user_1_loc
        self.post_1['editor'] = self.user_2_loc
        self.post_1['user_lists'] = [self.user_1_loc, self.user_2_loc]
        resp = self.app.post('/posts/', data=json.dumps(self.post_1))
        response_success(resp)
        compare_req_resp(self.post_1, json.loads(resp.data))
        self.post_1_obj = json.loads(resp.data)
        resp = self.app.get('/posts/%s/' % self.post_1_obj['id'])
        response_success(resp)
        compare_req_resp(self.post_1_obj, json.loads(resp.data))

        self.post_1_obj['author_id'] = self.user_2_loc
        resp = self.app.put('/posts/%s/' % self.post_1_obj['id'], data=json.dumps(self.post_1_obj))
        response_success(resp)
        jd = json.loads(resp.data)
        self.assertEqual(self.post_1_obj['author_id'], jd["author_id"])

        response_success(resp)
        compare_req_resp(self.post_1_obj, json.loads(resp.data))
        self.post_1_obj = json.loads(resp.data)

        resp = self.app.post('/posts/', data=json.dumps(self.post_2))
        response_success(resp)
        compare_req_resp(self.post_2, json.loads(resp.data))
        self.post_2_obj = json.loads(resp.data)

        #test filtering

        resp = self.app.get('/posts/?title__startswith=first')
        response_success(resp)
        data_list = json.loads(resp.data)['data']
        compare_req_resp(self.post_1_obj, data_list[0])

        resp = self.app.get('/posts/?title__startswith=second')
        response_success(resp)
        data_list = json.loads(resp.data)['data']
        self.assertEqual(data_list, [])

        resp = self.app.get('/posts/?title__in=%s,%s' % (self.post_1_obj['title'], self.post_2_obj['title']))
        response_success(resp)
        posts = json.loads(resp.data)
        self.assertEqual(len(posts['data']), 2)

        resp = self.app.get('/user/?datetime=%s' % '2012-10-09 10:00:00')
        response_success(resp)
        users = json.loads(resp.data)
        self.assertEqual(len(users['data']), 1)

        resp = self.app.get('/user/?datetime__gt=%s' % '2012-10-08 10:00:00')
        response_success(resp)
        users = json.loads(resp.data)
        self.assertEqual(len(users['data']), 2)

        resp = self.app.get('/user/?datetime__gte=%s' % '2012-10-09 10:00:00')
        response_success(resp)
        users = json.loads(resp.data)
        self.assertEqual(len(users['data']), 2)

        # test negation

        # exclude many
        resp = self.app.get('/posts/?title__not__in=%s,%s' % (self.post_1_obj['title'], self.post_2_obj['title']))
        response_success(resp)
        posts = json.loads(resp.data)
        self.assertEqual(len(posts['data']), 0)

        # exclude one
        resp = self.app.get('/posts/?title__not__in=%s' % (self.post_1_obj['title']))
        response_success(resp)
        posts = json.loads(resp.data)
        self.assertEqual(len(posts['data']), 1)

        resp = self.app.get('/posts/?author_id=%s' % self.user_2_obj['id'])
        response_success(resp)
        data_list = json.loads(resp.data)['data']
        compare_req_resp(self.post_1_obj, data_list[0])

        resp = self.app.get('/posts/?is_published=true')
        response_success(resp)
        data_list = json.loads(resp.data)['data']
        self.assertEqual(len(data_list), 1)
        compare_req_resp(self.post_1_obj, data_list[0])

        resp = self.app.get('/posts/?is_published=false')
        response_success(resp)
        data_list = json.loads(resp.data)['data']
        self.assertEqual(len(data_list), 1)
        compare_req_resp(self.post_2_obj, data_list[0])

        # default exact filtering
        resp = self.app.get('/posts/?title__exact=first post!')
        data_list_1 = json.loads(resp.data)['data']
        resp = self.app.get('/posts/?title=first post!')
        data_list_2 = json.loads(resp.data)['data']
        self.assertEqual(data_list_1, data_list_2)

        # test bulk update
        resp = self.app.put('/posts/?title__startswith=first', data=json.dumps({
            'description': 'Some description'
        }))
        response_success(resp)
        data = json.loads(resp.data)
        self.assertEqual(data['count'], 1)

        resp = self.app.put('/posts/', data=json.dumps({
            'description': 'Other description'
        }))
        response_success(resp)
        data = json.loads(resp.data)
        self.assertEqual(data['count'], 2)

        resp = self.app.get('/posts/')
        response_success(resp)
        data_list = json.loads(resp.data)['data']
        self.assertEqual(data_list[0]['description'], 'Other description')
        self.assertEqual(data_list[1]['description'], 'Other description')

        resp = self.app.put('/posts/', data=json.dumps({
            'description': 'X'*121 # too long
        }))
        response_error(resp)
        data = json.loads(resp.data)
        self.assertEqual(data['count'], 0)
        self.assertEqual(data['field-errors'].keys(), ['description'])

    def test_boolean_filter(self):
        resp = self.app.get('/filtered_user/?is_active=true')
        response_success(resp)
        self.assertEqual(set([d['is_active'] for d in json.loads(resp.data)['data']]), set([True]))

        resp = self.app.get('/filtered_user/?is_active=false')
        response_success(resp)
        self.assertEqual(len(json.loads(resp.data)['data']), 0)

    def test_invalid_datetime_filter(self):
        resp = self.app.get('/filtered_user/?datetime__lt=not_a_valid_date')
        response_error(resp, code=400)
        self.assertEqual(json.loads(resp.data), {
            'filter-errors': {
                'datetime': 'cannot parse date "not_a_valid_date"'
            }
        })

        resp = self.app.get('/filtered_user/?datetime__lt=2015-05-5476435468765405T00:00:00.000000 00:00')
        response_error(resp, code=400)
        self.assertEqual(json.loads(resp.data), {
            'filter-errors': {
                'datetime': 'cannot parse date "2015-05-5476435468765405T00:00:00.000000 00:00"'
            }
        })

    def test_invalid_int_filter(self):
        resp = self.app.get('/filtered_user/?balance__lt=not_a_valid_int')
        response_error(resp, code=400)
        self.assertEqual(json.loads(resp.data), {
            'filter-errors': {
                'balance': 'not_a_valid_int could not be converted to int'
            }
        })

    def test_post_auto_art_tag(self):
        # create a post by vangogh and an 'art' tag should be added automatically

        # create vangogh
        resp = self.app.post('/user/', data=json.dumps({
            'email': 'vincent@vangogh.com',
            'first_name': 'Vincent',
            'last_name': 'Vangogh',
        }))
        response_success(resp)
        author = resp.headers["Location"]

        # create a post
        resp = self.app.post('/posts/', data=json.dumps(self.post_1))
        response_success(resp)
        post = json.loads(resp.data)

        resp = self.app.put('/posts/%s/' % post['id'], data=json.dumps({
            'author_id': author
        }))
        response_success(resp)
        post = json.loads(resp.data)
        post_obj = example.Post.objects.get(pk=post['id'])
        self.assertTrue('art' in post_obj.tags)
        self.assertTrue('art' in post['tags'])

    def test_broken_reference(self):
        # create a new user
        resp = self.app.post('/user/', data=json.dumps({
            'email': '3@b.com',
            'first_name': 'steve',
            'last_name': 'wiseman',
            'datetime': '2012-11-09T11:00:00+00:00',
        }))
        response_success(resp)
        user_3 = json.loads(resp.data)
        user_3_loc = resp.headers["Location"]

        post = self.post_1.copy()
        post['author_id'] = self.user_1_loc
        post['editor'] = self.user_2_loc
        post['user_lists'] = [user_3_loc]
        resp = self.app.post('/posts/', data=json.dumps(post))
        response_success(resp)
        compare_req_resp(post, json.loads(resp.data))

        post = json.loads(resp.data)

        # remove the user and see if its reference is cleaned up properly
        resp = self.app.delete('/user/%s/' % user_3['id'])
        response_success(resp)

        resp = self.app.get('/posts/%s/' % post['id'])
        response_success(resp)

        self.assertEqual(json.loads(resp.data)['user_lists'], [])

        post['user_lists'] = []
        compare_req_resp(post, json.loads(resp.data))

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
        data = json.loads(resp.data)
        self.assertEqual(len(data['data']), 10)
        self.assertEqual(data['has_more'], True)

        resp = self.app.get('/posts/?_skip=100')
        response_success(resp)
        data = json.loads(resp.data)
        self.assertEqual(len(data['data']), 1)
        self.assertEqual(data['has_more'], False)

        resp = self.app.get('/posts/?_limit=1')
        response_success(resp)
        data = json.loads(resp.data)
        self.assertEqual(len(data['data']), 1)
        self.assertEqual(data['has_more'], True)

        resp = self.app.get('/posts/?_limit=0')
        response_success(resp)
        data = json.loads(resp.data)
        self.assertEqual(len(data['data']), 0)
        self.assertEqual(data['has_more'], True)

        resp = self.app.get('/posts/?_skip=100&_limit=1')
        response_success(resp)
        data = json.loads(resp.data)
        self.assertEqual(len(data['data']), 1)
        self.assertEqual(data['has_more'], False)

        # default limit
        resp = self.app.get('/posts/')
        response_success(resp)
        data = json.loads(resp.data)
        self.assertEqual(len(data['data']), 100)

        # _limit > max_limit
        resp = self.app.get('/posts/?_limit=101')
        response_error(resp, code=400)
        data = json.loads(resp.data)
        self.assertEqual(data['error'], 'The limit you set is larger than the maximum limit for this resource (max_limit = 100).')

        # respect custom max_limit
        resp = self.app.get('/posts10/?_limit=11')
        response_error(resp, code=400)
        data = json.loads(resp.data)
        self.assertEqual(data['error'], 'The limit you set is larger than the maximum limit for this resource (max_limit = 10).')

        resp = self.app.get('/posts10/')
        response_success(resp)
        data = json.loads(resp.data)
        self.assertEqual(len(data['data']), 10)

        resp = self.app.get('/posts10/?_limit=5')
        response_success(resp)
        data = json.loads(resp.data)
        self.assertEqual(len(data['data']), 5)

        resp = self.app.get('/posts250/?_limit=251')
        response_error(resp, code=400)
        data = json.loads(resp.data)
        self.assertEqual(data['error'], 'The limit you set is larger than the maximum limit for this resource (max_limit = 250).')

        resp = self.app.get('/posts250/')
        response_success(resp)
        data = json.loads(resp.data)
        self.assertEqual(len(data['data']), 100)

        resp = self.app.get('/posts250/?_limit=10')
        response_success(resp)
        data = json.loads(resp.data)
        self.assertEqual(len(data['data']), 10)

    def test_garbage_args(self):
        resp = self.app.get('/posts/?_limit=garbage')
        response_error(resp, code=400)
        self.assertEqual(json.loads(resp.data)['error'],
                        '_limit must be an integer (got "garbage" instead).')

        resp = self.app.get('/posts/?_skip=garbage')
        response_error(resp, code=400)
        self.assertEqual(json.loads(resp.data)['error'],
                        '_skip must be an integer (got "garbage" instead).')

    def test_fields(self):
        resp = self.app.get('/user/%s/?_fields=email' % self.user_1_obj['id'])
        response_success(resp)
        user = json.loads(resp.data)
        self.assertEqual(user.keys(), ['email'])

        resp = self.app.get('/user/%s/?_fields=first_name,last_name' % self.user_1_obj['id'])
        response_success(resp)
        user = json.loads(resp.data)
        self.assertEqual(user.keys(), ['first_name','last_name'])

        # Make sure all fields can still be posted.
        test_user_data = {
            'email': 'u@example.com',
            'first_name': 'first',
            'last_name': 'first',
            'balance': 54,
        }

        resp = self.app.post('/user/?_fields=id', data=json.dumps(test_user_data))
        response_success(resp)
        user = json.loads(resp.data)
        self.assertEqual(user.keys(), ['id'])

        resp = self.app.get(example.UserResource.uri(user['id'])) # /user/:id
        response_success(resp)
        user = json.loads(resp.data)
        compare_req_resp(test_user_data, user)

    def test_invalid_json(self):
        resp = self.app.post('/user/', data='{\"}')
        response_error(resp, code=400)
        resp = json.loads(resp.data)
        self.assertEqual(resp['error'], 'The request contains invalid JSON.')

    def test_dbref_vs_objectid(self):
        resp = self.app.post('/a/', data=json.dumps({ "txt": "some text 1" }))
        response_success(resp)
        a1 = json.loads(resp.data)

        resp = self.app.post('/a/', data=json.dumps({ "txt": "some text 2" }))
        response_success(resp)
        a2 = json.loads(resp.data)

        resp = self.app.post('/b/', data=json.dumps({ "ref": a1['id'], "txt": "text" }))
        response_success(resp)
        dbref_obj = json.loads(resp.data)

        resp = self.app.post('/c/', data=json.dumps({ "ref": a1['id'], "txt": "text" }))
        response_success(resp)
        objectid_obj = json.loads(resp.data)

        # compare objects with a dbref reference and an objectid reference
        resp = self.app.get('/b/{0}/'.format(dbref_obj['id']))
        response_success(resp)
        dbref_obj = json.loads(resp.data)

        resp = self.app.get('/c/{0}/'.format(objectid_obj['id']))
        response_success(resp)
        objectid_obj = json.loads(resp.data)

        self.assertEqual(dbref_obj['ref'], objectid_obj['ref'])
        self.assertEqual(dbref_obj['txt'], objectid_obj['txt'])

        # make sure both dbref and objectid are updated correctly
        resp = self.app.put('/b/{0}/'.format(dbref_obj['id']), data=json.dumps({ "ref": a2['id'] }))
        response_success(resp)

        resp = self.app.put('/c/{0}/'.format(objectid_obj['id']), data=json.dumps({ "ref": a2['id'] }))
        response_success(resp)

        resp = self.app.get('/b/{0}/'.format(dbref_obj['id']))
        response_success(resp)
        dbref_obj = json.loads(resp.data)

        resp = self.app.get('/c/{0}/'.format(objectid_obj['id']))
        response_success(resp)
        objectid_obj = json.loads(resp.data)

        self.assertEqual(dbref_obj['ref'], a2['id'])
        self.assertEqual(dbref_obj['ref'], objectid_obj['ref'])
        self.assertEqual(dbref_obj['txt'], objectid_obj['txt'])

    def test_view_methods(self):
        doc = example.ViewMethodTestDoc.objects.create(txt='doc1')

        resp = self.app.get('/test_view_method/%s/' % doc.pk)
        response_success(resp)
        self.assertEqual(json.loads(resp.data), {'method': 'Fetch'})

        resp = self.app.get('/test_view_method/')
        response_success(resp)
        self.assertEqual(json.loads(resp.data), {'method': 'List'})

        resp = self.app.post('/test_view_method/', data=json.dumps({
            'txt': 'doc2'
        }))
        response_success(resp)
        self.assertEqual(json.loads(resp.data), {'method': 'Create'})

        resp = self.app.put('/test_view_method/%s/' % doc.pk, data=json.dumps({
            'txt': 'doc1new'
        }))
        response_success(resp)
        self.assertEqual(json.loads(resp.data), {'method': 'Update'})

        resp = self.app.put('/test_view_method/', data=json.dumps({
            'txt': 'doc'
        }))
        response_success(resp)
        self.assertEqual(json.loads(resp.data), {'method': 'BulkUpdate'})

        resp = self.app.delete('/test_view_method/%s/' % doc.pk, data=json.dumps({
            'txt': 'doc'
        }))
        response_success(resp)
        self.assertEqual(json.loads(resp.data), {'method': 'Delete'})

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
        person = json.loads(resp.data)

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
        person = json.loads(resp.data)
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
        person = json.loads(resp.data)
        self.assertEqual(len(person['languages']), 2)
        self.assertEqual(person['name'], 'John')
        self.assertEqual(person['languages'][0]['id'], english_id)
        self.assertEqual(person['languages'][1]['id'], german_id)
        self.assertEqual(person['languages'][0]['name'], 'English')
        self.assertEqual(person['languages'][1]['name'], 'German')

        # Also no change (empty data)
        resp = self.app.put('/person/%s/' % person_id, data=json.dumps({ }))
        response_success(resp)
        person = json.loads(resp.data)
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
        person = json.loads(resp.data)
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
        person = json.loads(resp.data)
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
        person = json.loads(resp.data)
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
        person = json.loads(resp.data)
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
        datetime = json.loads(resp.data)
        self.assertEqual(datetime['datetime'], '2010-01-01T00:00:00+00:00')

        with query_counter() as c:
            resp = self.app.put('/datetime/%s/' % datetime['id'], data=json.dumps({
                'datetime': '2010-01-02T00:00:00',
            }))
            response_success(resp)
            datetime = json.loads(resp.data)
            self.assertEqual(datetime['datetime'], '2010-01-02T00:00:00+00:00')

            self.assertEqual(c, 3) # query, update, query (reload)

        with query_counter() as c:
            resp = self.app.put('/datetime/%s/' % datetime['id'], data=json.dumps({
                'datetime': '2010-01-02T00:00:00',
            }))
            response_success(resp)
            datetime = json.loads(resp.data)
            self.assertEqual(datetime['datetime'], '2010-01-02T00:00:00+00:00')

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
            datetime = json.loads(resp.data)
            self.assertEqual(datetime['datetime'], '2010-01-02T00:00:00+00:00')

            self.assertEqual(c, 2) # 2x query (with reload)

if __name__ == '__main__':
    unittest.main()

