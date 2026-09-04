"""
Exchange Adapter Base Class

交易所适配器抽象基类
"""
import logging
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import List, Dict, Any, Optional
from ..core import (
    OrderSpec, OrderType, OrderSide, PositionSide, TradingMode
)

logger = logging.getLogger(__name__)


class ExchangeAdapter(ABC):
    """交易所适配器抽象基类"""

    @abstractmethod
    def place_order(self, order_spec: OrderSpec) -> Dict[str, Any]:
        """
        下单

        Args:
            order_spec: 订单规格

        Returns:
            交易所返回的订单信息
        """
        pass

    @abstractmethod
    def cancel_order(self, symbol: str, order_id: str) -> bool:
        """
        取消订单

        Args:
            symbol: 交易对
            order_id: 订单 ID（交易所 ID 或客户端 ID）

        Returns:
            是否成功
        """
        pass

    @abstractmethod
    def get_order(self, symbol: str, order_id: str) -> Optional[Dict[str, Any]]:
        """
        获取订单信息

        Args:
            symbol: 交易对
            order_id: 订单 ID

        Returns:
            订单信息
        """
        pass

    @abstractmethod
    def get_open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """
        获取未完成订单

        Args:
            symbol: 交易对

        Returns:
            订单列表
        """
        pass

    @abstractmethod
    def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取仓位信息

        Args:
            symbol: 交易对（如果为 None 则获取所有仓位）

        Returns:
            仓位列表
        """
        pass

    @abstractmethod
    def get_balance(self) -> Dict[str, Any]:
        """
        获取账户余额

        Returns:
            余额信息
        """
        pass

    @abstractmethod
    def set_leverage(self, symbol: str, leverage: int, margin_mode: TradingMode) -> bool:
        """
        设置杠杆

        Args:
            symbol: 交易对
            leverage: 杠杆倍数
            margin_mode: 保证金模式

        Returns:
            是否成功
        """
        pass

    @abstractmethod
    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        获取行情信息

        Args:
            symbol: 交易对

        Returns:
            行情信息
        """
        pass

    @abstractmethod
    def normalize_symbol(self, symbol: str) -> str:
        """
        规范化交易对符号

        Args:
            symbol: 原始交易对符号

        Returns:
            规范化后的交易对符号
        """
        pass

    @abstractmethod
    def normalize_price(self, symbol: str, price: Decimal, direction: str) -> Decimal:
        """
        规范化价格（符合 tick size）

        Args:
            symbol: 交易对
            price: 原始价格
            direction: 方向（"up" 向上取整，"down" 向下取整）

        Returns:
            规范化后的价格
        """
        pass

    @abstractmethod
    def normalize_size(self, symbol: str, size: Decimal) -> Decimal:
        """
        规范化订单大小（符合 lot size）

        Args:
            symbol: 交易对
            size: 原始大小

        Returns:
            规范化后的大小
        """
        pass

    @abstractmethod
    def translate_order_type(self, order_type: OrderType) -> str:
        """
        将通用订单类型转换为交易所特定的类型

        Args:
            order_type: 通用订单类型

        Returns:
            交易所特定的订单类型
        """
        pass

    @abstractmethod
    def translate_order_side(self, side: OrderSide, position_side: PositionSide) -> Dict[str, str]:
        """
        将通用订单方向转换为交易所特定的参数

        Args:
            side: 订单方向
            position_side: 仓位方向

        Returns:
            交易所特定的参数（例如 {"side": "buy", "posSide": "long"}）
        """
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """
        测试连接

        Returns:
            连接是否正常
        """
        pass
