# Operational Overview

Gyrinx is a Django application is hosted on Google Cloud Run.

This was a decision to help mitigate operational overheads. Google Cloud Run scales down to zero when not in use and the Google Cloud Platform offers a huge amount of operational tools and dashboards for free.

{% hint style="info" %}
At time of writing, there is only one environment (production). In future, we may expand this to have a staging environment for testing features before they launch.
{% endhint %}

The application is deployed via Google Cloud Build. This deployment process is run directly out of GitHub when code is pushed or merged into main. The database is Postgres and migrations are run when the Docker container spins up in Google Cloud Run.

{% hint style="info" %}
_There is a potential bug here where if two containers span up at the same time, the migrations could be run simultaneously. This is something to fix in the future._
{% endhint %}

In front of the application, we have Google Cloud's load balancing offering CDN capabilities.

We use most of the default dashboards built into Google Cloud for observability, and we additionally use web hooks to push specific alerts into our Discord [#ops channel](https://discord.com/channels/1337524316987985963/1337780084102402140).&#x20;
