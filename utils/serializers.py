from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db import transaction
from collections import OrderedDict
from authentication.models import Hub, GrainUser
from utils.models import Document


class SimplestUser(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ('id', 'first_name', 'last_name', 'phone_number', 'role', 'hub')


class CreateOnlyCurrentUserDefault(serializers.CurrentUserDefault):
    def set_context(self, serializer_field):
        self.is_update = serializer_field.parent and serializer_field.parent.instance is not None

    def __call__(self, serializer_field):
        user = super(CreateOnlyCurrentUserDefault, self).__call__(serializer_field)
        if user and user.is_authenticated:
            return user


class NestedModelSerializer(serializers.ModelSerializer):

    @transaction.atomic
    def create(self, validated_data):
        return self.nested_save_override(validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        return self.nested_save_override(validated_data, instance=instance)

    def nested_save_override(self, validated_data, instance=None):
        nested_method_models = []
        nested_data = []

        field_source_map = dict()
        for field_key in self.get_fields():
            field_value = self.get_fields().get(field_key, None)
            if field_value:
                source = getattr(field_value, 'source', None)
                readOnly = getattr(field_value, 'read_only', False)
                if source and not readOnly:
                    field_source_map[source] = field_key

        for attribute_key in self.validated_data.keys():
            clean_attribute_key = field_source_map.get(
                attribute_key, attribute_key)
            save_method = getattr(
                self, 'save_nested_{}'.format(clean_attribute_key), None)
            attribute_value = self.validated_data.get(attribute_key, None)
            if save_method:
                if attribute_value:
                    nested_method_models.append((save_method, attribute_value))

                validated_data.pop(attribute_key)
            elif type(attribute_value) in [dict, list]:
                serializer_field = self.get_fields().get(clean_attribute_key, None)
                if serializer_field:
                    serializer_field_child = getattr(
                        serializer_field, 'child', None)

                    if serializer_field_child:
                        serializer_class = serializer_field_child.__class__
                    else:
                        serializer_class = serializer_field.__class__

                    if serializer_class and issubclass(serializer_class, serializers.Serializer):
                        fk_keys = []
                        if serializer_class.Meta and serializer_class.Meta.model and self.Meta and self.Meta.model:
                            for model_field in serializer_class.Meta.model._meta.get_fields():
                                if model_field.related_model == self.Meta.model:
                                    fk_keys.append(model_field.name)
                        if isinstance(attribute_value, list):
                            for single_attribute_value in attribute_value:
                                nested_data.append(
                                    (clean_attribute_key, single_attribute_value, serializer_class, fk_keys))
                        else:
                            nested_data.append(
                                (clean_attribute_key, attribute_value, serializer_class, fk_keys))
                    else:
                        continue

                validated_data.pop(attribute_key)

            if type(attribute_value) in [dict, OrderedDict]:
                attribute_value_object_id = attribute_value.get('id', None)
                if attribute_value_object_id:
                    serializer_field = self.get_fields().get(clean_attribute_key, None)
                    serializer_class = serializer_field.__class__
                    validated_data[clean_attribute_key] = serializer_class.Meta.model.objects.get(
                        pk=attribute_value_object_id)

        is_created = not bool(instance)
        if instance:
            instance = super(NestedModelSerializer, self).update(
                instance, validated_data)
        else:
            instance = super(NestedModelSerializer,
                             self).create(validated_data)

        try:
            for attribute_details in nested_method_models:
                save_method = attribute_details[0]
                attribute_value = attribute_details[1]
                if save_method and attribute_value:
                    save_method(attribute_value, instance, created=is_created)

            for (k, v, s, r) in nested_data:
                v = dict(v)
                if r:
                    for related_key in r:
                        v[related_key] = instance
                if s.Meta.model:
                    if 'id' in v:
                        s.Meta.model.objects.update_or_create(
                            id=v['id'], defaults=v)
                    else:
                        s.Meta.model.objects.create(**v)
                else:
                    serializer = s(data=v, **dict(context=self.context))
                    serializer.save()
        except Exception as e:
            raise e

        return instance


class SimpleDocumentSerializer(serializers.ModelSerializer):

    class Meta:
        model = Document  # Assuming Document model from utils/models.py
        fields = '__all__'

    def validate(self, attr):
        attr = super().validate(attr)
        attr['created_by'] = self.context.get('request').user
        return attr