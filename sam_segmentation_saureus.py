
# Run inside Fiji: Plugins > New > Script
# Language: Python (Jython)

from ij import IJ
from ij.plugin.frame import RoiManager
from ij.plugin.filter import Analyzer
from ij.measure import Measurements, ResultsTable
from ij.gui import PointRoi
from java.io import File
from ij import ImagePlus
from ij.gui import Overlay
from ij.process import ByteProcessor, ShortProcessor
from java.awt import Color
import os

# ======================================
# CONFIGURATION
# ======================================

IMAGE_PATH = r"C:\Users\Andrew\raw_data\wt.zvi"
OUTPUT_DIR = r"C:\Users\Andrew\output"

PROMINENCE = 200
SAM_MODEL = "SAM2 Tiny"

# ======================================
# 1. LOAD IMAGE
# ======================================

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

imp = IJ.openImage(IMAGE_PATH)

if imp is None:
    raise IOError("Cannot open image: " + IMAGE_PATH)
    
# If image is a stack, keep only the first slice
if imp.getStackSize() > 1:
    imp.setSlice(1)
    imp = imp.crop()
    print("Stack detected: keeping first slice only")
    
imp.show()
IJ.selectWindow(imp.getTitle())

# Clear existing ROI Manager
rm = RoiManager.getInstance()
if rm is None:
    rm = RoiManager()

rm.reset()

# ======================================
# 2. FIND MAXIMA
# ======================================

IJ.run(
    imp,
    "Find Maxima...",
    "prominence=%s strict exclude light output=[Point Selection]"
    % PROMINENCE
)

# The resulting Point ROI contains all
# candidate cell centres.
point_roi = imp.getRoi()

if point_roi is None or not isinstance(point_roi, PointRoi):
    raise RuntimeError("Find Maxima produced no point prompts.")

n_prompts = point_roi.getNCoordinates()
print("Detected %d candidate cells" % n_prompts)

# ======================================
# 3. SEGMENT CELLS USING SAMJ
# ======================================

# SAMJ uses the Point Selection as prompts.
# export=true also creates a label image.

IJ.run(
    imp,
    "SAMJ Annotator",
    "model=[%s] export=true" % SAM_MODEL
)

# SAMJ should add segmented cell ROIs
# to the ROI Manager.
n_cells = rm.getCount()

if n_cells == 0:
    raise RuntimeError(
        "No segmented ROIs found. "
        "Check SAMJ installation and model."
    )

print("SAMJ returned %d cell ROIs" % n_cells)

# ======================================
# 4. MEASURE INDIVIDUAL CELLS
# ======================================

# Measurements performed on original image
measurements = (
    Measurements.AREA |
    Measurements.MEAN |
    Measurements.STD_DEV |
    Measurements.PERIMETER |
    Measurements.SHAPE_DESCRIPTORS |
    Measurements.FERET |
    Measurements.CENTROID |
    Measurements.INTEGRATED_DENSITY
)

Analyzer.setMeasurements(measurements)

# Reset Results table
rt = ResultsTable.getResultsTable()
rt.reset()

# Measure all segmented cell ROIs
imp.deleteRoi()
rm.deselect()
rm.runCommand(imp, "Measure")


# ======================================
# 5. SAVE OUTPUTS
# ======================================


# Input filename without extension
input_name = os.path.splitext(
    os.path.basename(IMAGE_PATH)
)[0]

def output_path(suffix):
    return os.path.join(
        OUTPUT_DIR, input_name + suffix
    )

# --------------------------------------
# 5A. Save measurements
# --------------------------------------

rt.save(output_path("_cell_measurements.csv"))

# --------------------------------------
# 5B. Collect cell ROIs
# --------------------------------------

# Hide ROI Manager overlays and labels
rm.runCommand("Show None")

# Collect only area selections (not points)
cell_rois = []

for i in range(rm.getCount()):
    roi = rm.getRoi(i)
    if roi is not None and roi.isArea():
        cell_rois.append(roi.clone())

if len(cell_rois) == 0:
    raise RuntimeError("No segmented cell ROIs found")

# --------------------------------------
# 5C. Save binary mask
# --------------------------------------

width = imp.getWidth()
height = imp.getHeight()

mask_ip = ByteProcessor(width, height)
mask_ip.setValue(255)

for roi in cell_rois:
    mask_ip.fill(roi)

mask_imp = ImagePlus(
    input_name + "_binary_mask", mask_ip
)

IJ.saveAs(
    mask_imp, "Tiff",
    output_path("_binary_mask.tif")
)

# --------------------------------------
# 5D. Save labelled mask
# --------------------------------------

# 0 = background
# 1, 2, 3 ... = individual cells

if len(cell_rois) > 65535:
    raise RuntimeError("Too many cells for 16-bit mask")

label_ip = ShortProcessor(width, height)

for i, roi in enumerate(cell_rois):
    label_ip.setValue(i + 1)
    label_ip.fill(roi)

label_imp = ImagePlus(
    input_name + "_label_mask", label_ip
)

IJ.saveAs(
    label_imp, "Tiff",
    output_path("_label_mask.tif")
)

# --------------------------------------
# 5E. Create clean segmentation overlay
# --------------------------------------

# Duplicate original image
overlay_imp = imp.duplicate()
overlay_imp.setTitle(input_name + "_overlay")

# Remove any SAMJ overlay and active ROI
overlay_imp.setOverlay(None)
overlay_imp.deleteRoi()

# Create a new overlay with no labels
overlay = Overlay()
overlay.drawLabels(False)
overlay.drawNames(False)

for roi in cell_rois:
    clean_roi = roi.clone()
    clean_roi.setName(None)
    clean_roi.setStrokeColor(Color.yellow)
    clean_roi.setStrokeWidth(1)
    overlay.add(clean_roi)

overlay_imp.setOverlay(overlay)

# Save editable overlay as TIFF
IJ.saveAs(
    overlay_imp, "Tiff",
    output_path("_overlay.tif")
)

# Flatten to RGB for a clean PNG
flat_imp = overlay_imp.flatten()

IJ.saveAs(
    flat_imp, "PNG",
    output_path("_overlay.png")
)

# --------------------------------------
# 5F. Save ROI ZIP
# --------------------------------------

# Preserve only segmented cell ROIs
rm.reset()

for i, roi in enumerate(cell_rois):
    rm.addRoi(roi)
    rm.rename(i, "Cell_%03d" % (i + 1))

rm.deselect()

rm.runCommand(
    "Save", output_path("_segmented_cells.zip")
)

# --------------------------------------
# 5G. Display results
# --------------------------------------

mask_imp.show()
label_imp.show()
overlay_imp.show()

print("Processing complete!")
print("Segmented cells: %d" % len(cell_rois))
print("Outputs saved in: " + OUTPUT_DIR)
