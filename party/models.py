from django.conf import settings
from django.db import models, transaction
from django.db.models import Q

from common.models import TenantScopedModel, TimeStampedModel, UUIDModel


def party_document_upload_path(instance, filename):
	return f"party_documents/{instance.party_id}/{filename}"


class PartyCodeSequence(TenantScopedModel):
	key = models.CharField(max_length=32, default="PARTY")
	next_number = models.PositiveIntegerField(default=1)

	class Meta:
		ordering = ["key"]
		constraints = [
			models.UniqueConstraint(fields=["workspace", "key"], name="party_sequence_workspace_key_uniq"),
		]

	def save(self, *args, **kwargs):
		self.key = (self.key or "PARTY").strip().upper()
		super().save(*args, **kwargs)

	def __str__(self):
		return f"{self.workspace_id}:{self.key}"


class Party(TenantScopedModel):
	class PartyType(models.TextChoices):
		INDIVIDUAL = "individual", "Individual"
		ORGANIZATION = "organization", "Organization"
		BANK = "bank", "Bank"
		GOVERNMENT = "government", "Government"
		INTERNAL_WORKSPACE = "internal_workspace", "Internal Workspace"
		OTHER = "other", "Other"
		CUSTOMER = "customer", "Customer"
		SUPPLIER = "supplier", "Supplier"
		RETAILER = "retailer", "Retailer"
		WHOLESALER = "wholesaler", "Wholesaler"
		KARIGAR = "karigar", "Karigar"

	class Status(models.TextChoices):
		ACTIVE = "active", "Active"
		INACTIVE = "inactive", "Inactive"
		BLOCKED = "blocked", "Blocked"
		ARCHIVED = "archived", "Archived"

	class RelationLabel(models.TextChoices):
		SON_OF = "son_of", "Son Of"
		DAUGHTER_OF = "daughter_of", "Daughter Of"
		CARE_OF = "care_of", "Care Of"
		PARENT_OF = "parent_of", "Parent Of"
		FATHER_OF = "father_of", "Father Of"
		WIFE_OF = "wife_of", "Wife Of"
		HUSBAND_OF = "husband_of", "Husband Of"
		OTHER = "other", "Other"

	party_code = models.CharField(max_length=32, blank=True)
	party_type = models.CharField(max_length=32, choices=PartyType.choices)
	display_name = models.CharField(max_length=255, blank=True)
	legal_name = models.CharField(max_length=255, blank=True)
	normalized_name = models.CharField(max_length=255, blank=True)
	relation_label = models.CharField(max_length=16, choices=RelationLabel.choices, blank=True)
	relation_name = models.CharField(max_length=255, blank=True)
	primary_phone = models.CharField(max_length=32, blank=True)
	primary_email = models.EmailField(blank=True)
	profile_photo = models.ImageField(upload_to="party_profiles/", blank=True)
	tax_pan = models.CharField(max_length=16, blank=True)
	gstin = models.CharField(max_length=24, blank=True)
	risk_level = models.CharField(max_length=32, blank=True)
	credit_hold = models.BooleanField(default=False)
	status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
	metadata = models.JSONField(default=dict, blank=True)
	updated_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="party_updated",
	)

	# Backward-compatible fields retained while callers migrate to normalized tables.
	name = models.CharField(max_length=180)
	roles = models.JSONField(default=list, blank=True)
	contacts = models.JSONField(default=list, blank=True)
	addresses = models.JSONField(default=list, blank=True)
	documents = models.JSONField(default=list, blank=True)
	is_active = models.BooleanField(default=True)

	class Meta:
		ordering = ["display_name", "name"]
		constraints = [
			models.UniqueConstraint(fields=["workspace", "party_code"], name="party_workspace_code_uniq"),
		]
		indexes = [
			models.Index(fields=["workspace", "party_code"]),
			models.Index(fields=["workspace", "display_name"]),
			models.Index(fields=["workspace", "party_type"]),
			models.Index(fields=["workspace", "normalized_name"]),
			models.Index(fields=["workspace", "tax_pan"]),
			models.Index(fields=["workspace", "gstin"]),
			models.Index(fields=["workspace", "status", "party_type"]),
			models.Index(fields=["workspace", "credit_hold"]),
			models.Index(fields=["workspace", "is_active"]),
			models.Index(fields=["workspace", "name"]),
		]

	def _next_party_code(self):
		with transaction.atomic():
			sequence, _ = PartyCodeSequence.objects.select_for_update().get_or_create(
				workspace=self.workspace,
				key="PARTY",
				defaults={"created_by": self.created_by, "next_number": 1},
			)
			while True:
				candidate = f"P-{sequence.next_number:06d}"
				sequence.next_number += 1
				sequence.save(update_fields=["next_number", "updated_at"])
				if not Party.objects.filter(workspace=self.workspace, party_code=candidate).exists():
					return candidate

	def save(self, *args, **kwargs):
		self.display_name = (self.display_name or self.name or "").strip()
		self.name = (self.name or self.display_name or "").strip()
		if not self.display_name:
			self.display_name = self.name
		if not self.normalized_name:
			self.normalized_name = self.display_name.lower().strip()
		self.tax_pan = (self.tax_pan or "").strip().upper()
		self.gstin = (self.gstin or "").strip().upper()
		if self.is_active and self.status in {self.Status.INACTIVE, self.Status.ARCHIVED}:
			self.status = self.Status.ACTIVE
		if not self.is_active and self.status == self.Status.ACTIVE:
			self.status = self.Status.INACTIVE
		if not self.party_code and self.workspace_id:
			self.party_code = self._next_party_code()
		super().save(*args, **kwargs)

	def __str__(self):
		return self.display_name or self.name


