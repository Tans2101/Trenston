/** Standalone Jest (post-CRA). Mirrors the former craco Jest alias + CRA asset mocks. */
module.exports = {
  testEnvironment: "jsdom",
  roots: ["<rootDir>/src"],
  testMatch: ["**/__tests__/**/*.[jt]s?(x)", "**/?(*.)+(spec|test).[jt]s?(x)"],
  moduleNameMapper: {
    // Alias + asset stubs: @/…svg must win over the generic @/ mapper.
    "^@/(.*)\\.(svg|png|jpg|jpeg|gif|webp|woff2?)$": "<rootDir>/src/test/fileMock.js",
    "^@/(.*)$": "<rootDir>/src/$1",
    "\\.(css|less|scss|sass)$": "identity-obj-proxy",
    "\\.(svg|png|jpg|jpeg|gif|webp|woff2?)$": "<rootDir>/src/test/fileMock.js",
  },
  transform: {
    "^.+\\.(js|jsx)$": "babel-jest",
  },
  transformIgnorePatterns: [
    "/node_modules/",
  ],
  moduleFileExtensions: ["js", "jsx", "json"],
  setupFiles: ["<rootDir>/src/test/jestSetup.js"],
};
