import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { HuyApp } from './features/huy/HuyApp';

createRoot(document.getElementById('root')!).render(<StrictMode><HuyApp/></StrictMode>);
