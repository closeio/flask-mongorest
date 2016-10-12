import json
import mimerender
import mongoengine

from flask import request, render_template
from werkzeug.exceptions import NotFound, Unauthorized

from flask_mongorest.exceptions import ValidationError
from flask_mongorest.utils import MongoEncoder
from flask_mongorest import methods
from flask_views.base import View

mimerender = mimerender.FlaskMimeRender()

render_json = lambda **payload: json.dumps(payload, allow_nan=False, cls=MongoEncoder)
render_html = lambda **payload: render_template('mongorest/debug.html', data=json.dumps(payload, cls=MongoEncoder, sort_keys=True, indent=4))

try:
    text_type = unicode # Python 2
except NameError:
    text_type = str # Python 3

def serialize_mongoengine_validation_error(e):
    """
    Takes a MongoEngine ValidationError as an argument, and returns a
    serializable error dict. Note that we can have nested ValidationErrors.
    """

    def serialize_errors(e):
        if getattr(e, 'message', None):
            return e.message
        elif hasattr(e, 'items'):
            return dict((k, serialize_errors(v)) for (k, v) in e.items())
        else:
            return text_type(e)

    if e.errors:
        return {'field-errors': serialize_errors(e.errors)}
    else:
        return {'error': e.message}

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
            return {'error': 'Unauthorized'}, '401 Unauthorized'

        try:
            self._resource = self.requested_resource(request)
            return super(ResourceView, self).dispatch_request(*args, **kwargs)
        except mongoengine.queryset.DoesNotExist as e:
            return {'error': 'Empty query: ' + str(e)}, '404 Not Found'
        except ValidationError as e:
            return e.message, '400 Bad Request'
        except Unauthorized as e:
            return {'error': 'Unauthorized'}, '401 Unauthorized'
        except NotFound as e:
            return {'error': str(e)}, '404 Not Found'

    def handle_validation_error(self, e):
        if isinstance(e, ValidationError):
            raise
        elif isinstance(e, mongoengine.ValidationError):
            raise ValidationError(serialize_mongoengine_validation_error(e))
        else:
            raise

    def requested_resource(self, request):
        """In the case where the Resource that this view is associated with points to a Document class
           that allows inheritance, this method should indicate the specific Resource class to use
           when processing POST and PUT requests through information available in the request
           itself or through other means."""
        # Default behavior is to use the (base) resource class
        return self.resource()

    def get(self, **kwargs):
        pk = kwargs.pop('pk', None)

        # Set the view_method on a resource instance
        if pk:
            self._resource.view_method = methods.Fetch
        else:
            self._resource.view_method = methods.List

        # Create a queryset filter to control read access to the
        # underlying objects
        qfilter = lambda qs: self.has_read_permission(request, qs.clone())
        if pk is None:
            result = self._resource.get_objects(qfilter=qfilter)

            # Result usually contains objects and a has_more bool. However, in case where
            # more data is returned, we include it at the top level of the response dict
            if len(result) == 2:
                objs, has_more = result
                extra = {}
            elif len(result) == 3:
                objs, has_more, extra = result
            else:
                raise ValueError('Unsupported value of resource.get_objects')

            data = []
            for obj in objs:
                try:
                    data.append(self._resource.serialize(obj, params=request.args))
                except Exception as e:
                    fixed_obj = self._resource.handle_serialization_error(e, obj)
                    if fixed_obj is not None:
                        data.append(fixed_obj)

            # Serialize the objects one by one
            ret = {
                'data': data
            }

            if has_more is not None:
                ret['has_more'] = has_more

            if extra:
                ret.update(extra)
        else:
            obj = self._resource.get_object(pk, qfilter=qfilter)
            ret = self._resource.serialize(obj, params=request.args)
        return ret

    def post(self, **kwargs):
        if 'pk' in kwargs:
            raise NotFound("Did you mean to use PUT?")

        # Set the view_method on a resource instance
        self._resource.view_method = methods.Create

        self._resource.validate_request()
        try:
            obj = self._resource.create_object()
        except Exception as e:
            self.handle_validation_error(e)

        # Check if we have permission to create this object
        if not self.has_add_permission(request, obj):
            raise Unauthorized

        ret = self._resource.serialize(obj, params=request.args)
        if isinstance(obj, mongoengine.Document) and self._resource.uri_prefix:
            return ret, "201 Created", {"Location": self._resource._url(str(obj.id))}
        else:
            return ret

    def process_object(self, obj):
        """Validate and update an object"""
        # Check if we have permission to change this object
        if not self.has_change_permission(request, obj):
            raise Unauthorized

        self._resource.validate_request(obj)

        try:
            obj = self._resource.update_object(obj)
        except Exception as e:
            self.handle_validation_error(e)

    def process_objects(self, objs):
        """
        Update each object in the list one by one, and return the total count
        of updated objects.
        """
        count = 0
        try:
            for obj in objs:
                self.process_object(obj)
                count += 1
        except ValidationError as e:
            e.message['count'] = count
            raise e
        else:
            return {'count': count}

    def put(self, **kwargs):
        pk = kwargs.pop('pk', None)

        # Set the view_method on a resource instance
        if pk:
            self._resource.view_method = methods.Update
        else:
            self._resource.view_method = methods.BulkUpdate

        if pk is None:
            # Bulk update where the body contains the new values for certain
            # fields.

            # Currently, fetches all the objects and validates them separately.
            # If one of them fails, a ValidationError for this object will be
            # triggered.
            # Ideally, this would be translated into an update statement for
            # performance reasons and would perform the update either for all
            # objects, or for none, if (generic) validation fails. Since this
            # is a bulk update, only the count of objects which were updated is
            # returned.

            # Get a list of all objects matching the filters, capped at this
            # resource's `bulk_update_limit`
            result = self._resource.get_objects()
            if len(result) == 2:
                objs, has_more = result
            elif len(result) == 3:
                objs, has_more, extra = result

            # Update all the objects and return their count
            return self.process_objects(objs)
        else:
            obj = self._resource.get_object(pk)
            self.process_object(obj)
            ret = self._resource.serialize(obj, params=request.args)
            return ret

    def delete(self, **kwargs):
        pk = kwargs.pop('pk', None)

        # Set the view_method on a resource instance
        self._resource.view_method = methods.Delete

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

