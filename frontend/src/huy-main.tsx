
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { FieldApp } from './features/field-management/FieldApp';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <FieldApp />
  </StrictMode>
);
