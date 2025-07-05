# Technology Choices

The mantra for technology choices within Gyrinx is: _<mark style="background-color:yellow;">"choose boring technology".</mark>_

That's because we have a small team and would like to encourage contributions from outside that team. We also want to be able to make as much use of existing knowledge in books and on the internet for the technology we use, so that we are not ever encountering problems for the first time.

<figure><img src="https://imgs.xkcd.com/comics/wisdom_of_the_ancients.png" alt=""><figcaption><p>We've all been there.</p></figcaption></figure>

## Languages

Primarily, we choose Python, HTML, CSS, and vanilla JavaScript.

These are well-known, well-documented, used extensively and basically uncontroversial. There are a smattering of other languages used in the Gyrinx repositories, but these dominate.

One slight variant in particular is that because we use Django, we use the Django template language. We also use Bootstrap, which means our HTML is fairly liberally smattered with Bootstrap class names. And lastly, and in the future, we may use [htmx](https://htmx.org/), which will also extend the HTML with some unusual additional attributes.

## Frameworks

### Django

Django is an easy and obvious choice for a Python framework. You get a huge amount for free. There is a great community and it's very actively developed. The documentation is high quality and there is a rich ecosystem of third-party plugins and tools to build on top of and around. In many cases we get entire chunks of functionality for free thanks to Django ecosystem — one great example is AllAuth, although there are many other examples.

### Bootstrap

Like Django, Bootstrap is a mature framework and has excellent documentation, is well battle-tested and has become much more usable for a diverse array of projects in the last few years. Their excellent support for mobile-first and responsive applications as well as accessibility built-in means we can get a lot for free as we build out Gyrinx.

### Postgres

Postgres is simple, battle-tested and has excellent support in the cloud. It's an obvious choice for a database and fairly uncontroversial.

### Google Cloud

Google Cloud has emerged as a mature and easy to use cloud provider that gives developers a lot for free and without configuration. It is easy to configure, easy to secure and helps you achieve both of the above. Ultimately, we could have picked one of Google Cloud, AWS and Azure, and it was purely a case of familiarity, ease-of-use, and a generous initial credit grant that meant we went with Google Cloud.

### Docker

Using Docker to run Gyrinx locally, and in particular using Docker Compose standardises our use of container deployment and makes it easy for other non-core developers to spin up Gyrinx and make contributions. We should always aim to have new functionality work in Docker from the start so that it can be developed on locally. This also stands us in good stead for deployment of the application as containerised environments are fairly replicable locally and into the cloud.

## Tools

### GitHub

We use GitHub for source code hosting, because it is a high quality and feature-full tool for collaborating on software development.

We use GitHub Projects for project management and track milestones within the main Gyrinx repo.

We use a prioritization system of labels P0, P1, P2, and P3 to indicate the relative priority. Tasks shift up towards P0 as they become more important. Generally, the work in progress should really only be P0 or P1 unless someone is looking at a "good first task".

We annotate issues in the GitHub project with whether they are features or bugs or simple tasks.&#x20;

When estimating, we use a simple story point system of 1, 2, 3 where 1 is approximately a couple of hours, 2 is potentially half a day to a day, and 3 is more than a day.&#x20;

## On the radar

### htmx

An obvious extension to our current technology stack is to add htmx. This would give the app a feeling of more snappiness and more of a single page application because we could load in partial pages and add a layer of interactivity on the client side that would be friendly to the user experience. However, as this complicates both the template layer and some of the Django side, we're not going to adopt htmx for the time being.

### Cache

Django's cache becans are currently configured entirely in memory. This has obvious limitations as usage increases, but it does simplify operational overheads and reduce costs by not requiring us to have a cache cluster spun up. However, an obvious extension to our tech stack would be to add one of Redis or Memcache to our stack to act as a permanent and shared cache that persists through deploys.

