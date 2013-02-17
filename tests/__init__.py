import json
import copy
import datetime
import unittest
import example.app as example


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

    user_1 = {
        'email': '1@b.com',
        'first_name': 'alan',
        'last_name': 'baker',
        'datetime': '2012-10-09T10:00:00+00:00',
    }
    user_2 = {
        'email': '2@b.com',
        'first_name': 'olivia',
        'last_name': 'baker',
        'datetime': '2012-11-09T11:00:00+00:00',
    }

    post_1 = {
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

    post_2 = {
        'title': 'Second post',
        'is_published': False,
    }

    def setUp(self):
        self.app = example.app.test_client()
        example.User.drop_collection()
        example.Post.drop_collection()
        example.TestDocument.drop_collection()

        # create user 1
        resp = self.app.post('/user/', data=json.dumps(self.user_1))
        self.assertIn("Location", resp.headers)
        loc = resp.headers["Location"]
        self.assertIn("/user/", loc)
        response_success(resp)
        self.user_1_obj = json.loads(resp.data)
        compare_req_resp(self.user_1, self.user_1_obj)
        # create user 2
        resp = self.app.post('/user/', data=json.dumps(self.user_2))
        response_success(resp)
        self.user_2_obj = json.loads(resp.data)
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
        self.assertIn("Location",resp.headers)
        loc = resp.headers["Location"]
        self.assertIn("/testform/",loc)
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

    def test_get(self):
        resp = self.app.get(example.UserResource.uri_prefix) # /users/
        objs = json.loads(resp.data)['data']
        self.assertEqual(len(objs), 2)

    def test_post(self):
        self.post_1['author_id'] = example.UserResource.uri(self.user_1_obj['id'])
        self.post_1['editor'] = example.UserResource.uri(self.user_2_obj['id'])
        self.post_1['user_lists'] = [[example.UserResource.uri(self.user_1_obj['id'])],
                                     [example.UserResource.uri(self.user_1_obj['id']),
                                      example.UserResource.uri(self.user_2_obj['id'])]]
        print "author_id = "+str(self.post_1["author_id"])
        print "editor = "+str(self.post_1["editor"])
        print "user_lists = "+str(self.post_1["user_lists"])
        resp = self.app.post('/posts/', data=json.dumps(self.post_1))
        response_success(resp)
        compare_req_resp(self.post_1, json.loads(resp.data))
        self.post_1_obj = json.loads(resp.data)
        resp = self.app.get('/posts/%s/' % self.post_1_obj['id'])
        response_success(resp)
        compare_req_resp(self.post_1_obj, json.loads(resp.data))

        self.post_1_obj['author_id'] = example.UserResource.uri(self.user_2_obj['id'])
        resp = self.app.put('/posts/%s/' % self.post_1_obj['id'], data=json.dumps(self.post_1_obj))
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
            'balance': '0.54',
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
        self.assertEqual(resp['error'], 'invalid json.')


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

        spanish_id = person['languages'][1]['id']

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


if __name__ == '__main__':
    unittest.main()

