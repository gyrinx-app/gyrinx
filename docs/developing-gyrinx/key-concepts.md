# Key Concepts

{% hint style="info" %}
This section assumes you are familiar with Python+Django, Postgres, and HTML/CSS/Javascript.
{% endhint %}

Quick guide to where to go:

* Jump in and run the application locally → see the [GitHub README](https://github.com/gyrinx-app/gyrinx)
* Build or extend support for archetypal concepts in Necromunda → **Content**
* Add user-facing functionality and tools → **Core**
* Improve the frontend of the application → **Core**

## Project Structure

At the project level we have a few useful and shared folders or libraries such as overriding core or Django templates to improve the form rendering or to have shared models between the whole application.

We manage our settings using three settings files:

* a base file simply called `settings.py`
* a `settings_dev.py` file for local development
* a `settings_prod.py` file for production

### Directory Structure

Here's a breakdown of the directories in the repo, with files that are not important for development excluded.

```
.
├── CODE-OF-CONDUCT.md      -- Code of conduct for the project
├── CODEOWNERS              -- GitHub code owners for the project
├── CONTRIBUTING.md         -- Contribution guidelines
├── Dockerfile              -- Dockerfile for building the Gyrinx image
├── README.md               -- Project overview and instructions
├── SECURITY.md             -- Security policy for the project
├── cloudbuild.yaml         -- Google Cloud Build configuration
├── content                 -- Historic directory for the initial content, now deprecated
├── docker                  -- Docker configuration directory, with entrypoint etc.
├── docker-compose.yml      -- Docker Compose configuration for running Gyrinx locally
├── docs                    -- Documentation for the content you're looking at now
├── gyrinx                  -- The main application directory
│   ├── api                 -- API endpoints (used by webhooks from Patreon)
│   ├── conftest.py         -- pytest configuration
│   ├── content             -- content app with models etc for Necromunda content
│   ├── core                -- the core behaviour of the application
│   ├── models.py           -- shared models
│   ├── pages               -- static content
│   ├── settings.py         -- shared settings for the application
│   ├── settings_dev.py     -- development settings
│   ├── settings_prod.py    -- production settings
│   ├── templates           -- HTML templates
│   └── urls.py             -- URL routing
├── package.json            -- Node.js package configuration
├── pyproject.toml          -- Python package configuration
├── requirements.txt        -- Python package requirements
└── scripts
    └── manage.py           -- Dyango command line management script
```

### Application Structure

The project is structured into four Django apps. They are: **core**, **content**, **api** and **pages**.

Within **content** we have the models and admin for the core content library; this is where our content managers spend most of their time on the admin side ensuring that all the data inside Gyrinx is up to date with the Necromunda rulebooks.

In the **core** area we have lists and list fighters and all the functionality that is more user facing.

Within **pages** we have the static, user-facing documentation.
