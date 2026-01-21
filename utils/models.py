from selectors import SelectSelector
from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import FileExtensionValidator
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from utils.constants import ALLOWED_FILE_EXTS
from utils.helpers import get_file_path
from django.db.models import Q


class SoftDeleteModelManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(~Q(deleted=True))


class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=False)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=False)
    updated_by = models.ForeignKey(get_user_model(), models.DO_NOTHING, null=True, blank=False, related_name="%(app_label)s_%(class)s_updated_by")
    created_by = models.ForeignKey(get_user_model(), models.DO_NOTHING, null=True, blank=False)
    deleted = models.BooleanField(default=False, null=True, blank=True)

    objects = SoftDeleteModelManager()

    class Meta:
        abstract = True
        ordering = ("-id",)

    def delete(self, soft_delete=True):
        if not soft_delete:
            super(BaseModel, self).delete()
        else:
            self.deleted = True
            self.save()

    def save(self, *args, **kwargs):
        return super().save(*args, **kwargs)


class Document(BaseModel):
    file = models.FileField(
        max_length=500,
        upload_to=get_file_path,
        blank=False,
        null=False,
        validators=[FileExtensionValidator(ALLOWED_FILE_EXTS)]
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=['content_type'], name='document_content_type_idx'),
            models.Index(fields=['object_id'], name='document_object_id_idx'),
        ]
        ordering = ("-id",)

    def delete(self):
        super(BaseModel, self).delete()
