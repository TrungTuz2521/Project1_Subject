import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { TeamsPage } from './features/matchmaking/TeamsPage';
import './styles/app.css';

createRoot(document.getElementById('root')!).render(<StrictMode><TeamsPage /></StrictMode>);
