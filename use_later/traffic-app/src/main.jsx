import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { DebugProvider } from './contexts/DebugContext';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <DebugProvider>
      <App />
    </DebugProvider>
  </React.StrictMode>
);
