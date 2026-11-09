import '@fontsource/hanken-grotesk/latin-400.css';
import '@fontsource/hanken-grotesk/latin-500.css';
import '@fontsource/hanken-grotesk/latin-600.css';
import '@fontsource/hanken-grotesk/latin-700.css';
import '@fontsource/jetbrains-mono/latin-400.css';
import '@fontsource/jetbrains-mono/latin-500.css';
import '@fontsource/jetbrains-mono/latin-600.css';
import '@fontsource/jetbrains-mono/latin-700.css';
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { BACKEND_BASE_URL, fetchBrandingCached } from './lib/api'

// Fetch branding for dynamic favicon injection
fetchBrandingCached()
  .then(res => {
    if (res.data.logo_url) {
      const fullUrl = `${BACKEND_BASE_URL}${res.data.logo_url}`;
      let link = document.querySelector("link[rel~='icon']");
      if (!link) {
        link = document.createElement('link');
        link.rel = 'icon';
        document.head.appendChild(link);
      }
      link.href = fullUrl;
    }
    if (res.data.name) {
      document.title = res.data.name;
    }
  })
  .catch(err => {
    console.warn("Could not load branding for favicon", err);
  });

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
