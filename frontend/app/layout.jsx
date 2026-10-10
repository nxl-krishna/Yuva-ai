import "./globals.css";

export const metadata = { title: "Yuva AI" };

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
