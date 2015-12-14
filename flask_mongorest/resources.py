import json
import datetime
import dateutil.parser
import mongoengine

from bson.dbref import DBRef
from bson.objectid import ObjectId
from flask import request, url_for
from urlparse import urlparse
from mongoengine.base.proxy import DocumentProxy
from mongoengine.fields import EmbeddedDocumentField, ListField, ReferenceField, GenericReferenceField, SafeReferenceField
from mongoengine.fields import DateTimeField, DictField
from werkzeug.datastructures import MultiDict

from cleancat import ValidationError as SchemaValidationError
from flask.ext.mongorest.exceptions import ValidationError, UnknownFieldError
from flask.ext.mongorest.utils import cmp_fields, isbound, isint, equal
from flask.ext.mongorest.utils import MongoEncoder


class ResourceMeta(type):
    def __init__(cls, name, bases, classdict):
        if classdict.get('__metaclass__') is not ResourceMeta:
            for document,resource in cls.child_document_resources.iteritems():
                if resource == name:
                    cls.child_document_resources[document] = cls
        type.__init__(cls, name, bases, classdict)

class Resource(object):
    document = None # required
    fields = None
    readonly_fields = ['id']
    schema = None
    related_resources = {}
    related_resources_hints = {} #@todo this should be integrated into the related_resources dict, possibly as a tuple
    save_related_fields = []
    rename_fields = {}
    child_document_resources = {}
    paginate = True
    select_related = False
    allowed_ordering = []
    uri_prefix = None # Must start and end with a "/"
    max_limit = 100 # cap the number of records in the _limit param to avoid DDoS'ing the API.
    default_limit = 100 # default limit if no _limit is specified

    __metaclass__ = ResourceMeta

    def __init__(self):
        doc_fields = self.document._fields.keys()
        if self.fields == None:
            self.fields = doc_fields
        self._related_resources = self.get_related_resources()
        self._rename_fields = self.get_rename_fields()
        self._reverse_rename_fields = {}
        for k, v in self._rename_fields.iteritems():
            self._reverse_rename_fields[v] = k
        assert len(self._rename_fields) == len(self._reverse_rename_fields), \
            'Cannot rename multiple fields to the same name'
        self._filters = self.get_filters()
        self._child_document_resources = self.get_child_document_resources()
        self.data = None
        self._dirty_fields = None

    @property
    def params(self):
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
        if not hasattr(self, '_raw_data'):
            if request.method in ('PUT', 'POST') or request.data:
                if request.mimetype and 'json' not in request.mimetype:
                    raise ValidationError({'error': "Please send valid JSON with a 'Content-Type: application/json' header."})
                if request.headers.get('Transfer-Encoding') == 'chunked':
                    raise ValidationError({'error': "Chunked Transfer-Encoding is not supported."})

                try:
                    self._raw_data = json.loads(request.data, parse_constant=self._enforce_strict_json)
                except ValueError:
                    raise ValidationError({'error': 'The request contains invalid JSON.'})
                if not isinstance(self._raw_data, dict):
                    raise ValidationError({'error': 'JSON data must be a dict.'})
            else:
                self._raw_data = {}

        return self._raw_data

    @classmethod
    def uri(self, path):
        """This generates a URI reference for the given path"""
        if self.uri_prefix:
            ret = self.uri_prefix+path
            return ret
        else:
            raise ValueError("Cannot generate URI for resources that do not specify a uri_prefix")

    @classmethod
    def _url(self, path):
        """This generates a complete URL for the given path.  Requires application context."""
        if self.uri_prefix:
            url = url_for(self.uri_prefix.lstrip("/").rstrip("/"),_external=True)
            ret = url+path
            return ret
        else:
            raise ValueError("Cannot generate URL for resources that do not specify a uri_prefix")

    def get_fields(self):
        return self.fields

    def get_optional_fields(self):
        return []

    def get_requested_fields(self, **kwargs):
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
        if include_all or only_fields == None:
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
        return self.child_document_resources

    def get_filters(self):
        filters = {}
        for field, operators in getattr(self, 'filters', {}).iteritems():
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

    def serialize(self, obj, **kwargs):
        if not obj:
            return {}

        # If a subclass of an obj has been called with a base class' resource,
        # use the subclass-specific serialization
        if obj.__class__ in self._child_document_resources \
        and self._child_document_resources[obj.__class__] != self.__class__:
            return obj and self._child_document_resources[obj.__class__]().serialize_field(obj, **kwargs)

        def get(obj, field_name, field_instance=None):
            """
            @TODO needs significant cleanup
            """

            has_field_instance = bool(field_instance)
            field_instance = field_instance or \
                             self.document._fields.get(field_name, None) or \
                             getattr(self.document, field_name, None)

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
                    return field_value and \
                           not isinstance(field_value, DBRef) and \
                           self._related_resources[field_name]().serialize_field(field_value, **kwargs)
                else:
                    if isinstance(field_value, DocumentProxy):
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
                        for (key, elem) in field_value.iteritems()
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
                                     for (k, v) in value.iteritems())
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
        pass

    def value_for_field(self, obj, field):
        # If we specify a field which doesn't exist on the resource or on the
        # object, this method lets us return a custom value.
        raise UnknownFieldError

    def validate_request(self, obj=None):
        # Don't work on original raw data, we may reuse the resource for bulk updates.
        self.data = self.raw_data.copy()

        # Do renaming in two passes to prevent potential multiple renames depending on dict traversal order.
        # E.g. if a -> b, b -> c, then a should never be renamed to c.
        fields_to_delete = []
        fields_to_update = {}
        for k, v in self._rename_fields.iteritems():
            if self.data.has_key(v):
                fields_to_update[k] = self.data[v]
                fields_to_delete.append(v)
        for k in fields_to_delete:
            del self.data[k]
        for k, v in fields_to_update.iteritems():
            self.data[k] = v

        if self.schema:
            if request.method == 'PUT' and obj != None:
                obj_data = dict([(key, getattr(obj, key)) for key in obj._fields.keys()])
            else:
                obj_data = None

            schema = self.schema(self.data, obj_data)
            try:
                self.data = schema.full_clean()
            except SchemaValidationError:
                raise ValidationError({'field-errors': schema.field_errors, 'errors': schema.errors })

    def get_queryset(self):
        return self.document.objects

    def get_object(self, pk, qfilter=None):
        qs = self.get_queryset()
        # If a queryset filter was provided, pass our current
        # queryset in and get a new one out
        if qfilter:
            qs = qfilter(qs)
        return qs.get(pk=pk)

    def fetch_related_resources(self, objs, only_fields=None):
        document_queryset = {}
        for obj in objs:
            for field_name in self.related_resources_hints.keys():
                if only_fields != None and field_name not in only_fields:
                    continue
                resource = self.get_related_resources()[field_name]
                method = getattr(obj, field_name)
                if callable(method):
                    q = method()
                    if field_name in document_queryset.keys():
                        document_queryset[field_name] = (document_queryset[field_name] | q._query_obj)
                    else:
                        document_queryset[field_name] = q._query_obj

        hints = {}
        for k,v in document_queryset.iteritems():
            doc = self.get_related_resources()[k].document

            query = doc.objects.filter(v)

            # Don't let MongoDB do the sorting as it won't use the index.
            # Store the ordering so we can do client sorting afterwards.
            ordering = query._ordering or query._get_order_by(query._document._meta['ordering'])
            query = query.order_by()

            results = [o for o in query] # don't use list() because mongoengine will do a count query

            if ordering:
                document_queryset[k] = sorted(results, cmp_fields(ordering))
            else:
                document_queryset[k] = results

            hint_index = {}
            if k in self.related_resources_hints.keys():
                hint_field = self.related_resources_hints[k]
                for obj in document_queryset[k]:
                    hint_field_instance = obj._fields[hint_field]
                    # Don't trigger a query for SafeReferenceFields
                    if isinstance(hint_field_instance, SafeReferenceField):
                        hinted = obj._db_data[hint_field]
                        if hint_field_instance.dbref:
                            hinted = hinted.id
                    else:
                        hinted = str(getattr(obj, hint_field).id)
                    if hinted not in hint_index:
                        hint_index[hinted] = [obj]
                    else:
                        hint_index[hinted].append(obj)

                hints[k] = hint_index

        for obj in objs:
            for field, hint_index in hints.iteritems():
                obj_id = obj.id
                if isinstance(obj_id, DBRef):
                    obj_id = obj_id.id
                elif isinstance(obj_id, ObjectId):
                    obj_id = str(obj_id)
                if obj_id not in hint_index.keys():
                    setattr(obj, field, [])
                    continue
                setattr(obj, field, hint_index[obj_id])

    def apply_filters(self, qs, params=None):
        if params is None:
            params = self.params

        for key, value in params.iteritems():
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
        if params is None:
            params = self.params
        if self.allowed_ordering and params.get('_order_by') in self.allowed_ordering:
            order_params = [self._reverse_rename_fields.get(p, p) for p in params['_order_by'].split(',')]
            qs = qs.order_by(*order_params)
        return qs

    def get_skip_and_limit(self, params=None):
        if params is None:
            params = self.params
        if self.paginate:
            # _limit and _skip validation
            if not isint(params.get('_limit', 1)):
                raise ValidationError({'error': '_limit must be an integer (got "%s" instead).' % params['_limit']})
            if not isint(params.get('_skip', 1)):
                raise ValidationError({'error': '_skip must be an integer (got "%s" instead).' % params['_skip']})
            if params.get('_limit') and int(params['_limit']) > self.max_limit:
                raise ValidationError({'error': "The limit you set is larger than the maximum limit for this resource (max_limit = %d)." % self.max_limit})
            if params.get('_skip') and int(params['_skip']) < 0:
                raise ValidationError({'error': '_skip must be a non-negative integer (got "%s" instead).' % params['_skip']})

            limit = min(int(params.get('_limit', self.default_limit)), self.max_limit)
            # Fetch one more so we know if there are more results.
            return int(params.get('_skip', 0)), limit
        else:
            return 0, self.max_limit

    def get_objects(self, all=False, qs=None, qfilter=None):
        params = self.params

        custom_qs = True
        if qs is None:
            custom_qs = False
            qs = self.get_queryset()

        # If a queryset filter was provided, pass our current
        # queryset in and get a new one out
        if qfilter:
            qs = qfilter(qs)

        qs = self.apply_filters(qs, params)
        qs = self.apply_ordering(qs, params)

        limit = None
        if not custom_qs and not all:
            skip, limit = self.get_skip_and_limit(params)
            qs = qs.skip(skip).limit(limit+1)

        # Needs to be at the end as it returns a list.
        if self.select_related:
            qs = qs.select_related()

        if limit is not None and self.paginate:
            # It is OK to evaluate the queryset as we will do so anyway.
            qs = [o for o in qs] # don't use list() because mongoengine will do a count query
            has_more = len(qs) == limit+1
            if has_more:
                qs = qs[:-1]
        else:
            has_more = None

        # bulk-fetch related resources for moar speed
        if self.related_resources_hints:
            self.fetch_related_resources(qs, self.get_requested_fields(params=params))

        return qs, has_more

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
        update_dict = self.get_object_dict(data, update=True)

        self._dirty_fields = []

        for field, value in update_dict.items():
            update = False

            # If we're comparing reference fields, only compare ids without
            # hitting the database
            if isinstance(obj._fields.get(field), ReferenceField):
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

