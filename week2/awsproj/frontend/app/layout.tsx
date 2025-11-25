import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AI Digital Twin",
  description: "Digital Twin chat deployed on AWS App Runner"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
