import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "PicPal",
  description: "通过连续对话规划顺路的北京行程，并发现沿途值得拍的位置与建议时段。",
  icons: {
    icon: [{ url: "/brand/picpal-mark.png", type: "image/png" }],
    apple: [{ url: "/brand/picpal-mark.png", type: "image/png" }],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#f3f2ff",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
