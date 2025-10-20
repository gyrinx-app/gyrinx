# Runbook

{% hint style="info" %}
This is live operational information for Gyrinx. You should not be able to access this without being given an account — it's here for the development team.

We're a small, not-for-profit team building tools for enthusiasts. If you find you unexpectedly have access, or think this is leaking information it should not, feel free to email [tom@gyrinx.app](mailto:tom@gyrinx.app) or [file a security advisory](https://github.com/gyrinx-app/gyrinx/security/advisories/new).&#x20;
{% endhint %}

### Quick Links

- Coud Run
  - [Monitoring](https://console.cloud.google.com/monitoring/dashboards/integration/cloud_run.cloudrun-monitoring;duration=P1D?invt=Abt3Dw\&project=windy-ellipse-440618-p9\&pageState=\(%22eventTypes%22:\(%22selected%22:%5B%22CLOUD_ALERTING_ALERT%22,%22CLOUD_RUN_DEPLOYMENT%22%5D\)\))
  - Production
    - [Metrics](https://console.cloud.google.com/run/detail/europe-west2/gyrinx/metrics?invt=Abt3Dw\&project=windy-ellipse-440618-p9)
    - [Logs](https://console.cloud.google.com/run/detail/europe-west2/gyrinx/logs?invt=Abt3Dw\&project=windy-ellipse-440618-p9)
- Cloud Build
  - [Dashboard](https://console.cloud.google.com/cloud-build/dashboard?invt=Abt3Dw\&project=windy-ellipse-440618-p9)
  - [Build History](https://console.cloud.google.com/cloud-build/builds;region=global?query=trigger_id%3D%22bd49e415-bc5c-411a-a19d-ec77599c3ddf%22\&invt=Abt3Dw\&project=windy-ellipse-440618-p9)
- Cloud SQL
  - Production
    - [Instance](https://console.cloud.google.com/sql/instances/gyrinx-app-bootstrap-db/overview?invt=Abt3Dw\&project=windy-ellipse-440618-p9)
- Logs
  - [Dashboard](https://console.cloud.google.com/monitoring/dashboards/resourceList/logs;duration=P1D?invt=Abt3Dw\&project=windy-ellipse-440618-p9)

### Architecture Overview

<figure><img src=".gitbook/assets/image (2).png" alt=""><figcaption><p>Architecture overview of Gyrinx</p></figcaption></figure>
