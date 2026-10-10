const path = require("path");
const { WeappTailwindcssDisabled } = require("./platform");
const { UnifiedWebpackPluginV5 } = require("weapp-tailwindcss/webpack");

/**
 * @type {import('@vue/cli-service').ProjectOptions}
 */
const config = {
  //....
  configureWebpack: {
    resolve: {
      alias: {
        "node-forge/lib/util": path.resolve(
          __dirname,
          "src/vendor/node-forge/lib/util.js",
        ),
        "node-forge/lib/random": path.resolve(
          __dirname,
          "src/vendor/node-forge/lib/random.js",
        ),
        "node-forge/lib/prng": path.resolve(
          __dirname,
          "src/vendor/node-forge/lib/prng.js",
        ),
        "node-forge/lib/rsa": path.resolve(
          __dirname,
          "src/vendor/node-forge/lib/rsa.js",
        ),
      },
    },
    plugins: [
      new (require("webpack").NormalModuleReplacementPlugin)(
        /node-forge[\\/]lib[\\/]util\.js$/,
        path.resolve(__dirname, "src/vendor/node-forge/lib/util.js"),
      ),
      new (require("webpack").NormalModuleReplacementPlugin)(
        /node-forge[\\/]lib[\\/]random\.js$/,
        path.resolve(__dirname, "src/vendor/node-forge/lib/random.js"),
      ),
      new (require("webpack").NormalModuleReplacementPlugin)(
        /node-forge[\\/]lib[\\/]prng\.js$/,
        path.resolve(__dirname, "src/vendor/node-forge/lib/prng.js"),
      ),
      new (require("webpack").NormalModuleReplacementPlugin)(
        /node-forge[\\/]lib[\\/]rsa\.js$/,
        path.resolve(__dirname, "src/vendor/node-forge/lib/rsa.js"),
      ),
      new UnifiedWebpackPluginV5({
        rem2rpx: true,
        disabled: WeappTailwindcssDisabled,
      }),
    ],
  },
  chainWebpack: (config) => {
    // 去除ts类型检测，因为uni-app ts type 支持其实不咋好
    config.plugins.delete("fork-ts-checker");
  },
  css: {
    loaderOptions: {
      scss: {
        sassOptions: {
          silenceDeprecations: ["import", "legacy-js-api"],
        },
      },
    },
  },
  transpileDependencies: ["uview-ui", /@formatjs/],
  //....
};

module.exports = config;
