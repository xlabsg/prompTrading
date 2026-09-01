#!/usr/bin/env python3
"""
Create permanent, reusable invite codes for debugging.
Usage: docker compose exec api python create_debug_invites.py
"""
from datetime import datetime, timezone
from sqlalchemy import select
from control_plane.db import create_db_engine, create_session_factory
from control_plane.models import Base, InviteCode
from app.settings import settings

# Permanent debug invite codes
DEBUG_INVITES = [
    "DEBUG-2026",      # Simple debug code
    "TEST-INVITE",     # Test invite
    "DEV-ACCESS",      # Dev access code
    "ADMIN-DEBUG",     # Admin debug code
    "FOREVER-CODE",    # Forever code
]

def create_permanent_invites():
    """Create or update permanent invite codes for debugging."""
    engine = create_db_engine(settings.db_url)
    session_factory = create_session_factory(engine)
    Base.metadata.create_all(engine)

    created = []
    updated = []

    with session_factory() as db:
        for code in DEBUG_INVITES:
            # Check if invite already exists
            existing = db.execute(
                select(InviteCode).where(InviteCode.code == code)
            ).scalar_one_or_none()

            if existing:
                # Update existing invite to be permanent and reusable
                existing.max_uses = 999999  # Essentially unlimited
                existing.used_count = 0     # Reset usage counter
                existing.expires_at = None  # Never expires
                updated.append(code)
            else:
                # Create new permanent invite
                invite = InviteCode(
                    code=code,
                    max_uses=999999,        # Essentially unlimited
                    used_count=0,
                    expires_at=None,        # Never expires
                    created_by_user_id=None,
                )
                db.add(invite)
                created.append(code)

        db.commit()

    print("=" * 60)
    print("PERMANENT DEBUG INVITE CODES")
    print("=" * 60)

    if created:
        print("\n✅ Created new invite codes:")
        for code in created:
            print(f"   - {code}")

    if updated:
        print("\n🔄 Updated existing invite codes:")
        for code in updated:
            print(f"   - {code}")

    print("\n📋 All available permanent codes:")
    for code in DEBUG_INVITES:
        print(f"   - {code}")

    print("\n⚙️  Usage:")
    print(f"   curl -X POST http://localhost:8000/api/auth/oauth/github/start \\")
    print(f"     -H 'Content-Type: application/json' \\")
    print(f"     -d '{{\"invite_code\": \"{DEBUG_INVITES[0]}\", \"redirect_path\": \"/\"}}'")

    print("\n💡 These codes:")
    print("   - Never expire")
    print("   - Can be used unlimited times")
    print("   - Are perfect for debugging and testing")
    print("=" * 60)

if __name__ == "__main__":
    create_permanent_invites()
