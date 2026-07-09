from django.db import models

from common.models import TenantScopedModel


class Note(TenantScopedModel):
	title = models.CharField(max_length=160)
	body = models.TextField(blank=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [models.Index(fields=["workspace", "created_at"])]

	def __str__(self):
		return self.title
