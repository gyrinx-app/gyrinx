# Analytics Dashboard Guide

This guide explains how the Analytics Dashboard works in the Django admin interface.

## Overview

The Analytics Dashboard provides three hard-coded graphs that display key metrics about your application:

1. **User Registrations** - Daily count of new user registrations
2. **Top Events (Excluding Views)** - Top 10 event types over time
3. **Cumulative Creations** - Running totals of fighters, lists, and campaigns

Each graph supports time scale filtering to view data over different periods.

## Accessing the Dashboard

1. Navigate to **Django Admin**
2. Click on **Analytics** in the header (next to "View site")
3. The dashboard will load with the default time scale (Last 30 Days)

## Time Scale Options

You can filter the data shown in all graphs using the time scale selector:

- **Last 7 Days** - Shows data from the past week
- **Last 30 Days** - Shows data from the past month (default)
- **Last 90 Days** - Shows data from the past three months
- **Last Year** - Shows data from the past 365 days

Changing the time scale will reload the page with updated data for all graphs.

## Graph Descriptions

### 1. User Registrations

This graph shows the daily count of new user registrations. Each point on the graph represents how many users joined on that specific day. Days with no registrations will show as 0.

**Use cases**:

- Monitor user growth trends
- Identify spikes in registrations (e.g., after marketing campaigns)
- Track the effectiveness of user acquisition efforts

### 2. Top Events (Excluding Views)

This multi-line graph displays the top 10 most frequent event types over time, excluding view events. Each line represents a different event type (e.g., "list - create", "fighter - update").

**Use cases**:

- Understand which features are most actively used
- Track user engagement patterns
- Identify trends in user behavior

### 3. Cumulative Creations

This graph shows three cumulative lines tracking the total number of:

- **Fighters** created in list-building lists
- **Lists** in list-building mode
- **Campaigns** created

Each line shows the running total over time, so values always increase or stay flat.

**Use cases**:

- Monitor overall content growth
- Track adoption of different features
- Understand the ratio between different content types

## Technical Implementation

### Data Generation

All graphs use Django ORM queries to fetch data:

1. **Complete Date Ranges**: Every graph generates a complete set of dates for the selected time period, filling in 0 for days with no data
2. **Efficient Queries**: Data is fetched using Django's aggregation functions (`Count`, `TruncDate`)
3. **Simple Display**: Charts use string labels for dates, avoiding complex time axis configurations

### Chart Configuration

The dashboard uses Chart.js 4.4.0 with simple, reliable configurations:

- Line charts for all graphs
- String-based x-axis labels
- Responsive design that works on all screen sizes
- Clear legends and axis titles

## Customization

While the graphs themselves are hard-coded, you can:

1. **Modify Time Scales**: Edit the `scale_map` in `analytics/admin.py` to add or change time period options
2. **Adjust Colors**: Update the color arrays in each data method to change graph appearance
3. **Add New Graphs**: Create new data methods following the existing pattern and add corresponding chart initialization in the template

### Adding a New Graph

To add a new graph:

1. Create a data method in `AnalyticsAdminSite` that returns:

   ```python
   {
       "labels": [list of date strings],
       "datasets": [{"label": "...", "data": [...], ...}]
   }
   ```

2. Add the method call in `analytics_dashboard_view`

3. Add a new chart container in the template

4. Initialize the chart with basic Chart.js configuration

## Troubleshooting

### Common Issues

1. **Graphs show no data**:
   - Check that you have data in the selected time range
   - Verify database connectivity
   - Look at Django logs for query errors

2. **Graphs load slowly**:
   - Consider adding database indexes on date columns
   - Reduce the time range to improve performance

3. **Missing data points**:
   - This is normal - the graphs fill in 0 for days with no activity
   - All dates in the range are displayed even if no events occurred

### Performance Tips

1. **Database Indexes**: Ensure these columns are indexed:
   - `auth_user.date_joined`
   - `core_event.created`
   - `core_list.created`
   - `core_listfighter.created`
   - `core_campaign.created`

2. **Time Ranges**: Shorter time ranges load faster

## Security Considerations

- The analytics dashboard is only accessible to Django admin users
- All queries use Django ORM, preventing SQL injection
- No user input is directly used in queries
