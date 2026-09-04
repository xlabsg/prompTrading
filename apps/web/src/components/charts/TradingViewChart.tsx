import React, { useEffect, useRef, useState } from 'react';
import { createChart, createSeriesMarkers, ColorType, IChartApi, Time, AreaSeries, BaselineSeries, CandlestickSeries, LineSeries } from 'lightweight-charts';

interface ChartData {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

interface SignalEvent {
  time: number;
  type: 'buy' | 'sell';
  price: number;
  text?: string;
}

interface IndicatorData {
  name: string;
  data: { time: number; value: number }[];
  color?: string;
  isOverlay?: boolean;
}

interface TradingViewChartProps {
  data: ChartData[] | { time: number; value: number }[];
  chartType?: 'candlestick' | 'area' | 'line' | 'baseline';
  signals?: SignalEvent[];
  indicators?: IndicatorData[];
  height?: number;
  fitContent?: boolean;
  baselineValue?: number;
  colors?: {
    up?: string;
    down?: string;
    line?: string;
    areaTop?: string;
    areaBottom?: string;
  };
  pricePrecision?: number;
}

const EMPTY_SIGNALS: SignalEvent[] = [];
const EMPTY_INDICATORS: IndicatorData[] = [];
const EMPTY_COLORS: NonNullable<TradingViewChartProps["colors"]> = {};

const TradingViewChart: React.FC<TradingViewChartProps> = ({
  data,
  chartType = 'candlestick',
  signals,
  indicators,
  height = 500,
  fitContent = true,
  baselineValue,
  colors,
  pricePrecision,
}) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const resolvedSignals = signals ?? EMPTY_SIGNALS;
  const resolvedIndicators = indicators ?? EMPTY_INDICATORS;
  const resolvedColors = colors ?? EMPTY_COLORS;

  const toUnixSeconds = (rawTime: number): Time => {
    const t = Number(rawTime);
    if (!Number.isFinite(t)) return 0 as Time;
    if (t >= 1_000_000_000_000) return Math.floor(t / 1000) as Time; // ms -> s
    if (t >= 1_000_000_000) return Math.floor(t) as Time; // already seconds
    return Math.floor(t) as Time; // legacy/index-like values
  };

  // Theme handling (detect dark mode)
  const isDark = document.documentElement.classList.contains("dark");
  const [theme, setTheme] = useState(isDark ? 'dark' : 'light');

