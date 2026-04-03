const path = require("path");

module.exports = {
  entry: {
    background: "./src/background/background.ts",
    chatgpt_content: "./src/content/chatgpt_content.ts",
    claude_content: "./src/content/claude_content.ts",
    popup: "./src/popup/popup.ts",
  },
  output: {
    path: path.resolve(__dirname, "dist"),
    filename: "[name].js",
  },
  resolve: {
    extensions: [".ts", ".js"],
  },
  module: {
    rules: [
      {
        test: /\.ts$/,
        use: "ts-loader",
        exclude: /node_modules/,
      },
    ],
  },
};
