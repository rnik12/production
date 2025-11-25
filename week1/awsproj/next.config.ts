import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export", // build static files into /out
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
