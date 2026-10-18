import { defineConfig, loadEnv, transformWithEsbuild } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** CRA-compatible env keys (vercel.json + local .env*). Keep names so dashboard vars stay REACT_APP_*. */
const REACT_APP_KEYS = [
  "REACT_APP_BACKEND_URL",
  "REACT_APP_HELM_ORIGIN",
  "REACT_APP_CLERK_PUBLISHABLE_KEY",
  "REACT_APP_CLERK_SIGN_IN_URL",
  "REACT_APP_CLERK_SIGN_UP_URL",
  "REACT_APP_CLERK_SIGN_IN_FALLBACK_REDIRECT_URL",
  "REACT_APP_CLERK_SIGN_UP_FALLBACK_REDIRECT_URL",
  "REACT_APP_CLERK_SIGN_IN_FORCE_REDIRECT_URL",
  "REACT_APP_CLERK_SIGN_UP_FORCE_REDIRECT_URL",
  "REACT_APP_GOOGLE_SITE_VERIFICATION",
];

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, ["REACT_APP_", "VITE_"]);
  const define = {};
  for (const key of REACT_APP_KEYS) {
    define[`process.env.${key}`] = JSON.stringify(env[key] ?? process.env[key] ?? "");
  }

  const backend =
    env.REACT_APP_BACKEND_URL ||
    process.env.REACT_APP_BACKEND_URL ||
    "http://localhost:8001";

  return {
    plugins: [
      // Allow residual CRA-style JSX inside .js (most app files are already .jsx).
      {
        name: "treat-js-files-as-jsx",
        async transform(code, id) {
          if (!id.includes("/src/") || !id.endsWith(".js")) return null;
          return transformWithEsbuild(code, id, { loader: "jsx", jsx: "automatic" });
        },
      },
      react(),
    ],
    envPrefix: ["REACT_APP_", "VITE_"],
    define,
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "src"),
      },
    },
    optimizeDeps: {
      esbuildOptions: {
        loader: { ".js": "jsx" },
      },
    },
    server: {
      port: 3000,
      proxy: {
        "/api": {
          target: backend.replace(/\/$/, ""),
          changeOrigin: true,
          secure: false,
        },
      },
    },
    build: {
      outDir: "build",
      emptyOutDir: true,
      sourcemap: false,
      // Main graph is ~650kB (same ballpark as CRA). Avoid a noisy Vite warning.
      chunkSizeWarningLimit: 700,
      // Keep hashed assets under static/js + static/css (CRA layout) for verify-auth-build
      // and any ops scripts that expect that tree.
      rollupOptions: {
        output: {
          entryFileNames: "static/js/[name].[hash].js",
          chunkFileNames: "static/js/[name].[hash].js",
          assetFileNames: (info) => {
            const name = info.name || "";
            if (name.endsWith(".css")) return "static/css/[name].[hash][extname]";
            return "static/media/[name].[hash][extname]";
          },
          manualChunks(id) {
            // React core in its own chunk, otherwise Rollup folds it into the
            // recharts chunk and every page downloads the charting library.
            if (id.includes("commonjsHelpers")) return "react-vendor";
            if (/node_modules\/(react|react-dom|scheduler|react-is|use-sync-external-store|clsx|tailwind-merge)\//.test(id)) {
              return "react-vendor";
            }
            // Keep recharts out of the initial/main graph (RevenueBars is lazy).
            if (id.includes("node_modules/recharts") || id.includes("node_modules/victory-vendor")) {
              return "recharts";
            }
          },
        },
      },
    },
  };
});
