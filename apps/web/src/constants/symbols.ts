// OKX USDT-SWAP top 50 trading pairs by volume
export const PREDEFINED_SYMBOLS = {
    // Top主流币
    top: [
        { symbol: 'BTC-USDT-SWAP', name: 'BTC', icon: '₿' },
        { symbol: 'ETH-USDT-SWAP', name: 'ETH', icon: 'Ξ' },
        { symbol: 'SOL-USDT-SWAP', name: 'SOL', icon: '◎' },
        { symbol: 'BNB-USDT-SWAP', name: 'BNB' },
        { symbol: 'XRP-USDT-SWAP', name: 'XRP' },
        { symbol: 'DOGE-USDT-SWAP', name: 'DOGE' },
        { symbol: 'ADA-USDT-SWAP', name: 'ADA' },
        { symbol: 'AVAX-USDT-SWAP', name: 'AVAX' },
        { symbol: 'TRX-USDT-SWAP', name: 'TRX' },
        { symbol: 'DOT-USDT-SWAP', name: 'DOT' },
    ],
    // Layer1/公链
    l1: [
        { symbol: 'SOL-USDT-SWAP', name: 'SOL' },
        { symbol: 'ADA-USDT-SWAP', name: 'ADA' },
        { symbol: 'AVAX-USDT-SWAP', name: 'AVAX' },
        { symbol: 'DOT-USDT-SWAP', name: 'DOT' },
        { symbol: 'NEAR-USDT-SWAP', name: 'NEAR' },
        { symbol: 'ATOM-USDT-SWAP', name: 'ATOM' },
        { symbol: 'APT-USDT-SWAP', name: 'APT' },
        { symbol: 'SUI-USDT-SWAP', name: 'SUI' },
        { symbol: 'SEI-USDT-SWAP', name: 'SEI' },
        { symbol: 'TIA-USDT-SWAP', name: 'TIA' },
    ],
    // Layer2/扩容
    l2: [
        { symbol: 'MATIC-USDT-SWAP', name: 'POL' },
        { symbol: 'ARB-USDT-SWAP', name: 'ARB' },
        { symbol: 'OP-USDT-SWAP', name: 'OP' },
        { symbol: 'IMX-USDT-SWAP', name: 'IMX' },
        { symbol: 'INJ-USDT-SWAP', name: 'INJ' },
    ],
    // DeFi
    defi: [
        { symbol: 'UNI-USDT-SWAP', name: 'UNI' },
        { symbol: 'AAVE-USDT-SWAP', name: 'AAVE' },
        { symbol: 'LINK-USDT-SWAP', name: 'LINK' },
        { symbol: 'MKR-USDT-SWAP', name: 'MKR' },
        { symbol: 'COMP-USDT-SWAP', name: 'COMP' },
        { symbol: 'CRV-USDT-SWAP', name: 'CRV' },
        { symbol: 'GMX-USDT-SWAP', name: 'GMX' },
        { symbol: 'GRT-USDT-SWAP', name: 'GRT' },
    ],
    // AI/元宇宙/GameFi
    ai: [
        { symbol: 'FET-USDT-SWAP', name: 'FET' },
        { symbol: 'RNDR-USDT-SWAP', name: 'RNDR' },
        { symbol: 'WLD-USDT-SWAP', name: 'WLD' },
        { symbol: 'AR-USDT-SWAP', name: 'AR' },
        { symbol: 'AXS-USDT-SWAP', name: 'AXS' },
        { symbol: 'GALA-USDT-SWAP', name: 'GALA' },
        { symbol: 'SAND-USDT-SWAP', name: 'SAND' },
        { symbol: 'MANA-USDT-SWAP', name: 'MANA' },
        { symbol: 'ENJ-USDT-SWAP', name: 'ENJ' },
        { symbol: 'GMT-USDT-SWAP', name: 'GMT' },
    ],
    // Meme
    meme: [
        { symbol: 'PEPE-USDT-SWAP', name: 'PEPE' },
        { symbol: 'SHIB-USDT-SWAP', name: 'SHIB' },
        { symbol: 'WIF-USDT-SWAP', name: 'WIF' },
        { symbol: 'BONK-USDT-SWAP', name: 'BONK' },
        { symbol: 'FLOKI-USDT-SWAP', name: 'FLOKI' },
        { symbol: 'NEIRO-USDT-SWAP', name: 'NEIRO' },
        { symbol: 'MOG-USDT-SWAP', name: 'MOG' },
        { symbol: 'SATS-USDT-SWAP', name: 'SATS' },
    ],
    // 其他主流
    others: [
        { symbol: 'LTC-USDT-SWAP', name: 'LTC' },
        { symbol: 'BCH-USDT-SWAP', name: 'BCH' },
        { symbol: 'XLM-USDT-SWAP', name: 'XLM' },
        { symbol: 'ALGO-USDT-SWAP', name: 'ALGO' },
        { symbol: 'VET-USDT-SWAP', name: 'VET' },
        { symbol: 'ICP-USDT-SWAP', name: 'ICP' },
        { symbol: 'FIL-USDT-SWAP', name: 'FIL' },
        { symbol: 'ZRO-USDT-SWAP', name: 'ZRO' },
        { symbol: 'ORDI-USDT-SWAP', name: 'ORDI' },
        { symbol: 'AIXBT-USDT-SWAP', name: 'AIXBT' },
        { symbol: 'POPCAT-USDT-SWAP', name: 'POPCAT' },
        { symbol: 'CHZ-USDT-SWAP', name: 'CHZ' },
    ],
} as const;

export type SymbolCategory = keyof typeof PREDEFINED_SYMBOLS;

// 获取所有币种（扁平数组）
export const ALL_SYMBOLS = Object.values(PREDEFINED_SYMBOLS).flat();
