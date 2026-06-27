export const theme = {
  bg: "#0a0e17",
  card: "#141b2d",
  cardBorder: "#1e2a45",
  accent: "#00d4aa",
  accentDim: "#00a884",
  gold: "#f0b429",
  text: "#e8edf5",
  textMuted: "#8892a8",
  danger: "#ff4757",
  warning: "#ffa502",
  success: "#2ed573",
  pass: "#636e72",
  gradeA: "#00d4aa",
  gradeB: "#f0b429",
  gradeC: "#ffa502",
};

export function decisionColor(decision: string): string {
  switch (decision) {
    case "Value Bet":
      return theme.success;
    case "Arbitrage":
      return theme.gold;
    case "Watchlist":
      return theme.warning;
    default:
      return theme.pass;
  }
}

export function gradeColor(grade: string): string {
  if (grade === "A+" || grade === "A") return theme.gradeA;
  if (grade === "B") return theme.gradeB;
  if (grade === "C") return theme.gradeC;
  return theme.pass;
}

export function formatKickoff(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
