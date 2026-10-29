export const money = (n: number) => n.toLocaleString("zh-TW");
export const date = (value: string) =>
  new Date(value).toLocaleString("zh-TW", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
