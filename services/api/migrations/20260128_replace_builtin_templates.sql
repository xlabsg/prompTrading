-- Replace legacy builtin templates with new template set (breakout/trend-following)

BEGIN;

-- Migrate references from legacy template ids
UPDATE strategy_subscriptions
SET template_id = 'tmpl-price-breakout'
WHERE template_id = 'tmpl-bollinger-breakout';

UPDATE template_performance_runs
SET template_id = 'tmpl-price-breakout'
WHERE template_id = 'tmpl-bollinger-breakout';

UPDATE template_signals
SET template_id = 'tmpl-price-breakout'
WHERE template_id = 'tmpl-bollinger-breakout';

UPDATE strategy_subscriptions
SET template_id = 'tmpl-trend-following'
WHERE template_id = 'tmpl-macd-trend';

UPDATE template_performance_runs
SET template_id = 'tmpl-trend-following'
WHERE template_id = 'tmpl-macd-trend';

UPDATE template_signals
SET template_id = 'tmpl-trend-following'
WHERE template_id = 'tmpl-macd-trend';

-- Remove legacy templates after migrating references
DELETE FROM strategy_templates
WHERE id IN ('tmpl-bollinger-breakout', 'tmpl-macd-trend');

-- Ensure the new builtin templates exist and are up to date (keep subscriber_count)
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
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    template_type = EXCLUDED.template_type,
    prompt = EXCLUDED.prompt,
    config_snapshot = EXCLUDED.config_snapshot,
    author = EXCLUDED.author,
    tags = EXCLUDED.tags,
    is_public = EXCLUDED.is_public,
    is_featured = EXCLUDED.is_featured,
    updated_at = NOW();

-- Recalculate subscriber_count from active subscriptions (safety)
UPDATE strategy_templates t
SET subscriber_count = (
    SELECT COUNT(*) FROM strategy_subscriptions s WHERE s.template_id = t.id AND s.status = 'active'
)
WHERE t.template_type = 'builtin';

COMMIT;
