import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/overpass/index.css';
import '@fontsource/overpass-mono/400.css';
import App from './App';
import './index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
