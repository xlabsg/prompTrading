"""
Trading State

交易状态数据结构
"""
from dataclasses import dataclass, field
from typing import Dict, Optional, Any
from datetime import datetime
from ..core import Position, Order


@dataclass
class TradingState:
    """交易状态"""
    # 基本信息
    session_id: str
    symbol: str
    started_at: datetime

    # 仓位
    position: Optional[Position] = None

    # 待处理订单
    pending_orders: Dict[str, Order] = field(default_factory=dict)  # order_id -> Order

    # TP/SL 计划（用于挂单的 TP/SL）
    pending_tpsl: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # order_id -> {tp, sl}

    # 风控状态
    risk_state: Dict[str, Any] = field(default_factory=dict)

    # 止损管理器状态
    stop_loss_manager_state: Dict[str, Any] = field(default_factory=dict)

    # 仓位管理器状态
    position_manager_state: Dict[str, Any] = field(default_factory=dict)

    # 回撤追踪器状态
    drawdown_tracker_state: Dict[str, Any] = field(default_factory=dict)

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 最后更新时间
    last_updated: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            "session_id": self.session_id,
            "symbol": self.symbol,
            "started_at": self.started_at.isoformat(),
            "position": self._serialize_position() if self.position else None,
            "pending_orders": {
                oid: self._serialize_order(order)
                for oid, order in self.pending_orders.items()
            },
            "pending_tpsl": self.pending_tpsl,
            "risk_state": self.risk_state,
            "stop_loss_manager_state": self.stop_loss_manager_state,
            "position_manager_state": self.position_manager_state,
            "drawdown_tracker_state": self.drawdown_tracker_state,
            "metadata": self.metadata,
            "last_updated": self.last_updated.isoformat(),
        }

    def _serialize_position(self) -> Dict[str, Any]:
        """序列化仓位"""
        if not self.position:
            return None

        return {
            "symbol": self.position.symbol,
            "side": self.position.side.value,
            "size": float(self.position.size),
            "entry_price": float(self.position.entry_price),
            "current_price": float(self.position.current_price),
            "unrealized_pnl": float(self.position.unrealized_pnl),
            "realized_pnl": float(self.position.realized_pnl),
            "leverage": self.position.leverage,
            "margin": float(self.position.margin),
            "take_profit": float(self.position.take_profit) if self.position.take_profit else None,
            "stop_loss": float(self.position.stop_loss) if self.position.stop_loss else None,
            "status": self.position.status.value,
        }

    def _serialize_order(self, order: Order) -> Dict[str, Any]:
        """序列化订单"""
        return {
            "order_id": order.order_id,
            "exchange_order_id": order.exchange_order_id,
            "client_order_id": order.client_order_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "position_side": order.position_side.value,
            "status": order.status.value,
            "size": float(order.size),
            "filled_size": float(order.filled_size),
            "price": float(order.price) if order.price else None,
            "avg_fill_price": float(order.avg_fill_price) if order.avg_fill_price else None,
            "created_at": order.created_at.isoformat(),
            "updated_at": order.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TradingState":
        """从字典恢复（反序列化）"""
        # 注意：完整的反序列化需要重新创建对象实例
        # 这里简化实现，实际使用时建议从数据库恢复
        state = cls(
            session_id=data["session_id"],
            symbol=data["symbol"],
            started_at=datetime.fromisoformat(data["started_at"]),
        )
        state.pending_tpsl = data.get("pending_tpsl", {})
        state.risk_state = data.get("risk_state", {})
        state.stop_loss_manager_state = data.get("stop_loss_manager_state", {})
        state.position_manager_state = data.get("position_manager_state", {})
        state.drawdown_tracker_state = data.get("drawdown_tracker_state", {})
        state.metadata = data.get("metadata", {})
        state.last_updated = datetime.fromisoformat(data["last_updated"])

        return state
