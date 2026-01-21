import uuid
from django.contrib.contenttypes.models import ContentType
from rest_framework.pagination import PageNumberPagination
from authentication.helpers import get_file_path as auth_get_file_path  # Reuse multi-tenant file path from auth


def get_file_path(instance, filename):
    # Delegate to authentication's multi-tenant version for consistency
    return auth_get_file_path(instance, filename)


def save_attachments(data, instance, model, context):
    from utils.serializers import SimpleDocumentSerializer  # Moved import inside function to break circular import
    if data is not None:
        for attachment in data:
            content_type = ContentType.objects.get_for_model(model)
            attachment_data = {**attachment, 'content_type': content_type.id, 'object_id': instance.id}
            attachment = SimpleDocumentSerializer(
                data=attachment_data,
                context=context
            )
            attachment.is_valid(raise_exception=True)
            attachment.save()


def get_paginated_queryset(queryset, serializer_class, request, page_size=100):
    paginator = PageNumberPagination()
    paginator.page_size = page_size
    paginated_data = paginator.paginate_queryset(queryset, request)
    serializer = serializer_class(paginated_data, many=True)
    return paginator.get_paginated_response(serializer.data)