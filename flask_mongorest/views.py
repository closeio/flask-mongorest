import json
import mimerender
import mongoengine
from flask.ext.views.base import View
from werkzeug.routing import NotFound
from werkzeug.exceptions import BadRequest
from flask import request, render_template
from werkzeug.exceptions import Unauthorized
from flask.ext.mongorest.utils import MongoEncoder
from flask.ext.mongorest.exceptions import ValidationError

mimerender = mimerender.FlaskMimeRender()

render_json = lambda **payload: json.dumps(payload, cls=MongoEncoder)
render_html = lambda **payload: render_template('mongorest/debug.html', data=json.dumps(payload, cls=MongoEncoder, sort_keys=True, indent=4))

class ResourceView(View):
    resource = None
    methods = []
    authentication_methods = []

    def __init__(self):
        assert(self.resource and self.methods)

    @mimerender(default='json', json=render_json, html=render_html)
    def dispatch_request(self, *args, **kwargs):
        # keep all the logic in a helper method (_dispatch_request) so that
        # it's easy for subclasses to override this method (when they don't want to use
        # this mimerender decorator) without them also having to copy/paste all the
        # authentication logic, etc.
        return self._dispatch_request(*args, **kwargs)

    def _dispatch_request(self, *args, **kwargs):
        authorized = True if len(self.authentication_methods) == 0 else False
        for authentication_method in self.authentication_methods:
            if authentication_method().authorized():
                authorized = True
        if not authorized:
            raise Unauthorized

        try:
            self._resource = self.requested_resource(request)
            return super(ResourceView, self).dispatch_request(*args, **kwargs)
        except mongoengine.queryset.DoesNotExist as e:
            raise NotFound("Empty query: "+str(e))
        except ValidationError, e:
            return e.message, '400 Bad Request'
        except mongoengine.ValidationError, e:
            raise BadRequest(description=e)

    def requested_resource(self, request):
        """In the case where the Resource that this view is associated with points to a Document class
           that allows inheritance, this method should indicate the specific Resource class to use
           when processing POST and PUT requests through information available in the request
           itself or through other means."""
        # Default behavior is to use the (base) resource class
        return self.resource()

    def get(self, **kwargs):
        pk = kwargs.pop('pk', None)
        # Create a queryset filter to control read access to the
        # underlying objects
        qfilter = lambda qs: self.has_read_permission(request, qs.clone())
        if pk is None:
            objs, has_more = self._resource.get_objects(qfilter=qfilter)
            ret = {
                'data': [self._resource.serialize(obj, params=request.args) for obj in objs]
            }
            if has_more != None:
                ret['has_more'] = has_more
        else:
            obj = self._resource.get_object(pk, qfilter=qfilter)
            ret = self._resource.serialize(obj, params=request.args)
        return ret

    def post(self, **kwargs):
        if 'pk' in kwargs:
            raise NotFound("Did you mean to use PUT?")
        self._resource.validate_request()
        obj = self._resource.create_object()
        # Check if we have permission to create this object
        if not self.has_add_permission(request, obj):
            raise Unauthorized
        ret = self._resource.serialize(obj, params=request.args)
        if isinstance(obj, mongoengine.Document) and self._resource.uri_prefix:
            return ret, "201 Created", {"Location": self._resource._url(str(obj.id))}
        else:
            return ret

    def put(self, **kwargs):
        pk = kwargs.pop('pk', None)
        if pk is None:
            # Bulk update where the body contains the new values for certain
            # fields.

            # Currently, fetches all the objects and validate them separately.
            # If one of them fails, a ValidationError for this object will be
            # triggered.
            # Ideally, this would be translated into an update statement for
            # performance reasons and would perform the update either for all
            # objects, or for none, if (generic) validation fails. Since this
            # is a bulk update, only the count of objects which were updated is
            # returned.

            objs, has_more = self._resource.get_objects(all=True)
            count = 0
            try:
                for obj in objs:
                    self._resource.validate_request(obj)
                    obj = self._resource.update_object(obj)
                    # Raise or skip?
                    if not self.has_change_permission(request, obj):
                        raise Unauthorized
                    obj.save()
                    count += 1
            except ValidationError, e:
                e.message['count'] = count
                raise e
            else:
                return {'count': count}
        else:
            obj = self._resource.get_object(pk)
            # Check if we have permission to change this object
            if not self.has_change_permission(request, obj):
                raise Unauthorized
            self._resource.validate_request(obj)
            obj = self._resource.update_object(obj)
            ret = self._resource.serialize(obj, params=request.args)
            return ret

    def delete(self, **kwargs):
        pk = kwargs.pop('pk', None)
        obj = self._resource.get_object(pk)
        # Check if we have permission to delete this object
        if not self.has_delete_permission(request, obj):
            raise Unauthorized
        self._resource.delete_object(obj)
        return {}

    # This takes a QuerySet as an argument and then
    # returns a query set that this request can read
    def has_read_permission(self, request, qs):
        return qs

    def has_add_permission(self, request, obj):
        return True

    def has_change_permission(self, request, obj):
        return True

    def has_delete_permission(self, request, obj):
        return True
