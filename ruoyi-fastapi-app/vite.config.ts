import uni from "@dcloudio/vite-plugin-uni";
import { defineConfig } from "vite";
import { UnifiedViteWeappTailwindcssPlugin } from "weapp-tailwindcss/vite";
import { WeappTailwindcssDisabled } from "./platform";
import postcssPlugins from "./postcss.config";

function patchNodeForgeMiniProgramRuntime() {
  return {
    name: "patch-node-forge-mini-program-runtime",
    enforce: "pre",
    transform(code: string, id: string) {
      if (id.includes("node-forge/lib/util.js")) {
        return {
          code: code.replace(
            /return typeof self === 'undefined' \? window : self;/,
            "return typeof globalThis !== 'undefined' ? globalThis : (typeof self === 'undefined' ? (typeof window === 'undefined' ? {} : window) : self);",
          ),
          map: null,
        };
      }

      if (id.includes("node-forge/lib/random.js")) {
        return {
          code: code.replace(
            /var _crypto = globalScope\.crypto \|\| globalScope\.msCrypto;/,
            "var _crypto = (globalScope && (globalScope.crypto || globalScope.msCrypto)) || null;",
          ),
          map: null,
        };
      }

      return null;
    },
  };
}

// https://vitejs.dev/config/
export default defineConfig(async () => {
  // 新版本的 unplugin-auto-import 改成了只有 esm 格式的产物，而 uni-app 目前必须 cjs 格式
  // 所以需要改成动态 import 的写法来进行引入
  // 详见 https://github.com/sonofmagic/uni-app-vite-vue3-tailwind-vscode-template/issues/29
  const { default: AutoImport } = await import("unplugin-auto-import/vite");
  return {
    // uvtw 一定要放在 uni 后面
    plugins: [
      uni(),
      patchNodeForgeMiniProgramRuntime(),
      UnifiedViteWeappTailwindcssPlugin({
        rem2rpx: true,
        disabled: WeappTailwindcssDisabled,
      }),
      AutoImport({
        imports: ["vue", "uni-app", "pinia"],
        dts: "./src/auto-imports.d.ts",
      }),
    ],
    // 内联 postcss 注册 tailwindcss
    css: {
      postcss: {
        plugins: postcssPlugins,
      },
      // https://vitejs.dev/config/shared-options.html#css-preprocessoroptions
      preprocessorOptions: {
        scss: {
          silenceDeprecations: ["legacy-js-api"],
        },
      },
    },
  };
});
