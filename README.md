# SiteWatch

A simple Python script to monitor web pages for changes and send email notifications via [Resend](https://resend.com/).

![SiteWatch](watcher.webp "SiteWatch")

## Table of Contents

- [Features](#features)
- [Configuration](#configuration)
- [Local Development](#local-development)
- [Pre-commit Hooks](#pre-commit-hooks)
- [Docker Deployment](#docker-deployment)
- [Monitoring Frequency (Cron)](#monitoring-frequency-cron)

## Features

- Monitor multiple URLs simultaneously.
- Extract visible text (ignoring scripts/styles) to avoid false positives.
- Keep history of changes in Markdown files.
- Email notifications using [Resend](https://resend.com/).
- Dockerized for easy deployment.

## Configuration

The script is configured via environment variables. You can create a `.env` file based on `template.env`.

| Variable | Description | Default |
|----------|-------------|---------|
| `RESEND_API_KEY` | Your Resend API key. | Required |
| `MONITOR_URLS` | Comma-separated list of URLs to monitor. | Required |
| `EMAIL_RECIPIENTS` | Comma-separated list of email addresses. | Required |
| `EMAIL_FROM` | Sender address (must be verified in Resend). | `Notification <onboarding@resend.dev>` |
| `EMAIL_SUBJECT` | Subject of the notification email. | `Page Updated` |
| `EMAIL_HTML` | HTML body of the email. Use `{url}` as a placeholder. | See `script.py` |

## Local Development

1. Install [uv](https://docs.astral.sh/uv/):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
2. Install dependencies:
```bash
uv sync
```
3. Copy `template.env` to `.env` and fill in your details.
4. Run the script:
```bash
uv run script.py
```

## Pre-commit Hooks

This project uses [pre-commit](https://pre-commit.com/) to maintain code quality. The hooks include:
- **Ruff**: For linting and formatting.
- **Gitleaks**: To prevent secrets from being committed.
- **Standard hooks**: To check YAML, TOML, JSON files, trailing whitespace, etc.

### Setup

1. Install dependencies (including `pre-commit`):
```bash
uv sync
```

2. Install the git hooks:
```bash
uv run pre-commit install
```

### Usage

The hooks will run automatically on every `git commit`. To run them manually on all files:
```bash
uv run pre-commit run --all-files
```

## Docker Deployment

Build and run with Docker:

```bash
docker build -t sitewatch .
docker run -d \
  --name sitewatch \
  --env-file .env \
  sitewatch
```

The script runs every minute inside the container (configured in `crontab`).

## Monitoring Frequency (Cron)

The script uses `cron` inside the Docker container to handle periodic monitoring. This allows the script to run automatically without manual intervention.

### How it works:
- **`crontab` file**: Defines the schedule using standard cron syntax.
- **`entrypoint.sh`**: When the container starts, it registers the `crontab` file and starts the cron service in the background.
- **Execution**: The script is executed via `uv run` to ensure all dependencies are available.

### Modifying the schedule:
To change how often the script runs, edit the `crontab` file in the root of the project:

```bash
# Example: Run every minute (current default)
*/1 * * * * cd /app && /bin/uv run script.py >> /var/log/cron.log 2>&1

# Example: Run every 15 minutes
*/15 * * * * cd /app && /bin/uv run script.py >> /var/log/cron.log 2>&1

# Example: Run every hour at the top of the hour
0 * * * * cd /app && /bin/uv run script.py >> /var/log/cron.log 2>&1

# Example: Run every day at midnight
0 0 * * * cd /app && /bin/uv run script.py >> /var/log/cron.log 2>&1
```

After modifying the `crontab` file, you need to rebuild the Docker image:
```bash
docker build -t sitewatch .
```
