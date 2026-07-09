from django.db import models

from common.models import TenantScopedModel


class Party(TenantScopedModel):
	class PartyType(models.TextChoices):
		CUSTOMER = "customer", "Customer"
		SUPPLIER = "supplier", "Supplier"
		RETAILER = "retailer", "Retailer"
		WHOLESALER = "wholesaler", "Wholesaler"
		KARIGAR = "karigar", "Karigar"
		OTHER = "other", "Other"

	name = models.CharField(max_length=180)
	party_type = models.CharField(max_length=24, choices=PartyType.choices)
	roles = models.JSONField(default=list, blank=True)
	contacts = models.JSONField(default=list, blank=True)
	addresses = models.JSONField(default=list, blank=True)
	documents = models.JSONField(default=list, blank=True)
	is_active = models.BooleanField(default=True)

	class Meta:
		ordering = ["name"]
		indexes = [
			models.Index(fields=["workspace", "party_type"]),
			models.Index(fields=["workspace", "name"]),
			models.Index(fields=["workspace", "is_active"]),
		]

	def __str__(self):
		return self.name
