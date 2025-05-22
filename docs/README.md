# Overview

This documentation site captures technical documentation for [Gyrinx](https://gyrinx.app).

Gyrinx is a [Django](https://www.djangoproject.com/) application running in [Google Cloud Platform](https://console.cloud.google.com/). It runs in [Cloud Run](https://cloud.google.com/run), a serverless application platform, with [Cloud SQL (specifically, Postgres)](https://cloud.google.com/sql/postgresql) for data storage. [Cloud Build](https://cloud.google.com/build) is used to deploy the application. The frontend is built with [Bootstrap 5](https://getbootstrap.com/docs/5.0/getting-started/introduction/).

The code is hosted here on [GitHub](https://github.com/gyrinx-app). When new code is pushed on main to the [gyrinx repo](https://github.com/gyrinx-app/gyrinx), it is automatically deployed by Cloud Build. This includes running database migrations. Code is tested automatically in [Github Actions](https://github.com/gyrinx-app/gyrinx/actions).

Analytics are through [Google Analytics](https://analytics.google.com/analytics/web/#/p470310767/reports/intelligenthome?params=_u..nav%3Dmaui).

Project tasks, issues and to-dos are managed in the [Gyrinx GitHub Project](https://github.com/orgs/gyrinx-app/projects/1).

***

## Getting Started

To get started developing Gyrinx:

1. **Begin with [Key Concepts](developing-gyrinx/key-concepts.md)** :star: - Overview of the project structure and principles
2. **Set up your environment** - Follow the setup guide in the GitHub README
3. **Dive deeper**:
   - [Models and Database](developing-gyrinx/models-and-database.md) - Understanding the data layer
   - [Frontend Development](developing-gyrinx/frontend-development.md) - Working with templates and styling
   - [Testing](developing-gyrinx/testing.md) - Writing and running tests
   - [History Tracking](developing-gyrinx/history-tracking.md) - Understanding audit trails

## Operations

For deployment and operational information:
- [Deployment](deployment.md) - How the application is deployed and managed
- [Operational Overview](operations/operational-overview.md) - Infrastructure and monitoring
- [Runbook](runbook.md) - Live operational procedures (team access only)