  // Monitor theme changes
  useEffect(() => {
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.attributeName === 'class') {
          const newIsDark = document.documentElement.classList.contains('dark');
          setTheme(newIsDark ? 'dark' : 'light');
        }
      });
    });
    observer.observe(document.documentElement, { attributes: true });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    // Destroy previous chart
    if (chartRef.current) {
      chartRef.current.remove();
    }

    // Chart Options
    const chartOptions = {
      layout: {
        background: { type: ColorType.Solid, color: theme === 'dark' ? '#1c1c1c' : '#ffffff' },
        textColor: theme === 'dark' ? '#d1d4dc' : '#333',
      },
      grid: {
        vertLines: { color: theme === 'dark' ? '#2B2B43' : '#F0F3FA' },
        horzLines: { color: theme === 'dark' ? '#2B2B43' : '#F0F3FA' },
      },
      width: chartContainerRef.current.clientWidth,
      height: height,
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        minimumWidth: 72,
      },
    };

    const chart = createChart(chartContainerRef.current, chartOptions);
    chartRef.current = chart;

    let mainSeries;

    // Sort and Format Data
    const sortedData = [...data].sort((a, b) => a.time - b.time).map(item => ({
      ...item,
      time: toUnixSeconds(item.time),
    }));
    const seriesPriceFormat = Number.isFinite(Number(pricePrecision))
      ? { type: 'price' as const, precision: Number(pricePrecision), minMove: Math.pow(10, -Number(pricePrecision)) }
      : undefined;

    if (chartType === 'candlestick') {
      mainSeries = chart.addSeries(CandlestickSeries, {
        upColor: resolvedColors.up || '#26a69a',
        downColor: resolvedColors.down || '#ef5350',
        borderVisible: false,
        wickUpColor: resolvedColors.up || '#26a69a',
        wickDownColor: resolvedColors.down || '#ef5350',
        ...(seriesPriceFormat ? { priceFormat: seriesPriceFormat } : {}),
      });
      mainSeries.setData(sortedData as any);
    } else if (chartType === 'area') {
      mainSeries = chart.addSeries(AreaSeries, {
        lineColor: resolvedColors.line || '#2962FF',
        topColor: resolvedColors.areaTop || 'rgba(41, 98, 255, 0.3)',
        bottomColor: resolvedColors.areaBottom || 'rgba(41, 98, 255, 0)',
        ...(seriesPriceFormat ? { priceFormat: seriesPriceFormat } : {}),
      });
      mainSeries.setData(sortedData as any);
    } else if (chartType === 'baseline') {
      const firstPoint = (sortedData[0] as { value?: number } | undefined)?.value;
      const resolvedBaseline = Number.isFinite(Number(baselineValue))
        ? Number(baselineValue)
        : Number(firstPoint ?? 0);
      mainSeries = chart.addSeries(BaselineSeries, {
        baseValue: { type: 'price', price: resolvedBaseline },
        topLineColor: resolvedColors.up || '#16a34a',
        topFillColor1: 'rgba(22, 163, 74, 0.30)',
        topFillColor2: 'rgba(22, 163, 74, 0.02)',
        bottomLineColor: resolvedColors.down || '#dc2626',
        bottomFillColor1: 'rgba(220, 38, 38, 0.28)',
        bottomFillColor2: 'rgba(220, 38, 38, 0.03)',
        ...(seriesPriceFormat ? { priceFormat: seriesPriceFormat } : {}),
      });
      mainSeries.setData(sortedData as any);
    } else {
      mainSeries = chart.addSeries(LineSeries, {
        color: resolvedColors.line || '#2962FF',
        lineWidth: 2,
        ...(seriesPriceFormat ? { priceFormat: seriesPriceFormat } : {}),
      });
      mainSeries.setData(sortedData as any);
    }

    // Markers (Signals) - only if candlestick for now, or generally if requested
    if (resolvedSignals.length > 0 && chartType === 'candlestick') {
      const markers = resolvedSignals.map(sig => ({
        time: toUnixSeconds(sig.time),
        position: sig.type === 'buy' ? 'belowBar' : 'aboveBar',
        color: sig.type === 'buy' ? '#2196F3' : '#E91E63',
        shape: sig.type === 'buy' ? 'arrowUp' : 'arrowDown',
        text: (sig.text || sig.type).toUpperCase(),
        size: 1,
      }));
      // lightweight-charts v5 uses a markers plugin API instead of series.setMarkers.
      try {
        const markersPlugin = createSeriesMarkers(mainSeries as any, markers as any);
        markersPlugin.setMarkers(markers as any);
      } catch {
        // Backward compatibility with older versions where setMarkers exists on series.
        const maybeSeries = mainSeries as unknown as { setMarkers?: (m: unknown) => void };
        maybeSeries.setMarkers?.(markers);
      }
    }

    // Indicators
    resolvedIndicators.forEach((ind, index) => {
      const color = ind.color || (index % 2 === 0 ? '#2962FF' : '#FF6D00');
      const lineSeries = chart.addSeries(LineSeries, {
        color: color,
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      const lineData = ind.data
        .sort((a, b) => a.time - b.time)
        .map(d => ({ time: toUnixSeconds(d.time), value: d.value }));
      lineSeries.setData(lineData);
    });

    let fitRaf: number | null = null;
    if (fitContent && sortedData.length > 0) {
      fitRaf = window.requestAnimationFrame(() => {
        try {
          chart.timeScale().fitContent();
        } catch {
          // no-op
        }
      });
    }

    // Handle Resize
    const handleResize = () => {
      if (chartRef.current && chartContainerRef.current) {
        chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
        if (fitContent) {
          chartRef.current.timeScale().fitContent();
        }
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      if (fitRaf !== null) {
        window.cancelAnimationFrame(fitRaf);
      }
      window.removeEventListener('resize', handleResize);
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [data, resolvedSignals, resolvedIndicators, height, theme, chartType, resolvedColors, fitContent, baselineValue, pricePrecision]);

  return <div ref={chartContainerRef} className="w-full relative" />;
};

export default TradingViewChart;
