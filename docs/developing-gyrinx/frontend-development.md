# Frontend Development

Gyrinx follows a server-rendered approach using Django templates with Bootstrap 5 for styling. The frontend emphasizes simplicity, accessibility, and mobile-first design.

## Technology Stack

### Core Technologies

- **Django Templates** - Server-side rendering with template inheritance
- **Bootstrap 5** - CSS framework for responsive design
- **SCSS** - CSS preprocessing for maintainable styles
- **Vanilla JavaScript** - Minimal client-side interactivity

### Build Tools

- **npm** - Package management and build scripts
- **SCSS compilation** - CSS preprocessing
- **No bundlers** - Keep it simple with direct file serving

## Template Architecture

### Template Hierarchy

```
templates/
├── core/layouts/
│   ├── base.html          # Root template with <html>, <head>, <body>
│   ├── page.html          # Simple content pages
│   └── foundation.html    # Minimal template for special cases
├── core/includes/
│   ├── back.html          # Standard back button component
│   ├── fighter_card.html  # Fighter display component
│   └── ...                # Other reusable components
└── core/
    ├── list.html          # Page-specific templates
    ├── campaign.html
    └── ...
```

### Template Usage Patterns

**Full Page Layout**

```django

<div data-gb-custom-block data-tag="extends" data-0='core/layouts/base.html'></div>

<div data-gb-custom-block data-tag="block">My Page Title</div>

<div data-gb-custom-block data-tag="block">

<div class="container">
    <h1>Page Content</h1>
</div>

</div>

```

**Simple Content Page**

```django

<div data-gb-custom-block data-tag="extends" data-0='core/layouts/page.html'></div>

<div data-gb-custom-block data-tag="block">Simple Page</div>

<div data-gb-custom-block data-tag="block">

<p>Simple content without navigation complexity</p>

</div>

```

**Back Button Navigation**

```django

<div data-gb-custom-block data-tag="include" data-0='core/includes/back.html' data-text='Back to Lists'></div>

```

## Styling with Bootstrap 5

### Mobile-First Approach

All designs start with mobile layout and scale up:

```html
<!-- Mobile-first column layout -->
<div class="row">
    <div class="col-12 col-md-8">
        <!-- Main content: full width on mobile, 8/12 on desktop -->
    </div>
    <div class="col-12 col-md-4">
        <!-- Sidebar: full width on mobile, 4/12 on desktop -->
    </div>
</div>
```

### Common Bootstrap Patterns

**Cards for Content Grouping**

```html
<div class="card">
    <div class="card-header">
        <h5 class="card-title">Section Title</h5>
    </div>
    <div class="card-body">
        <p class="card-text">Content goes here</p>
    </div>
</div>
```

**Form Styling**

```html
<form method="post">


<div data-gb-custom-block data-tag="csrf_token"></div>

    <div class="mb-3">
        <label for="name" class="form-label">Name</label>
        <input type="text" class="form-control" id="name" name="name">
    </div>
    <button type="submit" class="btn btn-primary">Submit</button>
</form>
```

**Responsive Tables**

```html
<div class="table-responsive">
    <table class="table table-striped">
        <thead>
            <tr>
                <th>Fighter</th>
                <th>Cost</th>
                <th class="d-none d-md-table-cell">Equipment</th>
            </tr>
        </thead>
        <!-- Table content -->
    </table>
</div>
```

## SCSS Development

### File Structure

```
gyrinx/core/static/core/scss/
├── styles.scss           # Main entry point
├── _variables.scss       # Custom Bootstrap variables
├── _components.scss      # Custom component styles
└── _utilities.scss       # Utility classes
```

### Build Process

```bash
# Compile SCSS to CSS
npm run css

# Watch for changes and rebuild
npm run watch

# Lint SCSS
npm run css-lint
```

### Custom Styling Approach

- Override Bootstrap variables rather than writing custom CSS
- Use Bootstrap utility classes when possible
- Create component-specific styles only when needed

```scss
// _variables.scss - Override Bootstrap defaults
$primary: #your-brand-color;
$font-family-base: 'Your-Font', sans-serif;

// _components.scss - Custom components
.fighter-card {
    @extend .card;

    .fighter-name {
        @extend .card-title;
        color: $primary;
    }
}
```