class PartyRoleType(UUIDModel, TimeStampedModel):
	key = models.CharField(max_length=64, unique=True, db_index=True)
	label = models.CharField(max_length=128)
	description = models.TextField(blank=True)
	is_system = models.BooleanField(default=True)
	is_active = models.BooleanField(default=True)
	sort_order = models.PositiveIntegerField(default=0)

	class Meta:
		ordering = ["sort_order", "label"]

	def save(self, *args, **kwargs):
		self.key = (self.key or "").strip().upper()
		self.label = (self.label or "").strip()
		super().save(*args, **kwargs)

	def __str__(self):
		return self.label


class PartyRole(TenantScopedModel):
	class Status(models.TextChoices):
		ACTIVE = "active", "Active"
		INACTIVE = "inactive", "Inactive"
		ENDED = "ended", "Ended"

	party = models.ForeignKey(Party, on_delete=models.CASCADE, related_name="party_roles")
	role_type = models.ForeignKey(PartyRoleType, on_delete=models.PROTECT, related_name="party_roles")
	status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
	segment = models.CharField(max_length=64, blank=True)
	effective_from = models.DateField(null=True, blank=True)
	effective_to = models.DateField(null=True, blank=True)
	metadata = models.JSONField(default=dict, blank=True)

	class Meta:
		ordering = ["party", "role_type"]
		constraints = [
			models.UniqueConstraint(
				fields=["workspace", "party", "role_type"],
				condition=Q(status="active"),
				name="party_role_one_active_per_type",
			),
		]
		indexes = [
			models.Index(fields=["workspace", "party", "status"]),
			models.Index(fields=["workspace", "role_type", "status"]),
		]

	def __str__(self):
		return f"{self.party} - {self.role_type}"


class PartyContactMethod(TenantScopedModel):
	class ContactType(models.TextChoices):
		PHONE = "phone", "Phone"
		MOBILE = "mobile", "Mobile"
		WHATSAPP = "whatsapp", "WhatsApp"
		EMAIL = "email", "Email"
		WEBSITE = "website", "Website"
		OTHER = "other", "Other"

	party = models.ForeignKey(Party, on_delete=models.CASCADE, related_name="contact_methods")
	contact_type = models.CharField(max_length=16, choices=ContactType.choices)
	label = models.CharField(max_length=64, blank=True)
	value = models.CharField(max_length=255)
	normalized_value = models.CharField(max_length=255, blank=True)
	is_primary = models.BooleanField(default=False)
	is_verified = models.BooleanField(default=False)

	class Meta:
		ordering = ["party", "contact_type", "-is_primary", "value"]
		constraints = [
			models.UniqueConstraint(
				fields=["workspace", "party", "contact_type"],
				condition=Q(is_primary=True),
				name="party_contact_one_primary_per_type",
			),
		]
		indexes = [
			models.Index(fields=["workspace", "party", "contact_type"]),
			models.Index(fields=["workspace", "normalized_value"]),
		]

	def save(self, *args, **kwargs):
		self.normalized_value = (self.normalized_value or self.value or "").strip().lower()
		super().save(*args, **kwargs)

	def __str__(self):
		return f"{self.party} - {self.contact_type}: {self.value}"


class PartyAddress(TenantScopedModel):
	class AddressType(models.TextChoices):
		REGISTERED = "registered", "Registered"
		BILLING = "billing", "Billing"
		SHIPPING = "shipping", "Shipping"
		HOME = "home", "Home"
		WORK = "work", "Work"
		KYC = "kyc", "KYC"
		OTHER = "other", "Other"

	party = models.ForeignKey(Party, on_delete=models.CASCADE, related_name="party_addresses")
	address_type = models.CharField(max_length=16, choices=AddressType.choices)
	line1 = models.CharField(max_length=255)
	line2 = models.CharField(max_length=255, blank=True)
	area = models.CharField(max_length=128, blank=True)
	city = models.CharField(max_length=128)
	state = models.CharField(max_length=128, blank=True)
	postal_code = models.CharField(max_length=24, blank=True)
	country = models.CharField(max_length=2, default="IN")
	is_default = models.BooleanField(default=False)
	is_verified = models.BooleanField(default=False)

	class Meta:
		ordering = ["party", "address_type", "-is_default", "city"]
		constraints = [
			models.UniqueConstraint(
				fields=["workspace", "party", "address_type"],
				condition=Q(is_default=True),
				name="party_address_one_default_per_type",
			),
		]
		indexes = [
			models.Index(fields=["workspace", "party", "address_type"]),
			models.Index(fields=["workspace", "city", "state"]),
		]

	def save(self, *args, **kwargs):
		self.country = (self.country or "IN").upper()
		super().save(*args, **kwargs)

	def __str__(self):
		return f"{self.party} - {self.address_type}: {self.city}"


