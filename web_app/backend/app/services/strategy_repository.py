from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import StrategyVersion, User, UserStrategy
from app.services.strategy_service import validate_strategy_payload


def create_strategy(
    db: Session,
    user: User,
    name: str,
    strategy_json: dict,
    source_template_id: str | None = None,
    change_note: str = "Initial version",
) -> UserStrategy:
    validation = validate_strategy_payload(strategy_json)
    if not validation["ok"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Strategy validation failed", "errors": validation["errors"]},
        )
    symbols = strategy_json.get("universe", {}).get("symbols") or [""]
    strategy = UserStrategy(
        strategy_id=f"usr_{uuid4().hex}",
        owner_id=user.id,
        name=name,
        market=strategy_json.get("market", "a_share"),
        symbol=symbols[0],
        frequency=strategy_json.get("data", {}).get("frequency", "1d"),
        source_template_id=source_template_id,
        status="draft",
        strategy_json=strategy_json,
    )
    db.add(strategy)
    db.flush()
    _add_version(db, strategy, change_note)
    db.commit()
    db.refresh(strategy)
    return strategy


def list_user_strategies(db: Session, user: User) -> list[UserStrategy]:
    return list(
        db.scalars(
            select(UserStrategy)
            .where(UserStrategy.owner_id == user.id)
            .order_by(UserStrategy.updated_at.desc(), UserStrategy.id.desc())
        ).all()
    )


def get_user_strategy(db: Session, user: User, strategy_id: str) -> UserStrategy:
    strategy = db.scalar(
        select(UserStrategy).where(
            UserStrategy.strategy_id == strategy_id,
            UserStrategy.owner_id == user.id,
        )
    )
    if strategy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")
    return strategy


def update_strategy(
    db: Session,
    user: User,
    strategy_id: str,
    name: str | None = None,
    strategy_json: dict | None = None,
    status_value: str | None = None,
    change_note: str = "Updated strategy",
) -> UserStrategy:
    strategy = get_user_strategy(db, user, strategy_id)
    if name is not None:
        strategy.name = name
    if status_value is not None:
        strategy.status = status_value
    if strategy_json is not None:
        validation = validate_strategy_payload(strategy_json)
        if not validation["ok"]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"message": "Strategy validation failed", "errors": validation["errors"]},
            )
        symbols = strategy_json.get("universe", {}).get("symbols") or [strategy.symbol]
        strategy.strategy_json = strategy_json
        strategy.market = strategy_json.get("market", strategy.market)
        strategy.symbol = symbols[0]
        strategy.frequency = strategy_json.get("data", {}).get("frequency", strategy.frequency)
        _add_version(db, strategy, change_note)
    db.commit()
    db.refresh(strategy)
    return strategy


def delete_strategy(db: Session, user: User, strategy_id: str) -> None:
    strategy = get_user_strategy(db, user, strategy_id)
    db.delete(strategy)
    db.commit()


def list_strategy_versions(db: Session, user: User, strategy_id: str) -> list[StrategyVersion]:
    strategy = get_user_strategy(db, user, strategy_id)
    return list(
        db.scalars(
            select(StrategyVersion)
            .where(StrategyVersion.strategy_id == strategy.strategy_id)
            .order_by(StrategyVersion.version.desc())
        ).all()
    )


def _add_version(db: Session, strategy: UserStrategy, change_note: str) -> None:
    latest = db.scalar(
        select(func.max(StrategyVersion.version)).where(
            StrategyVersion.strategy_id == strategy.strategy_id
        )
    )
    db.add(
        StrategyVersion(
            strategy_id=strategy.strategy_id,
            version=(latest or 0) + 1,
            change_note=change_note,
            strategy_json=strategy.strategy_json,
        )
    )
