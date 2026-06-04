"""
Generate 1000 simulated devices across multiple models with template bindings.
Syncs expected hashes to Redis for fast drift detection.
Run: python -m scripts.seed_devices
"""
import random
import sys
from datetime import datetime, timedelta

from sqlalchemy import select, func

from app.database import SessionLocal, engine, Base
from app.models import Device
from app.template_models import ConfigTemplate, TemplateBinding
from app.template_engine import (
    render_template, compute_config_hash, get_device_variables,
    simulate_device_config, compute_field_diff_count,
)
from app.dashboard_crud import sync_expected_hashes_to_redis
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
            # Still sync hashes to Redis
            count = sync_expected_hashes_to_redis(db)
            print(f"Synced {count} expected hashes to Redis.")
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

            if created % 100 == 0:
                db.flush()
                print(f"  Created {created} devices...")

        db.flush()
        print(f"Devices created: {created}")

        # Create bindings (80% of devices) with real field-by-field drift
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

            # Render the expected config from template
            template = templates[model]

            class FakeDevice:
                pass
            fake = FakeDevice()
            fake.device_id = device_id
            fake.model = model
            fake.kernel_version = kv
            fake.is_online = True

            variables = get_device_variables(fake)
            rendered = render_template(template.content, variables)
            expected_hash = compute_config_hash(rendered)

            # 40% have drift — mutate random fields in the config
            if random.random() < 0.4:
                drift_target = random.randint(1, 4)
                current_cfg = simulate_device_config(rendered, drift_target)
            else:
                current_cfg = rendered

            current_hash = compute_config_hash(current_cfg)
            actual_diff = compute_field_diff_count(rendered, current_cfg)

            binding = TemplateBinding(
                template_id=template.id,
                device_id=device_id,
                expected_config_hash=expected_hash,
                current_config_hash=current_hash,
                rendered_config=rendered,
                current_config=current_cfg,
                drift_field_count=actual_diff,
            )
            db.add(binding)
            binding_count += 1

            if binding_count % 100 == 0:
                db.flush()

        db.commit()
        print(f"Bindings created: {binding_count}")

        # Sync all expected hashes to Redis
        count = sync_expected_hashes_to_redis(db)
        print(f"Synced {count} expected hashes to Redis.")
        print(f"Seed complete: {DEVICE_COUNT} devices, ~{binding_count} bindings, ~{int(binding_count*0.4)} drifted")

    except Exception as e:
        db.rollback()
        print(f"Seed error: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    seed()
