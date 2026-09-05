import type { NextConfig } from 'next';

const isGitHubPages = process.env.GITHUB_PAGES === 'true';
const repositoryName = process.env.GITHUB_REPOSITORY?.split('/')[1] || 'local-prompt-studio';
const pagesBasePath = `/${repositoryName}`;

const nextConfig: NextConfig = {
  output: isGitHubPages ? 'export' : undefined,
  assetPrefix: isGitHubPages ? pagesBasePath : undefined,
  trailingSlash: isGitHubPages,
};

export default nextConfig;
