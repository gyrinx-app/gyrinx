# Overview

This documentation site captures technical documentation for Gyrinx.

Gyrinx is a [Django](https://www.djangoproject.com/) application running in [Google Cloud Platform](https://console.cloud.google.com/). It runs in [Cloud Run](https://cloud.google.com/run), a serverless application platform, with [Cloud SQL (specifically, Postgres)](https://cloud.google.com/sql/postgresql) for data storage. [Cloud Build](https://cloud.google.com/build) is used to deploy the application. The frontend is built with [Bootstrap 5](https://getbootstrap.com/docs/5.0/getting-started/introduction/).

The code is hosted here on [GitHub](https://github.com/gyrinx-app). When new code is pushed on main to the [gyrinx repo](https://github.com/gyrinx-app/gyrinx), it is automatically deployed by Cloud Build. This includes running database migrations. Code is tested automatically in [Github Actions](https://github.com/gyrinx-app/gyrinx/actions).

Analytics are through [Google Analytics](https://analytics.google.com/analytics/web/#/p470310767/reports/intelligenthome?params=_u..nav%3Dmaui).

Project tasks, issues and to-dos are managed in the [Gyrinx GitHub Project](https://github.com/orgs/gyrinx-app/projects/1).

## Project Structure

The project is structured into four Django apps. They are: **core**, **content**, **api** and **pages**.

Within **content** we have the models and admin for the core content library; this is where our content managers spend most of their time on the admin side ensuring that all the data inside Gyrinx is up to date with the Necromunda rulebooks.

In the **core** area we have lists and list fighters and all the functionality that is more user facing.

Within **pages** we have static documentation that you are looking at right now.

At the project level we have a few useful and shared folders or libraries such as overriding core or Django templates to improve the form rendering or to have shared models between the whole application. We manage our settings using three settings files:

* a base file simply called settings.py
* a settings\_dev.py file for local development
* a settings\_prod.py file for production