## JavaScript Usage

### Minimal JavaScript Philosophy

Gyrinx uses minimal JavaScript, favoring server-side rendering and simple form submissions.

### When to Use JavaScript

- Form enhancements (show/hide fields)
- Client-side validation feedback
- Simple interactive elements (dropdowns, modals)
- Progressive enhancement only

### JavaScript Patterns

```javascript
// Progressive enhancement
document.addEventListener('DOMContentLoaded', function() {
    // Only enhance if JavaScript is available
    const enhancedElements = document.querySelectorAll('.js-enhance');
    enhancedElements.forEach(element => {
        // Add JavaScript behavior
    });
});

// Avoid JavaScript dependencies for core functionality
// Core features must work without JavaScript
```

## Form Handling

### Django Form Integration

```python
# forms.py
class ListForm(forms.ModelForm):
    class Meta:
        model = List
        fields = ['name', 'content_house', 'public']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'content_house': forms.Select(attrs={'class': 'form-select'}),
            'public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
```

```django
<!-- Template -->
<form method="post">


<div data-gb-custom-block data-tag="csrf_token"></div>

    {{ form.as_p }}
    <button type="submit" class="btn btn-primary">Save</button>
</form>
```

### Custom Form Rendering

```django
<!-- Manual form field rendering for better control -->
<div class="mb-3">
    <label for="{{ form.name.id_for_label }}" class="form-label">
        {{ form.name.label }}
    </label>
    {{ form.name }}


<div data-gb-custom-block data-tag="if">

        <div class="text-danger">{{ form.name.errors }}</div>


</div>

</div>
```

## Static File Management

### Development

```bash
# Collect static files for development
manage collectstatic --noinput

# Files are served by Django in development
DEBUG=True  # in settings_dev.py
```

### Production

- WhiteNoise serves static files
- Files are collected during deployment
- CSS is compiled from SCSS in build process

### File Organization

```
gyrinx/core/static/core/
├── css/
│   └── styles.css        # Compiled from SCSS
├── js/
│   └── index.js          # Minimal JavaScript
├── img/
│   ├── brand/           # Logos and branding
│   └── content/         # Game-related images
└── scss/
    └── ...              # Source SCSS files
```

## Performance Considerations

### Template Performance

- Use \`

\` efficiently\
\- Cache template fragments with \`\`\
\- Minimize database queries in templates

### CSS Performance

- Minimize custom CSS
- Use Bootstrap utilities to reduce file size
- Optimize images for web delivery

### JavaScript Performance

- Load JavaScript at end of `<body>`
- Use event delegation for dynamic content
- Avoid large JavaScript frameworks

## Accessibility

### Built-in Bootstrap Accessibility

- Use semantic HTML elements
- Leverage Bootstrap's ARIA attributes
- Ensure keyboard navigation works

### Custom Accessibility

```html
<!-- Proper labeling -->
<label for="fighter-name">Fighter Name</label>
<input type="text" id="fighter-name" name="name" required>

<!-- ARIA attributes for dynamic content -->
<div role="alert" aria-live="polite" id="status-message"></div>

<!-- Focus management -->
<button class="btn btn-primary" aria-expanded="false" data-bs-toggle="collapse">
    Toggle Section
</button>
```

## Testing Frontend Code

### Template Testing

```python
@pytest.mark.django_db
def test_list_template_renders():
    client = Client()
    user = User.objects.create_user(username="test", password="test")
    response = client.get("/lists/")

    assert response.status_code == 200
    assert "Lists" in response.content.decode()
```

### CSS Testing

- Visual regression testing (manual)
- Cross-browser testing on common devices
- Mobile responsiveness testing

### JavaScript Testing

- Manual testing for progressive enhancement
- Ensure core functionality works without JavaScript

## Future Considerations

### htmx Integration

While not currently used, htmx could add interactivity:

```html
<!-- Potential future pattern -->
<button hx-post="/lists/create/" hx-target="#list-container">
    Create List
</button>
```

### Performance Monitoring

- Consider adding Core Web Vitals monitoring
- Monitor CSS bundle size growth
- Track JavaScript execution time
