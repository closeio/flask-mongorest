import json
import mongoengine
from flask import request
from bson.dbref import DBRef
from mongoengine.fields import EmbeddedDocumentField, ListField, ReferenceField, DateTimeField
from flask.ext.mongorest.exceptions import ValidationError
import dateutil.parser

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
    form = None
    related_resources = {}
    rename_fields = {}
    child_document_resources = {}
    paginate = True
    select_related = False
    allowed_ordering = []

    __metaclass__ = ResourceMeta

    def __init__(self):
        doc_fields = self.document._fields.keys()
        if self.fields == None:
            self.fields = doc_fields
        self._related_resources = self.get_related_resources()
        self._rename_fields = self.get_rename_fields()
        self._filters = self.get_filters()
        self._child_document_resources = self.get_child_document_resources()
        self.data = {}
        if request.method in ('PUT', 'POST'):
            self.data = json.loads(request.data)
        
    def get_fields(self):
        return self.fields

    def get_related_resources(self):
        return self.related_resources

    def get_rename_fields(self):
        """
        Return (k,v) and (v,k) for all renamed fields to support serialization and deserialization
        @TODO should automatically support model_id for reference fields (only) and model for related_resources
        """
        rename_fields = {}
        for k, v in self.rename_fields.iteritems():
            rename_fields[k] = v
            if not self.rename_fields.has_key(v):
                rename_fields[v] = k
        return rename_fields
    
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

    def serialize(self, obj, params=None):
        if not obj:
            return {}
        
        if obj.__class__ in self._child_document_resources \
        and self._child_document_resources[obj.__class__] != self.__class__:
            return obj and self._child_document_resources[obj.__class__]().serialize(obj)

        def get(obj, field_name, field_instance=None):
            """
            @TODO needs significant cleanup
            """
            field_value = obj if field_instance else getattr(obj, field_name)
            field_instance = field_instance or getattr(self.document, field_name)
            if isinstance(field_instance, (ReferenceField, EmbeddedDocumentField)):
                if field_name in self._related_resources:
                    return field_value and self._related_resources[field_name]().serialize(field_value)
                else:
                    if isinstance(field_value, DBRef):
                        return field_value
                    return field_value and field_value.to_dbref()
            elif isinstance(field_instance, ListField):
                return [get(elem, field_name, field_instance=field_instance.field) for elem in field_value]
            elif callable(field_instance):
                value = field_value()
                if field_name in self._related_resources:
                    if isinstance(value, mongoengine.queryset.QuerySet):
                        return [self._related_resources[field_name]().serialize(o) for o in value]
                return value
            return field_value

        fields = self.get_fields()

        if params and '_fields' in params:
            only_fields = set(params['_fields'].split(','))
        else:
            only_fields = None

        data = {}
        for field in fields:
            renamed_field = self._rename_fields.get(field, field)
            if only_fields != None and renamed_field not in only_fields:
                continue
            if hasattr(self, field):
                data[renamed_field] = getattr(self, field)(obj)
            else:
                data[renamed_field] = get(obj, field)

        return data

    def validate_request(self, obj=None):
        # @TODO this should rename form fields otherwise in a resource you could say "model_id" and in a form still have to use "model".
        for k, v in self._rename_fields.iteritems():
            if self.data.has_key(v):
                self.data[k] = self.data[v]
                del self.data[v]

        if self.form:
            from werkzeug.datastructures import MultiDict

            if request.method == 'PUT' and obj != None:
                # We treat 'PUT' like 'PATCH', i.e. when fields are not
                # specified, existing values are used.

                # TODO: This is not implemented properly for nested objects yet.

                obj_data = self.serialize(obj)
                obj_data.update(self.data)

                self.data = obj_data

            # We need to convert JSON data into form data.
            # e.g. { "people": [ { "name": "A" } ] } into { "people-0-name": "A" }
            def json_to_form_data(prefix, json_data):
                form_data = {}
                for k, v in json_data.iteritems():
                    if isinstance(v, list): # FieldList
                        for n, el in enumerate(v):
                            form_data.update(json_to_form_data('%s%s-%d-' % (prefix, k, n), el))
                    else:
                        if isinstance(v, dict): # DictField
                            v = json.dumps(v)
                        form_data['%s%s' % (prefix, k)] = v
                return form_data

            json_data = json_to_form_data('', self.data)
            data = MultiDict(json_data)
            form = self.form(data, csrf_enabled=False)

            if not form.validate():
                raise ValidationError({'field-errors': form.errors})

            self.data = form.data

    def get_queryset(self):
        return self.document.objects

    def get_object(self, pk):
        return self.get_queryset().get(pk=pk)
   
    def get_objects(self):
        params = request.args
        qs = self.get_queryset()
        for key in params:
            value = params[key]
            operator = None
            negate = False
            op_name = ''
            parts = key.split('__')
            if len(parts) > 1:
                op_name = parts.pop()
                if parts[-1] == 'not':
                    negate = True
                    parts.pop()
            field = parts.pop()
            allowed_operators = self._filters.get(field, {})
            if op_name not in allowed_operators.keys():
                continue
            operator = allowed_operators[op_name]
            field = self._rename_fields.get(field, field)
            qs = operator().apply(qs, field, value, negate)
        if self.paginate:
            qs = qs.skip(int(params.get('_skip', 0))).limit(int(params.get('_limit', 100)))
        if self.allowed_ordering and params.get('_order_by', None) in self.allowed_ordering:
            qs = qs.order_by(params['_order_by'])
        # Needs to be at the end as it returns a list.
        if self.select_related:
            qs = qs.select_related()
        return qs

    def _get(self, method, data, field_name, field_instance=None, parent_resources=None):
        """
        @TODO needs significant cleanup
        """
        if not parent_resources:
            parent_resources = []

        field_data_value = data if field_instance else data[field_name]
        field_instance = field_instance or getattr(self.document, field_name)

        if isinstance(field_instance, ReferenceField):
            if field_name in self._related_resources:
                return self.related_resources[field_name]().create_object(data=field_data_value, save=True, parent_resources=parent_resources+[self])
            else:
                if isinstance(field_data_value, mongoengine.Document):
                    return field_data_value
                return field_data_value and field_instance.document_type.objects.get(pk=field_data_value).to_dbref()

        elif isinstance(field_instance, DateTimeField):
            return field_data_value and dateutil.parser.parse(field_data_value)

        elif isinstance(field_instance, EmbeddedDocumentField):
            if field_name in self._related_resources:
                return self.related_resources[field_name]().create_object(data=field_data_value, save=False, parent_resources=parent_resources+[self])
            else:
                return {} # dummy embedded document

        elif isinstance(field_instance, ListField):
            def expand_list(inner_field, inner_data):
                if isinstance(inner_field, ListField):
                    return [expand_list(inner_field.field, elem) for elem in inner_data]
                elif isinstance(inner_field, EmbeddedDocumentField):
                    return self.related_resources[field_name]().create_object(data=inner_data, save=False, parent_resources=parent_resources+[self])
                else:
                    return self._get(method, inner_data, field_name, field_instance=inner_field, parent_resources=parent_resources)
            return [expand_list(field_instance.field, elem) for elem in field_data_value]

        else:
            return field_data_value

    def _save(self, obj):
        try:
            obj.save()
        except mongoengine.ValidationError, e:
            def serialize_errors(errors):
                if hasattr(errors, 'iteritems'):
                    return {k: serialize_errors(v) for k, v in errors.iteritems()}
                else:
                    return str(errors)
            raise ValidationError({'field-errors': serialize_errors(e.errors)})

    def create_object(self, data=None, save=True, parent_resources=None):
        kwargs = {}
        data = data or self.data
        for field in self.get_fields():
            if field in self.document._fields.keys() and field not in self.readonly_fields and (type(data) is list or (type(data) is dict and data.has_key(field))): 
                kwargs[field] = self._get('create_object', data, field, parent_resources=parent_resources) 
        obj = self.document(**kwargs)
        if save:
            self._save(obj)
        return obj

    def update_object(self, obj, data=None, save=True, parent_resources=None):
        data = data or self.data
        for field in self.get_fields():
            if field in self.document._fields.keys() and field not in self.readonly_fields and field in data:
                if field in self._related_resources:
                    field_instance = getattr(self.document, field)
                    if isinstance(field_instance, ReferenceField) or (isinstance(field_instance, ListField) and isinstance(field_instance.field, ReferenceField)):
                        continue # Not implemented.
                setattr(obj, field, self._get('update_object', data, field, parent_resources=parent_resources))
        if save:
            self._save(obj)
        return obj

    def delete_object(self, obj, parent_resources=None):
        obj.delete()
