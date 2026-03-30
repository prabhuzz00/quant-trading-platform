import axios from 'axios';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';
const WS_BASE = process.env.REACT_APP_WS_URL || 'ws://localhost:8000/ws';

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 10000,
});

api.interceptors.response.use(
  response => response.data,
  error => {
    const message = error.response?.data?.detail || error.message || 'API Error';
    return Promise.reject(new Error(message));
  }
);

export const createDashboardWebSocket = (onMessage, onError) => {
  const ws = new WebSocket(`${WS_BASE}/dashboard`);
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch (e) {
      console.error('WS parse error:', e);
    }
  };
  ws.onerror = onError;
  ws.onclose = () => setTimeout(() => createDashboardWebSocket(onMessage, onError), 3000);
  return ws;
};

export const tradesAPI = {
  getOpen: () => api.get('/trades/open'),
  getClosed: (params) => api.get('/trades/closed', { params }),
  getDetail: (id) => api.get(`/trades/${id}`),
  squareOff: (id) => api.post(`/trades/squareoff/${id}`),
  squareOffAll: () => api.post('/trades/squareoff-all'),
};

export const riskAPI = {
  getConfig: () => api.get('/risk/config'),
  updateConfig: (data) => api.put('/risk/config', data),
  getDashboard: () => api.get('/risk/dashboard'),
  activateKillSwitch: (reason) => api.post('/risk/kill-switch/activate', { reason }),
  deactivateKillSwitch: () => api.post('/risk/kill-switch/deactivate'),
};

export const strategiesAPI = {
  getAll: () => api.get('/strategies'),
  toggle: (name, enabled) => api.put(`/strategies/${name}/toggle`, { enabled }),
  getPerformance: (name) => api.get(`/strategies/${name}/performance`),
};

export const positionsAPI = {
  getAll: () => api.get('/positions'),
  getBalance: () => api.get('/positions/balance'),
  getOrders: () => api.get('/positions/orders'),
  getTrades: () => api.get('/positions/trades'),
};

export const manualAPI = {
  getExpiries: (symbol = 'NIFTY', exchangeSegment = 'NSEFO', series = 'OPTIDX') =>
    api.get('/manual/expiries', { params: { symbol, exchange_segment: exchangeSegment, series } }),

  getOptionChain: (symbol, expiry, { numStrikes = 10, exchangeSegment = 'NSEFO' } = {}) =>
    api.get('/manual/option-chain', {
      params: {
        symbol,
        expiry,
        num_strikes: numStrikes,
        exchange_segment: exchangeSegment,
      },
    }),

  placeOrder: (payload) => api.post('/manual/order', payload),
};
