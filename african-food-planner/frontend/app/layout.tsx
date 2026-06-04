import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "African Food Planner",
  description: "Plan meals and manage your pantry",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          fontFamily: "system-ui, sans-serif",
          background: "var(--color-bg)",
          color: "var(--color-text)",
        }}
      >
        {children}
      </body>
    </html>
  );
}
