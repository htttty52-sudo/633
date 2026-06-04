"""
Generate 1000 simulated devices across multiple models with template bindings.
Run: python -m scripts.seed_devices
"""
import random
import hashlib
import sys
from datetime import datetime, timedelta

from sqlalchemy import select, func

from app.database import SessionLocal, engine, Base
from app.models import Device
from app.template_models import ConfigTemplate, TemplateBinding
import app.ota_models  # noqa: F401

MODELS = ["RK3588", "IMX6ULL", "STM32MP1", "AllwinnerH6", "AM335x"]
KERNEL_VERSIONS = ["5.10.110", "5.15.80", "6.1.25", "5.4.210", "6.6.1"]
DEVICE_COUNT = 1000


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        existing_count = db.execute(select(func.count()).select_from(Device)).scalar()
        if existing_count >= DEVICE_COUNT:
            print(f"Already have {existing_count} devices, skipping seed.")
            return

        # Create templates (one per model)
        templates = {}
        for model in MODELS:
            existing = db.execute(
                select(ConfigTemplate).where(ConfigTemplate.name == f"kernel-config-{model}")
            ).scalar_one_or_none()
            if existing:
                templates[model] = existing
                continue

            t = ConfigTemplate(
                name=f"kernel-config-{model}",
                description=f"Standard kernel config for {model}",
                content=(
                    f"# Kernel config for {{{{ model }}}}\n"
                    f"CONFIG_ARCH={model}\n"
                    f"CONFIG_VERSION={{{{ kernel_version }}}}\n"
                    f"CONFIG_PREEMPT=y\n"
                    f"CONFIG_HZ=1000\n"
                    f"CONFIG_MODULES=y\n"
                ),
            )
            db.add(t)
            db.flush()
            templates[model] = t

        print(f"Templates ready: {len(templates)}")

        # Create devices
        created = 0
        for i in range(DEVICE_COUNT):
            model = MODELS[i % len(MODELS)]
            kv = random.choice(KERNEL_VERSIONS)
            device_id = f"DEV-{model}-{i:04d}"

            existing = db.execute(
                select(Device).where(Device.device_id == device_id)
            ).scalar_one_or_none()
            if existing:
                continue

            d = Device(
                device_id=device_id,
                model=model,
                kernel_version=kv,
                is_online=random.random() > 0.15,
                last_heartbeat=datetime.utcnow() - timedelta(seconds=random.randint(0, 120)),
            )
            db.add(d)
            created += 1

            # Batch commit every 100
            if created % 100 == 0:
                db.flush()
                print(f"  Created {created} devices...")

        db.flush()
        print(f"Devices created: {created}")

        # Create bindings (80% of devices)
        binding_count = 0
        for i in range(DEVICE_COUNT):
            if random.random() > 0.8:
                continue

            model = MODELS[i % len(MODELS)]
            device_id = f"DEV-{model}-{i:04d}"
            kv = random.choice(KERNEL_VERSIONS)

            existing_binding = db.execute(
                select(TemplateBinding).where(
                    TemplateBinding.template_id == templates[model].id,
                    TemplateBinding.device_id == device_id,
                )
            ).scalar_one_or_none()
            if existing_binding:
                continue

            expected = hashlib.sha256(f"{model}-{kv}-expected".encode()).hexdigest()
            # 40% have drift
            if random.random() < 0.4:
                current = hashlib.sha256(
                    f"{device_id}-stale-{random.random()}".encode()
                ).hexdigest()
            else:
                current = expected

            binding = TemplateBinding(
                template_id=templates[model].id,
                device_id=device_id,
                expected_config_hash=expected,
                current_config_hash=current,
            )
            db.add(binding)
            binding_count += 1

            if binding_count % 100 == 0:
                db.flush()

        db.commit()
        print(f"Bindings created: {binding_count}")
        print(f"Seed complete: {DEVICE_COUNT} devices, ~{binding_count} bindings, ~{int(binding_count*0.4)} drifted")

    except Exception as e:
        db.rollback()
        print(f"Seed error: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    seed()
