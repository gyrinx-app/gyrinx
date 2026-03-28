# Colour Clustering Guide

How to identify and consolidate near-duplicate colours.

## Process

### 1. Convert to CIELAB

Convert hex colours to CIELAB colour space for perceptual distance calculation.

### 2. Calculate Delta-E

Use Delta-E (ΔE) as the distance metric:

- ΔE < 2.3: imperceptible difference
- ΔE < 5: minimal, noticeable only side-by-side
- ΔE < 10: noticeable but similar
- ΔE > 10: clearly different colours

### 3. Cluster

Simple greedy grouping by distance threshold (ΔE < 5):

1. Sort colours by frequency (most common first)
2. First colour becomes the seed of cluster 1
3. For each remaining colour, check distance to all existing cluster seeds
4. If within threshold of any seed, add to that cluster
5. Otherwise, start a new cluster

### 4. Select Representative

For each cluster, choose the representative colour:

- Prefer the most frequent member
- If tied, prefer the one closest to a Bootstrap default
- Document the choice rationale
