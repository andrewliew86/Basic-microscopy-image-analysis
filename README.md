# Bio Image Analysis

This repository is a small sandbox for exploring simple image-analysis methods for segmenting and analyzing bacterial and eukaryotic cells, including bacterial colonies on agar plates. The focus is on lightweight, accessible workflows such as SAM, Weka-based machine learning, and ImageJ/Fiji-style processing pipelines.

The goal is to test practical ways to:

- detect and segment individual cells in microscopy images
- detect and count bacterial colonies on agar plates
- separate foreground objects from background
- generate binary and labeled masks for downstream analysis
- quantify morphology and intensity-related features
- compare simple segmentation approaches across different sample types

The [bacterial colony segmentation script](bacterial_colony_segmentation_count.py) isolates the agar region, segments colonies, and exports labeled masks and measurements.


