import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: { environment: 'node', clearMocks: true },
  build: {
    rollupOptions: {
      input: {
        main: 'index.html', // existing team's homepage
        sanBong: 'san-bong.html',    // Huy's standalone frontend module
      },
    },
  },
});
