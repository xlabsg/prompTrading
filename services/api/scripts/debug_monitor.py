#!/usr/bin/env python3
"""Debug script to test position monitoring"""

import sys
sys.path.insert(0, '/app')

from sqlalchemy import select

from control_plane.db import create_db_engine, create_session_factory
from control_plane.models import TradingConfig, TradingSession, StrategyExchangeAccount
from control_plane.enums import TradingSessionStatus
from app.trading_engine.monitor import PositionMonitor
from app.settings import settings

def main():
    engine = create_db_engine(settings.db_url)
    Session = create_session_factory(engine)

    with Session() as db:
        # Get active trading session
        session = db.execute(
            select(TradingSession)
            .where(TradingSession.status.in_([TradingSessionStatus.STARTING, TradingSessionStatus.RUNNING]))
        ).scalar_one_or_none()

        if not session:
            print("No active trading session found")
            return

        print(f"Found session: {session.id}")

        # Get config
        config = db.execute(
            select(TradingConfig).where(TradingConfig.id == session.config_id)
        ).scalar_one()

        print(f"Config: {config.exchange} {config.symbol}")

        # Get account
        account = None
        if session.exchange_account_id:
            account = db.get(StrategyExchangeAccount, session.exchange_account_id)
        if not account:
            print("No exchange account found")
            return

        # Create monitor
        monitor = PositionMonitor(config, session.id, db, account)

        print("Testing update_positions()...")
        try:
            monitor.update_positions()
            print("Success!")
        except Exception as e:
            print(f"FAILED: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
