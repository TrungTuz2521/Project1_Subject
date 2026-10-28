import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: { environment: 'node', clearMocks: true },
  build: {
    rollupOptions: {
      input: {
        main: 'index.html', // existing team's homepage
        huy: 'huy.html',    // Huy's standalone frontend module
      },
    },
  },
});
