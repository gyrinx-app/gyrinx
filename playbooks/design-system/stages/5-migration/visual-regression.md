# Visual Regression Process

## Taking Screenshots

- Fixed viewport: 1280px desktop, 375px mobile
- Wait for fonts/images to load, disable animations
- Use consistent browser (Chrome via automation)

## Comparison

- Flag views where visual differences are unexpected
- Document intended visual changes vs unintended regressions
- Sub-pixel rendering noise is expected — focus on meaningful differences

## Storage

```
output/migration/{unit-name}/
  before/{view-name}-desktop.png
  after/{view-name}-desktop.png
  pr-description.md
```
