export const number = (value: number | null | undefined, digits = 0) => value == null ? "—" : new Intl.NumberFormat("en-US", { maximumFractionDigits: digits }).format(value);
export const compactNumber = (value: number) => new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 2 }).format(value);
export const price = (value: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
export const datetime = (value: string | null | undefined) => value ? new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(new Date(value)) + " UTC" : "—";
export const shortId = (value: string) => value.slice(0, 8);
export const score = (value: number | null | undefined) => value == null ? "—" : value.toFixed(1);
export const sessionName = (value: string) => ({ PREMARKET: "Pre-market", RTH: "Regular hours", AFTERHOURS: "After-hours" }[value] ?? value);
