# Key Concepts

{% hint style="info" %}
This section assumes you are reasonably familiar with Python, Django, Postgres, and HTML/CSS/Javascript. Those are the main technologies we use. If you're not, don't let that stop you — we'd still welcome your contributions!
{% endhint %}

Quick guide to where to go:

- Jump in and run the application locally → see the [GitHub README](https://github.com/gyrinx-app/gyrinx)
- Build or extend support for archetypal concepts in Necromunda → **Content**
- Add user-facing functionality and tools → **Core**
- Improve the frontend of the application → **Core**

## Project Structure

The project is structured into four Django apps. They are: **core**, **content**, **api** and **pages**.

Within **content** we have the models and admin for the core content library; this is where our content managers spend most of their time on the admin side ensuring that all the data inside Gyrinx is up to date with the Necromunda rulebooks.

In the **core** area we have lists and list fighters and all the functionality that is more user facing.

Within **pages** we have the static, user-facing documentation.

There are also a few useful and shared folders or libraries such as overriding core Django templates to improve the form rendering, to have shared models between the whole application.

### Django Settings

We manage our settings using three settings files:

- a base file simply called `settings.py`
- a `settings_dev.py` file for **local development**
- a `settings_prod.py` file for **production**

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

## Technical Principles of Gyrinx

### Not an SPA

We could have built Gyrinx as a React-based single-page application with an API. However, for reasons of accessibility and ease of integration with Django, as well as just the simplicity of HTML and an ability to work extensively with the blessed path in Django, we did not take the SPA approach. As a result, our primary way of building should be pages that offer simple HTML-driven UI, and where changes happen, they happen via a form submit.

This principle keeps the pages easy to reason about and simple, and allows us to do most performance work on the server side and simply render HTML.

### Mobile-first

We design and build Gyrinx mobile-first. That means that every page should work in linear, single column view _first_, and scale up from there. Explicitly: it's OK if a page's design _only_ looks right on mobile for the first iteration, with other design changes coming later.

This principle is chosen because:

1. It forces thoughtful ordering, heirarchy and placement of key UI elements, helping with a simple user experience
2. We expect users to use Gyrinx on their phones at the gaming table

### Make it work; make it right; make it fast

Performance comes after we build stuff _right_. Necromunda is a complex game and it can be hard to get the implementation of a specific game rule exactly right first time. As a result, we try to always-be-shipping: get stuff working, ship it, and iterate.

Performance is important, but performance optimising the wrong implementation is waste of time. When optimising performance, we start with the basics: duplication of database queries and unnecessary round trips. We're not really interested in algorithmic complexity.