class PartyIdentifier(TenantScopedModel):
	class IdentifierType(models.TextChoices):
		PAN = "pan", "PAN"
		AADHAAR = "aadhaar", "Aadhaar"
		GSTIN = "gstin", "GSTIN"
		CIN = "cin", "CIN"
		UDYAM = "udyam", "UDYAM"
		PASSPORT = "passport", "Passport"
		DRIVING_LICENSE = "driving_license", "Driving License"
		OTHER = "other", "Other"

	party = models.ForeignKey(Party, on_delete=models.CASCADE, related_name="party_identifiers")
	identifier_type = models.CharField(max_length=32, choices=IdentifierType.choices)
	value = models.CharField(max_length=128)
	masked_value = models.CharField(max_length=128, blank=True)
	value_hash = models.CharField(max_length=128, blank=True)
	is_verified = models.BooleanField(default=False)
	verified_at = models.DateTimeField(null=True, blank=True)
	expires_on = models.DateField(null=True, blank=True)
	metadata = models.JSONField(default=dict, blank=True)

	class Meta:
		ordering = ["party", "identifier_type"]
		constraints = [
			models.UniqueConstraint(
				fields=["workspace", "party", "identifier_type"],
				name="party_identifier_one_per_type",
			),
		]
		indexes = [
			models.Index(fields=["workspace", "identifier_type", "value_hash"]),
			models.Index(fields=["workspace", "party", "identifier_type"]),
		]

	def __str__(self):
		return f"{self.party} - {self.identifier_type}"


class PartyDocument(TenantScopedModel):
	class DocumentType(models.TextChoices):
		KYC = "kyc", "KYC"
		TAX = "tax", "Tax"
		CONTRACT = "contract", "Contract"
		LICENSE = "license", "License"
		OTHER = "other", "Other"

	party = models.ForeignKey(Party, on_delete=models.CASCADE, related_name="party_documents")
	document_type = models.CharField(max_length=32, choices=DocumentType.choices)
	title = models.CharField(max_length=255)
	file = models.FileField(upload_to=party_document_upload_path, blank=True)
	identifier = models.ForeignKey(
		PartyIdentifier,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="party_documents",
	)
	is_verified = models.BooleanField(default=False)
	verified_at = models.DateTimeField(null=True, blank=True)
	expires_on = models.DateField(null=True, blank=True)
	metadata = models.JSONField(default=dict, blank=True)

	class Meta:
		ordering = ["party", "document_type", "title"]
		indexes = [
			models.Index(fields=["workspace", "party", "document_type"]),
			models.Index(fields=["workspace", "expires_on"]),
		]

	def __str__(self):
		return f"{self.party} - {self.title}"


class PartyRelationship(TenantScopedModel):
	class RelationshipType(models.TextChoices):
		CONTACT_PERSON = "contact_person", "Contact Person"
		EMPLOYER = "employer", "Employer"
		EMPLOYEE = "employee", "Employee"
		BROKER = "broker", "Broker"
		AGENT = "agent", "Agent"
		RELATED_BUSINESS = "related_business", "Related Business"
		FAMILY = "family", "Family"
		OTHER = "other", "Other"

	from_party = models.ForeignKey(Party, on_delete=models.CASCADE, related_name="relationships_from")
	to_party = models.ForeignKey(Party, on_delete=models.CASCADE, related_name="relationships_to")
	relationship_type = models.CharField(max_length=32, choices=RelationshipType.choices)
	notes = models.TextField(blank=True)
	is_active = models.BooleanField(default=True)

	class Meta:
		ordering = ["from_party", "relationship_type", "to_party"]
		constraints = [
			models.UniqueConstraint(
				fields=["workspace", "from_party", "to_party", "relationship_type"],
				name="party_relationship_unique_type",
			),
			models.CheckConstraint(
				condition=~Q(from_party=models.F("to_party")),
				name="party_relationship_not_self",
			),
		]
		indexes = [
			models.Index(fields=["workspace", "from_party", "relationship_type"]),
			models.Index(fields=["workspace", "to_party", "relationship_type"]),
		]

	def __str__(self):
		return f"{self.from_party} -> {self.to_party} ({self.relationship_type})"
