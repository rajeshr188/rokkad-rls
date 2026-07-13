from django.db import migrations


ROLE_TYPE_KEYS = [
    "CUSTOMER",
    "SUPPLIER",
    "BORROWER",
    "LENDER",
    "RETAILER",
    "WHOLESALER",
    "MANUFACTURER",
    "EMPLOYEE",
    "AGENT",
    "BROKER",
    "BANK",
    "TRANSPORTER",
    "INSURANCE_PROVIDER",
    "PORTAL_CUSTOMER",
]


def seed_role_types(apps, schema_editor):
    PartyRoleType = apps.get_model("party", "PartyRoleType")

    for index, key in enumerate(ROLE_TYPE_KEYS, start=1):
        label = key.replace("_", " ").title()
        PartyRoleType.objects.update_or_create(
            key=key,
            defaults={
                "label": label,
                "description": "",
                "is_system": True,
                "is_active": True,
                "sort_order": index,
            },
        )


def unseed_role_types(apps, schema_editor):
    PartyRoleType = apps.get_model("party", "PartyRoleType")
    PartyRoleType.objects.filter(key__in=ROLE_TYPE_KEYS, is_system=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("party", "0004_auto_rls_policies"),
    ]

    operations = [
        migrations.RunPython(seed_role_types, unseed_role_types),
    ]
