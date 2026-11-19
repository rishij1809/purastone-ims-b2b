from django.core.management.base import BaseCommand
from core.services import setup_rbac_groups


class Command(BaseCommand):
    help = "Initializes Pura Stone RBAC Groups and maps model permissions for all 6 discrete roles."

    def handle(self, *args, **options):
        self.stdout.write("Configuring Pura Stone RBAC Groups and Permissions...")
        groups = setup_rbac_groups()
        for role_code, group in groups.items():
            self.stdout.write(self.style.SUCCESS(
                f"  ✓ Configured group '{group.name}' with {group.permissions.count()} permissions."
            ))
        self.stdout.write(self.style.SUCCESS("Pura Stone RBAC architecture successfully initialized."))
