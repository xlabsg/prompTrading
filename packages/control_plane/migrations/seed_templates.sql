-- Seed data for built-in strategy templates
-- Run this after add_strategy_templates.sql

-- Insert sample built-in templates (using dollar-quoting for code blocks)
INSERT INTO strategy_templates (id, name, description, template_type, prompt, config_snapshot, author, tags, is_public, is_featured, subscriber_count)
VALUES
(
    'tmpl-moving-average-crossover',
    'Moving Average Crossover',
    'A classic momentum strategy that generates buy and sell signals based on the crossover of short-term and long-term moving averages. Best for trending markets.',
    'builtin',
    $code$# Moving Average Crossover Strategy
# Generates signals when short MA crosses above/below long MA

class MovingAverageCrossover(LiveStrategy):
    def initialize(self):
        self.short_window = 20
        self.long_window = 50
        self.symbols = ["BTCUSDT"]
        self.intervals = ["1h"]

    def on_bar(self, bar: Bar):
        # Calculate moving averages
        short_ma = self.ma(self.short_window)
        long_ma = self.ma(self.long_window)

        # Get current position
        pos = self.get_position()

        # Golden Cross (buy signal)
        if short_ma > long_ma and pos.size == 0:
            self.market_order(bar.symbol, size=0.1, side=OrderSide.BUY)

        # Death Cross (sell signal)
        elif short_ma < long_ma and pos.size > 0:
            self.market_order(bar.symbol, size=pos.size, side=OrderSide.SELL)
$code$,
    '{"exchange": "okx", "symbols": ["BTCUSDT"], "intervals": ["1h"], "default_max_position_pct": 10, "default_stop_loss_pct": 5}',
    'System',
    '["momentum", "trend-following", "ma-crossover"]',
    true,
    true,
    0
),
(
    'tmpl-rsi-oversold',
    'RSI Mean Reversion',
    'A mean reversion strategy that buys when RSI indicates oversold conditions and sells when overbought. Effective in ranging markets.',
    'builtin',
    $code$# RSI Mean Reversion Strategy
# Buys at oversold levels, sells at overbought levels

class RSIMeanReversion(LiveStrategy):
    def initialize(self):
        self.rsi_period = 14
        self.oversold = 30
        self.overbought = 70
        self.symbols = ["BTCUSDT"]
        self.intervals = ["1h"]

    def on_bar(self, bar: Bar):
        rsi = self.rsi(self.rsi_period)
        pos = self.get_position()

        # Buy when oversold
        if rsi < self.oversold and pos.size == 0:
            self.market_order(bar.symbol, size=0.1, side=OrderSide.BUY)

        # Sell when overbought
        elif rsi > self.overbought and pos.size > 0:
            self.market_order(bar.symbol, size=pos.size, side=OrderSide.SELL)
$code$,
    '{"exchange": "okx", "symbols": ["BTCUSDT"], "intervals": ["1h"], "default_max_position_pct": 10, "default_stop_loss_pct": 5}',
    'System',
    '["mean-reversion", "rsi", "oscillator"]',
    true,
    true,
    0
),
(
    'tmpl-price-breakout',
    'Price Breakout',
    'A breakout strategy that enters when price exceeds recent highs with volume confirmation and uses a trailing stop for exits.',
    'builtin',
    $code$# Price Breakout Strategy
# Enters on 20-day high breakout with volume confirmation

class PriceBreakout(LiveStrategy):
    def initialize(self):
        self.lookback = 20
        self.volume_mult = 2
        self.symbols = ["BTCUSDT"]
        self.intervals = ["4h"]

    def on_bar(self, bar: Bar):
        high_20 = self.highest(self.lookback)
        avg_vol = self.sma_volume(self.lookback)
        pos = self.get_position()

        if bar.close > high_20 and bar.volume > avg_vol * self.volume_mult and pos.size == 0:
            self.market_order(bar.symbol, size=0.1, side=OrderSide.BUY)

        elif pos.size > 0 and self.trailing_stop_hit(0.03):
            self.market_order(bar.symbol, size=pos.size, side=OrderSide.SELL)
$code$,
    '{"exchange": "okx", "symbols": ["BTCUSDT"], "intervals": ["4h"], "default_max_position_pct": 10, "default_stop_loss_pct": 5}',
    'System',
    '["breakout", "momentum", "trend"]',
    true,
    false,
    0
),
(
    'tmpl-trend-following',
    'Trend Following',
    'A trend-following strategy that stays long while price remains above long-term averages and exits on trend breaks.',
    'builtin',
    $code$# Trend Following Strategy
# Uses moving averages and ADX for trend confirmation

class TrendFollowing(LiveStrategy):
    def initialize(self):
        self.fast = 50
        self.slow = 100
        self.adx_period = 14
        self.symbols = ["BTCUSDT"]
        self.intervals = ["4h"]

    def on_bar(self, bar: Bar):
        fast_ma = self.ema(self.fast)
        slow_ma = self.ema(self.slow)
        adx = self.adx(self.adx_period)
        pos = self.get_position()

        if bar.close > slow_ma and fast_ma > slow_ma and adx > 20 and pos.size == 0:
            self.market_order(bar.symbol, size=0.1, side=OrderSide.BUY)

        elif bar.close < fast_ma and pos.size > 0:
            self.market_order(bar.symbol, size=pos.size, side=OrderSide.SELL)
$code$,
    '{"exchange": "okx", "symbols": ["BTCUSDT"], "intervals": ["4h"], "default_max_position_pct": 10, "default_stop_loss_pct": 5}',
    'System',
    '["trend", "momentum", "moving-average"]',
    true,
    true,
    0
),
(
    'tmpl-grid-trading',
    'Grid Trading',
    'A range-bound trading strategy that places buy orders at predefined levels below price and sell orders above, profiting from price oscillations.',
    'builtin',
    $code$# Grid Trading Strategy
# Places orders at regular intervals within a price range

class GridTrading(LiveStrategy):
    def initialize(self):
        self.grid_levels = 5
        self.grid_size_pct = 0.02  # 2% between levels
        self.symbols = ["BTCUSDT"]
        self.intervals = ["15m"]

    def on_bar(self, bar: Bar):
        # Calculate grid levels
        current_price = bar.close
        grid_interval = current_price * self.grid_size_pct

        # Check and place grid orders
        for i in range(self.grid_levels):
            level_price = current_price - (i + 1) * grid_interval
            self.limit_order(bar.symbol, size=0.01, side=OrderSide.BUY, price=level_price)

            sell_level = current_price + (i + 1) * grid_interval
            self.limit_order(bar.symbol, size=0.01, side=OrderSide.SELL, price=sell_level)
$code$,
    '{"exchange": "okx", "symbols": ["BTCUSDT"], "intervals": ["15m"], "default_max_position_pct": 20, "default_stop_loss_pct": 10}',
    'System',
    '["grid", "range-bound", "scalping"]',
    true,
    false,
    0
)
ON CONFLICT (id) DO NOTHING;
