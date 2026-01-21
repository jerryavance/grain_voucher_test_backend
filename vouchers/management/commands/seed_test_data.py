import uuid
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from hubs.models import Hub
from vouchers.models import GrainType, QualityGrade, PriceFeed
from django.contrib.auth import get_user_model
import random

User = get_user_model()

class Command(BaseCommand):
    help = "Seed large test data for GrainTypes, QualityGrades, Hubs, and PriceFeeds"

    def handle(self, *args, **kwargs):
        self.stdout.write("Seeding test data...")

        # -----------------------
        # Create GrainTypes
        # -----------------------
        grain_names = ["Maize", "Rice", "Beans", "Wheat", "Sorghum", "Millet", "Barley", "Oats"]
        grain_objs = []
        for name in grain_names:
            grain, created = GrainType.objects.get_or_create(name=name)
            grain_objs.append(grain)
            if created:
                self.stdout.write(f"Created GrainType: {name}")

        # -----------------------
        # Create QualityGrades
        # -----------------------
        # Adjusted seeding for QualityGrades
        quality_grades = [
            {"name": "A", "min_moisture": 12, "max_moisture": 14, "description": "Top quality"},
            {"name": "B", "min_moisture": 14, "max_moisture": 16, "description": "Medium quality"},
            {"name": "C", "min_moisture": 16, "max_moisture": 18, "description": "Low quality"},
            {"name": "D", "min_moisture": 18, "max_moisture": 20, "description": "Poor quality"},
        ]

        for grain in grain_objs:  # if you have GrainType objects
            for qg in quality_grades:
                qg_name = f"{grain.name} Grade {qg['name']}"
                QualityGrade.objects.get_or_create(
                    name=qg_name,
                    min_moisture=qg["min_moisture"],
                    max_moisture=qg["max_moisture"],
                    description=qg["description"]
                )
        # -----------------------
        # Create Hubs
        # -----------------------
        hubs = []
        for i in range(1, 21):  # 20 Hubs
            hub_name = f"Test Hub {i}"
            hub, created = Hub.objects.get_or_create(
                name=hub_name,
                defaults={"location": f"Location {i}"}
            )
            hubs.append(hub)
            if created:
                self.stdout.write(f"Created Hub: {hub_name}")

        # -----------------------
        # Create PriceFeeds
        # -----------------------
        total_pricefeeds = 0
        for hub in hubs:
            for grain in grain_objs:
                for day_offset in range(10):  # 10 days history
                    pf, created = PriceFeed.objects.get_or_create(
                        hub=hub,
                        grain_type=grain,
                        effective_date=date.today() - timedelta(days=day_offset),
                        defaults={"price_per_kg": round(random.uniform(800, 2000), 2)}
                    )
                    if created:
                        total_pricefeeds += 1

        self.stdout.write(self.style.SUCCESS(
            f"Created {len(grain_objs)} GrainTypes, {len(quality_grades)} QualityGrades each, "
            f"{len(hubs)} Hubs, and {total_pricefeeds} PriceFeeds."
        ))
