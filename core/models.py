from django.db import models

from common.models import TimeStampedModel, UUIDModel


class SystemSetting(UUIDModel, TimeStampedModel):
	key = models.SlugField(max_length=100, unique=True)
	value = models.JSONField(default=dict, blank=True)
	description = models.CharField(max_length=255, blank=True)

	class Meta:
		ordering = ["key"]

	def __str__(self):
		return self.key
