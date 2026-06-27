/** @type {import('expo/config').ExpoConfig} */
module.exports = ({ config }) => ({
  ...config,
  extra: {
    ...config.extra,
    oddsApiKey: process.env.THE_ODDS_API_KEY || process.env.ODDS_API_KEY || "",
    apiBaseUrl: process.env.KRAITOS_API_URL || "",
  },
});
