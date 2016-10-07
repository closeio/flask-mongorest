import json
import mongoengine

from bson.dbref import DBRef
from bson.objectid import ObjectId
from flask import request, url_for
try:
    from urllib.parse import urlparse
except ImportError: # Python 2
    from urlparse import urlparse

try: # closeio/mongoengine
    from mongoengine.base.proxy import DocumentProxy
    from mongoengine.fields import SafeReferenceField
except ImportError:
    DocumentProxy = None
    SafeReferenceField = None

from mongoengine.fields import EmbeddedDocumentField, ListField, ReferenceField, GenericReferenceField
from mongoengine.fields import DictField

from cleancat import ValidationError as SchemaValidationError
from flask_mongorest import methods
from flask_mongorest.exceptions import ValidationError, UnknownFieldError
from flask_mongorest.utils import cmp_fields, isbound, isint, equal


class ResourceMeta(type):
    def __init__(cls, name, bases, classdict):
        if classdict.get('__metaclass__') is not ResourceMeta:
            for document, resource in cls.child_document_resources.items():
                if resource == name:
                    cls.child_document_resources[document] = cls
        type.__init__(cls, name, bases, classdict)

class Resource(object):
    # MongoEngine Document class related to this resource (required)
    document = None

    # List of fields that can (and should by default) be included in the
    # response
    fields = None

    # Dict of original field names (as seen in `fields`) and what they should
    # be renamed to in the API response
    rename_fields = {}

    # CleanCat Schema class (used for validation)
    schema = None

    # List of fields that the objects can be ordered by
    allowed_ordering = []

    # Define whether or not this resource supports pagination
    paginate = True

    # Default limit if no _limit is specified in the request. Only relevant
    # if pagination is enabled.
    default_limit = 100

    # Maximum value of _limit that can be requested (avoids DDoS'ing the API).
    # Only relevant if pagination is enabled.
    max_limit = 100

    # Maximum number of objects which can be bulk-updated by a single request
    bulk_update_limit = 1000

    # Map of field names and Resource classes that should be used to handle
    # these fields (for serialization, saving, etc.).
    related_resources = {}

    # Map of field names on this resource's document to field names on the
    # related resource's document, used as a helper in the process of
    # turning a field value from a queryset to a list of objects
    #
    # TODO Behavior of this is *very* unintuitive and should be changed or
    # dropped, or at least refactored
    related_resources_hints = {}

    # List of field names corresponding to related resources. If a field is
    # mentioned here and in `related_resources`, it can be created/updated
    # from within this resource.
    save_related_fields = []

    # Map of MongoEngine Document classes to Resource class names. Defines
    # which sub-resource should be used for handling a particular subclass of
    # this resource's document.
    child_document_resources = {}

    # Whenever a new document is posted and the system doesn't know the type
    # of it yet, it will choose a default sub-resource for this document type
    default_child_resource_document = None

    # Defines whether MongoEngine's select_related should be used on a
    # filtered query set, pulling all the references efficiently.
    select_related = False

    # Must start and end with a "/"
    uri_prefix = None

    def __init__(self, view_method=None):
        """
        Initializes a resource. Optionally, a method class can be given to
        view_method (see methods.py) so the resource can behave differently
        depending on the method.
        """
        doc_fields = self.document._fields.keys()
        if self.fields is None:
            self.fields = doc_fields
        self._related_resources = self.get_related_resources()
        self._rename_fields = self.get_rename_fields()
        self._reverse_rename_fields = {}
        for k, v in self._rename_fields.items():
            self._reverse_rename_fields[v] = k
        assert len(self._rename_fields) == len(self._reverse_rename_fields), \
            'Cannot rename multiple fields to the same name'
        self._filters = self.get_filters()
        self._child_document_resources = self.get_child_document_resources()
        self._default_child_resource_document = self.get_default_child_resource_document()
        self.data = None
        self._dirty_fields = None
        self.view_method = view_method

    @property
    def params(self):
        """
        Return parameters of the request which is currently being processed.
        Params can be passed in two different ways:

        1. As a querystring (e.g. '/resource/?status=active&_limit=10').
        2. As a _params property in the JSON payload. For example:
             { '_params': { 'status': 'active', '_limit': '10' } }
        """
        if not hasattr(self, '_params'):
            if '_params' in self.raw_data:
                self._params = self.raw_data['_params']
            else:
                try:
                    self._params = request.args.to_dict()
                except AttributeError: # mocked request with regular dict
                    self._params = request.args
        return self._params

    def _enforce_strict_json(self, val):
        """
        Helper method used to raise a ValueError if NaN, Infinity, or
        -Infinity were posted. By default, json.loads accepts these values,
        but it allows us to perform extra validation via a parse_constant
        kwarg.
        """
        # according to the `json.loads` docs: "parse_constant, if specified,
        # will be called with one of the following strings: '-Infinity',
        # 'Infinity', 'NaN'". Since none of them are valid JSON, we can simply
        # raise an exception here.
        raise ValueError

    @property
    def raw_data(self):
        """Validate and return parsed JSON payload."""
        if not hasattr(self, '_raw_data'):
            if request.method in ('PUT', 'POST') or request.data:
                if request.mimetype and 'json' not in request.mimetype:
                    raise ValidationError({'error': "Please send valid JSON with a 'Content-Type: application/json' header."})
                if request.headers.get('Transfer-Encoding') == 'chunked':
                    raise ValidationError({'error': "Chunked Transfer-Encoding is not supported."})

                try:
                    self._raw_data = json.loads(request.data.decode('utf-8'), parse_constant=self._enforce_strict_json)
                except ValueError:
                    raise ValidationError({'error': 'The request contains invalid JSON.'})
                if not isinstance(self._raw_data, dict):
                    raise ValidationError({'error': 'JSON data must be a dict.'})
            else:
                self._raw_data = {}

        return self._raw_data

    @classmethod
    def uri(self, path):
        """Generate a URI reference for the given path"""
        if self.uri_prefix:
            ret = self.uri_prefix+path
            return ret
        else:
            raise ValueError("Cannot generate URI for resources that do not specify a uri_prefix")

    @classmethod
    def _url(self, path):
        """Generate a complete URL for the given path. Requires application context."""
        if self.uri_prefix:
            url = url_for(self.uri_prefix.lstrip("/").rstrip("/"),_external=True)
            ret = url+path
            return ret
        else:
            raise ValueError("Cannot generate URL for resources that do not specify a uri_prefix")

    def get_fields(self):
        """
        Return a list of fields that should be included in the response
        (unless a `_fields` param didn't include them).
        """
        return self.fields

    def get_optional_fields(self):
        """
        Return a list of fields that can optionally be included in the
        response (but only if a `_fields` param mentioned them explicitly).
        """
        return []

    def get_requested_fields(self, **kwargs):
        """
        Process a list of fields requested by the client and return only the
        ones which are allowed by get_fields and get_optional_fields.

        If `_fields` param is set to '_all', return a list of all the fields
        from get_fields and get_optional_fields combined.
        """
        params = kwargs.get('params', None)

        include_all = False

        if 'fields' in kwargs:
            fields = kwargs['fields']
            all_fields_set = set(fields)
        else:
            fields = self.get_fields()
            all_fields_set = set(fields) | set(self.get_optional_fields())

        if params and '_fields' in params:
            only_fields = set(params['_fields'].split(','))
            if '_all' in only_fields:
                include_all = True
        else:
            only_fields = None

        requested_fields = []
        if include_all or only_fields is None:
            if include_all:
                field_selection = all_fields_set
            else:
                field_selection = fields
            for field in field_selection:
                requested_fields.append(field)
        else:
            for field in only_fields:
                actual_field = self._reverse_rename_fields.get(field, field)
                if actual_field in all_fields_set:
                    requested_fields.append(actual_field)

        return requested_fields

    def get_max_limit(self):
        return self.max_limit

    def get_related_resources(self):
        return self.related_resources

    def get_save_related_fields(self):
        return self.save_related_fields

    def get_rename_fields(self):
        """
        @TODO should automatically support model_id for reference fields (only) and model for related_resources
        """
        return self.rename_fields

    def get_child_document_resources(self):
        # By default, don't inherit child_document_resources. This lets us have
        # multiple resources for a child document without having to reset the
        # child_document_resources property in the subclass.
        if 'child_document_resources' in self.__class__.__dict__:
            return self.child_document_resources
        else:
            return {}

    def get_default_child_resource_document(self):
        # See comment on get_child_document_resources.
        if 'default_child_resource_document' in self.__class__.__dict__:
            return self.default_child_resource_document
        else:
            return None

    def get_filters(self):
        """
        Given the filters declared on this resource, return a mapping
        of all allowed filters along with their individual mappings of
        suffixes and operators.

        For example, if self.filters declares:
            { 'date': [operators.Exact, operators.Gte] }
        then this method will return:
            {
                'date': {
                    '': operators.Exact,
                    'exact': operators.Exact,
                    'gte': operators.Gte
                }
            }
        Then, when a request comes in, Flask-MongoRest will match
        `?date__gte=value` to the 'date' field and the 'gte' suffix: 'gte',
        and hence use the Gte operator to filter the data.
        """
        filters = {}
        for field, operators in getattr(self, 'filters', {}).items():
            field_filters = {}
            for op in operators:
                if op.op == 'exact':
                    field_filters[''] = op
                field_filters[op.op] = op
            filters[field] = field_filters
        return filters

    def serialize_field(self, obj, **kwargs):
        if self.uri_prefix and hasattr(obj, "id"):
            return self._url(str(obj.id))
        else:
            return self.serialize(obj, **kwargs)

    def _subresource(self, obj):
        """
        Select and create an appropriate sub-resource class for delegation or
        return None if there isn't one.
        """
        s_class = self._child_document_resources.get(obj.__class__)
        if not s_class and self._default_child_resource_document:
            s_class = self._child_document_resources[self._default_child_resource_document]
        if s_class and s_class != self.__class__:
            r = s_class(view_method=self.view_method)
            r.data = self.data
            return r
        else:
            return None

    def serialize(self, obj, **kwargs):
        """
        Given an object, serialize it, turning it into its JSON
        respresentation.
        """
        if not obj:
            return {}

        # If a subclass of an obj has been called with a base class' resource,
        # use the subclass-specific serialization
        subresource = self._subresource(obj)
        if subresource:
            return subresource.serialize(obj, **kwargs)

        def get(obj, field_name, field_instance=None):
            """
            @TODO needs significant cleanup
            """

            has_field_instance = bool(field_instance)
            field_instance = (field_instance or
                              self.document._fields.get(field_name, None) or
                              getattr(self.document, field_name, None))

            # Determine the field value
            if has_field_instance:
                field_value = obj
            elif isinstance(obj, dict):
                return obj[field_name]
            else:
                try:
                    field_value = getattr(obj, field_name)
                except AttributeError:
                    raise UnknownFieldError

            # If this field is a reference or an embedded document, either
            # return a DBRef or serialize it using a resource found in
            # `related_resources`.
            if isinstance(field_instance, (ReferenceField, GenericReferenceField, EmbeddedDocumentField)):
                if field_name in self._related_resources:
                    return (
                        field_value and
                        not isinstance(field_value, DBRef) and
                        self._related_resources[field_name]().serialize_field(field_value, **kwargs)
                    )
                else:
                    if DocumentProxy and isinstance(field_value, DocumentProxy):
                        # Don't perform a DBRef isinstance check below since
                        # it might trigger an extra query.
                        return field_value.to_dbref()
                    if isinstance(field_value, DBRef):
                        return field_value
                    return field_value and field_value.to_dbref()

            # If this field is a list, serialize each item in the list separately.
            elif isinstance(field_instance, ListField):
                return [val for val in [get(elem, field_name, field_instance=field_instance.field) for elem in field_value] if val]

            # If this field is a dict...
            elif isinstance(field_instance, DictField):
                # ... serialize each value based on an explicit field type
                # (e.g. if the schema defines a DictField(IntField), where all
                # the values in the dict should be ints).
                if field_instance.field:
                    return {
                        key: get(elem, field_name, field_instance=field_instance.field)
                        for (key, elem) in field_value.items()
                    }
                # ... or simply return the dict intact, if the field type
                # wasn't specified
                else:
                    return field_value

            # If this field is callable, execute it and return it or serialize
            # it based on its related resource defined in the
            # `related_resources` map.
            elif callable(field_instance):
                if isinstance(field_value, list):
                    value = field_value
                else:
                    if isbound(field_instance):
                        value = field_instance()
                    elif isbound(field_value):
                        value = field_value()
                    else:
                        value = field_instance(obj)

                if field_name in self._related_resources:
                    if isinstance(value, list):
                        return [self._related_resources[field_name]().serialize_field(o, **kwargs) for o in value]
                    elif value is None:
                        return None
                    else:
                        return self._related_resources[field_name]().serialize_field(value, **kwargs)
                return value
            return field_value

        # Get the requested fields
        requested_fields = self.get_requested_fields(**kwargs)

        # Drop the kwargs we don't need any more (we're passing `kwargs` to
        # child resources so we don't want to pass `fields` and `params` that
        # pertain to the parent resource).
        kwargs.pop('fields', None)
        kwargs.pop('params', None)

        # Fill in the `data` dict by serializing each of the requested fields
        # one by one.
        data = {}
        for field in requested_fields:

            # resolve the user-facing name of the field
            renamed_field = self._rename_fields.get(field, field)

            # if the field is callable, execute it with `obj` as the param
            if hasattr(self, field) and callable(getattr(self, field)):
                value = getattr(self, field)(obj)

                # if the field is associated with a specific resource (via the
                # `related_resources` map), use that resource to serialize it
                if field in self._related_resources and value is not None:
                    related_resource = self._related_resources[field]()
                    if isinstance(value, mongoengine.document.Document):
                        value = related_resource.serialize_field(value)
                    elif isinstance(value, dict):
                        value = dict((k, related_resource.serialize_field(v))
                                     for (k, v) in value.items())
                    else:  # assume queryset or list
                        value = [related_resource.serialize_field(o)
                                 for o in value]
                data[renamed_field] = value
            else:
                try:
                    data[renamed_field] = get(obj, field)
                except UnknownFieldError:
                    try:
                        data[renamed_field] = self.value_for_field(obj, field)
                    except UnknownFieldError:
                        pass

        return data

    def handle_serialization_error(self, exc, obj):
        """
        Override this to implement custom behavior whenever serializing an
        object fails.
        """
        pass

    def value_for_field(self, obj, field):
        """
        If we specify a field which doesn't exist on the resource or on the
        object, this method lets us return a custom value.
        """
        raise UnknownFieldError

    def validate_request(self, obj=None):
        """
        Validate the request that's currently being processed and fill in
        the self.data dict that'll later be used to save/update an object.

        `obj` points to the object that's being updated, or is empty if a new
        object is being created.
        """
        # When creating or updating a single object, delegate the validation
        # to a more specific subresource, if it exists
        if (request.method == 'PUT' and obj) or request.method == 'POST':
            subresource = self._subresource(obj)
            if subresource:
                subresource._raw_data = self._raw_data
                subresource.validate_request(obj=obj)
                self.data = subresource.data
                return

        # Don't work on original raw data, we may reuse the resource for bulk
        # updates.
        self.data = self.raw_data.copy()

        # Do renaming in two passes to prevent potential multiple renames
        # depending on dict traversal order.
        # E.g. if a -> b, b -> c, then a should never be renamed to c.
        fields_to_delete = []
        fields_to_update = {}
        for k, v in self._rename_fields.items():
            if v in self.data:
                fields_to_update[k] = self.data[v]
                fields_to_delete.append(v)
        for k in fields_to_delete:
            del self.data[k]
        for k, v in fields_to_update.items():
            self.data[k] = v

        # If CleanCat schema exists on this resource, use it to perform the
        # validation
        if self.schema:
            if request.method == 'PUT' and obj is not None:
                obj_data = dict([(key, getattr(obj, key)) for key in obj._fields.keys()])
            else:
                obj_data = None

            schema = self.schema(self.data, obj_data)
            try:
                self.data = schema.full_clean()
            except SchemaValidationError:
                raise ValidationError({'field-errors': schema.field_errors, 'errors': schema.errors })

    def get_queryset(self):
        """
        Return a MongoEngine queryset that will later be used to return
        matching documents.
        """
        return self.document.objects

    def get_object(self, pk, qfilter=None):
        """
        Given a PK and an optional queryset filter function, find a matching
        document in the queryset.
        """
        qs = self.get_queryset()
        # If a queryset filter was provided, pass our current queryset in and
        # get a new one out
        if qfilter:
            qs = qfilter(qs)
        return qs.get(pk=pk)

    def fetch_related_resources(self, objs, only_fields=None):
        """
        Given a list of objects and an optional list of the only fields we
        should care about, fetch these objects' related resources.
        """

        # Create a map of field names to MongoEngine Q objects that will
        # later be used to fetch the related resources from MongoDB
        # Queries for the same document/collection are combined to improve
        # efficiency.
        document_queryset = {}
        for obj in objs:
            for field_name in self.related_resources_hints.keys():
                if only_fields is not None and field_name not in only_fields:
                    continue
                method = getattr(obj, field_name)
                if callable(method):
                    q = method()
                    if field_name in document_queryset:
                        document_queryset[field_name] = (document_queryset[field_name] | q._query_obj)
                    else:
                        document_queryset[field_name] = q._query_obj

        # For each field name, execute the queries we generated in the block
        # above, and map the results to each object that references them.
        # TODO This is in dire need of refactoring, or a complete overhaul
        hints = {}
        for field_name, q_obj in document_queryset.items():
            doc = self.get_related_resources()[field_name].document

            # Create a QuerySet based on the query object
            query = doc.objects.filter(q_obj)

            # Don't let MongoDB do the sorting as it won't use the index.
            # Store the ordering so we can do client sorting afterwards.
            ordering = query._ordering or query._get_order_by(query._document._meta['ordering'])
            query = query.order_by()

            # Fetch the results
            results = list(query)

            # Reapply the ordering and add results to the mapping
            if ordering:
                document_queryset[field_name] = sorted(results, cmp_fields(ordering))
            else:
                document_queryset[field_name] = results

            # For each field name, create a map of obj PKs to a list of
            # results they referenced.
            hint_index = {}
            if field_name in self.related_resources_hints.keys():
                hint_field = self.related_resources_hints[field_name]
                for obj in document_queryset[field_name]:
                    hint_field_instance = obj._fields[hint_field]
                    # Don't trigger a query for SafeReferenceFields
                    if SafeReferenceField and isinstance(hint_field_instance, SafeReferenceField):
                        hinted = obj._db_data[hint_field]
                        if hint_field_instance.dbref:
                            hinted = hinted.id
                    else:
                        hinted = str(getattr(obj, hint_field).id)
                    if hinted not in hint_index:
                        hint_index[hinted] = [obj]
                    else:
                        hint_index[hinted].append(obj)

                hints[field_name] = hint_index

        # Assign the results to each object
        # TODO This is in dire need of refactoring, or a complete overhaul
        for obj in objs:
            for field_name, hint_index in hints.items():
                obj_id = obj.id
                if isinstance(obj_id, DBRef):
                    obj_id = obj_id.id
                elif isinstance(obj_id, ObjectId):
                    obj_id = str(obj_id)
                if obj_id not in hint_index:
                    setattr(obj, field_name, [])
                else:
                    setattr(obj, field_name, hint_index[obj_id])

    def apply_filters(self, qs, params=None):
        """
        Given this resource's filters, and the params of the request that's
        currently being processed, apply additional filtering to the queryset
        and return it.
        """
        if params is None:
            params = self.params

        for key, value in params.items():
            # If this is a resource identified by a URI, we need
            # to extract the object id at this point since
            # MongoEngine only understands the object id
            if self.uri_prefix:
                url = urlparse(value)
                uri = url.path
                value = uri.lstrip(self.uri_prefix)

            # special handling of empty / null params
            # http://werkzeug.pocoo.org/docs/0.9/utils/ url_decode returns '' for empty params
            if value == '':
                value = None
            elif value in ['""', "''"]:
                value = ''

            negate = False
            op_name = ''
            parts = key.split('__')
            for i in range(len(parts) + 1, 0, -1):
                field = '__'.join(parts[:i])
                allowed_operators = self._filters.get(field)
                if allowed_operators:
                    parts = parts[i:]
                    break
            if allowed_operators is None:
                continue

            if parts:
                # either an operator or a query lookup!  See what's allowed.
                op_name = parts[-1]
                if op_name in allowed_operators:
                    # operator; drop it
                    parts.pop()
                else:
                    # assume it's part of a lookup
                    op_name = ''
                if parts and parts[-1] == 'not':
                    negate = True
                    parts.pop()

            operator = allowed_operators.get(op_name, None)
            if operator is None:
                continue
            if negate and not operator.allow_negation:
                continue
            if parts:
                field = '%s__%s' % (field, '__'.join(parts))
            field = self._reverse_rename_fields.get(field, field)
            qs = operator().apply(qs, field, value, negate)
        return qs

    def apply_ordering(self, qs, params=None):
        """
        Given this resource's allowed_ordering, and the params of the request
        that's currently being processed, apply ordering to the queryset
        and return it.
        """
        if params is None:
            params = self.params
        if self.allowed_ordering and params.get('_order_by') in self.allowed_ordering:
            order_params = [self._reverse_rename_fields.get(p, p) for p in params['_order_by'].split(',')]
            qs = qs.order_by(*order_params)
        return qs

    def get_skip_and_limit(self, params=None):
        """
        Perform validation and return sanitized values for _skip and _limit
        params of the request that's currently being processed.
        """
        max_limit = self.get_max_limit()
        if params is None:
            params = self.params
        if self.paginate:
            # _limit and _skip validation
            if not isint(params.get('_limit', 1)):
                raise ValidationError({'error': '_limit must be an integer (got "%s" instead).' % params['_limit']})
            if not isint(params.get('_skip', 1)):
                raise ValidationError({'error': '_skip must be an integer (got "%s" instead).' % params['_skip']})
            if params.get('_limit') and int(params['_limit']) > max_limit:
                raise ValidationError({'error': "The limit you set is larger than the maximum limit for this resource (max_limit = %d)." % max_limit})
            if params.get('_skip') and int(params['_skip']) < 0:
                raise ValidationError({'error': '_skip must be a non-negative integer (got "%s" instead).' % params['_skip']})

            limit = min(int(params.get('_limit', self.default_limit)), max_limit)
            # Fetch one more so we know if there are more results.
            return int(params.get('_skip', 0)), limit
        else:
            return 0, max_limit

    def get_objects(self, qs=None, qfilter=None):
        """
        Return objects fetched from the database based on all the parameters
        of the request that's currently being processed.

        Params:
        - Custom queryset can be passed via `qs`. Otherwise `self.get_queryset`
          is used.
        - Pass `qfilter` function to modify the queryset.
        """
        params = self.params

        custom_qs = True
        if qs is None:
            custom_qs = False
            qs = self.get_queryset()

        # If a queryset filter was provided, pass our current queryset in and
        # get a new one out
        if qfilter:
            qs = qfilter(qs)

        # Apply filters and ordering, based on the params supplied by the
        # request
        qs = self.apply_filters(qs, params)
        qs = self.apply_ordering(qs, params)

        # Apply limit and skip to the queryset
        limit = None
        if self.view_method == methods.BulkUpdate:
            # limit the number of objects that can be bulk-updated at a time
            qs = qs.limit(self.bulk_update_limit)
        elif not custom_qs:
            # no need to skip/limit if a custom `qs` was provided
            skip, limit = self.get_skip_and_limit(params)
            qs = qs.skip(skip).limit(limit+1)

        # Needs to be at the end as it returns a list, not a queryset
        if self.select_related:
            qs = qs.select_related()

        # Evaluate the queryset
        objs = list(qs)

        # Raise a validation error if bulk update would result in more than
        # bulk_update_limit updates
        if self.view_method == methods.BulkUpdate and len(objs) >= self.bulk_update_limit:
            raise ValidationError({
                'errors': ["It's not allowed to update more than %d objects at once" % self.bulk_update_limit]
            })

        # Determine the value of has_more
        if self.view_method != methods.BulkUpdate and self.paginate:
            has_more = len(objs) > limit
            if has_more:
                objs = objs[:-1]
        else:
            has_more = None

        # bulk-fetch related resources for moar speed
        if self.related_resources_hints:
            self.fetch_related_resources(objs, self.get_requested_fields(params=params))

        return objs, has_more

    def save_related_objects(self, obj, parent_resources=None):
        if not parent_resources:
            parent_resources = [self]
        else:
            parent_resources += [self]

        if self._dirty_fields:
            for field_name in set(self._dirty_fields) & set(self.get_save_related_fields()):
                try:
                    related_resource = self.get_related_resources()[field_name]
                except KeyError:
                    related_resource = None

                field_instance = getattr(self.document, field_name)

                # If it's a ReferenceField, just save it.
                if isinstance(field_instance, ReferenceField):
                    instance = getattr(obj, field_name)
                    if instance:
                        if related_resource:
                            related_resource().save_object(instance, parent_resources=parent_resources)
                        else:
                            instance.save()

                # If it's a ListField(ReferenceField), save all instances.
                if isinstance(field_instance, ListField) and isinstance(field_instance.field, ReferenceField):
                    instance_list = getattr(obj, field_name)
                    for instance in instance_list:
                        if related_resource:
                            related_resource().save_object(instance, parent_resources=parent_resources)
                        else:
                            instance.save()

    def save_object(self, obj, **kwargs):
        self.save_related_objects(obj, **kwargs)
        obj.save()
        obj.reload()

        self._dirty_fields = None # No longer dirty.

    def get_object_dict(self, data=None, update=False):
        data = self.data or data
        filter_fields = set(self.document._fields.keys())
        if update:
            # We want to update only the fields that appear in the request data
            # rather than re-updating all the document's existing/other fields.
            filter_fields &= set(self._reverse_rename_fields.get(field, field)
                                 for field in self.raw_data.keys())
        update_dict = {field: value for field, value in data.items()
                       if field in filter_fields}
        return update_dict

    def create_object(self, data=None, save=True, parent_resources=None):
        update_dict = self.get_object_dict(data)
        obj = self.document(**update_dict)
        self._dirty_fields = update_dict.keys()
        if save:
            self.save_object(obj)
        return obj

    def update_object(self, obj, data=None, save=True, parent_resources=None):
        subresource = self._subresource(obj)
        if subresource:
            return subresource.update_object(obj, data=data, save=save, parent_resources=parent_resources)

        update_dict = self.get_object_dict(data, update=True)

        self._dirty_fields = []

        for field, value in update_dict.items():
            update = False

            # If we're comparing reference fields, only compare ids without
            # hitting the database
            if hasattr(obj, '_db_data') and isinstance(obj._fields.get(field), ReferenceField):
                db_val = obj._db_data.get(field)
                id_from_obj = db_val and getattr(db_val, 'id', db_val)
                id_from_data = value and getattr(value, 'pk', value)
                if id_from_obj != id_from_data:
                    update = True
            elif not equal(getattr(obj, field), value):
                update = True

            if update:
                setattr(obj, field, value)
                self._dirty_fields.append(field)

        if save:
            self.save_object(obj)
        return obj

    def delete_object(self, obj, parent_resources=None):
        obj.delete()

# Py2/3 compatible way to do metaclasses (or six.add_metaclass)
body = vars(Resource).copy()
body.pop('__dict__', None)
body.pop('__weakref__', None)

Resource = ResourceMeta(Resource.__name__, Resource.__bases__, body)
