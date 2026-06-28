export const themeStorageKey = "aop-theme";

export const themeModes = ["light", "dark", "system"] as const;

export type ThemeMode = (typeof themeModes)[number];

export function isThemeMode(value: string): value is ThemeMode {
  return themeModes.includes(value as ThemeMode);
}
