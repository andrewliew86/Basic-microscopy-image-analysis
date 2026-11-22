# Run inside Fiji: Plugins > New > Script
# Language: Python (Jython)
from ij import IJ, ImagePlus, Prefs, WindowManager
from ij.plugin.frame import RoiManager
from ij.plugin.filter import Analyzer, EDM, ParticleAnalyzer
from ij.measure import Measurements, ResultsTable
from ij.gui import OvalRoi, Overlay, WaitForUserDialog, Roi, TextRoi
from ij.process import ByteProcessor, ShortProcessor, ImageProcessor
import sys
from jarray import zeros
from java.awt import Color, Font
import os

# CONFIGURATION
IMAGE_PATH = r"C:\Users\Andrew\raw_data\349.jpg"
OUTPUT_DIR = r"C:\Users\Andrew\output"
DARK_COLONIES = True
INTERACTIVE_ROI = True
PLATE_ROI = (275, 228, 1470, 1470) # x, y, width, height
# For IMG_7709ecoli_T4_10^-8_16.JPG, try:
# DARK_COLONIES = False
# PLATE_ROI = (215, 690, 930, 930)
ROLLING_RADIUS = 50
GAUSSIAN_SIGMA = 6
THRESHOLD_METHOD = "Otsu"
MIN_AREA = 1000
MAX_AREA = 4000
MIN_CIRCULARITY = 0.8
USE_WATERSHED = True
LABEL_FONT_SIZE = 16
CLOSE_OTHER_IMAGES = True

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)
name = os.path.splitext(os.path.basename(IMAGE_PATH))[0]
def output_path(suffix):
    return os.path.join(OUTPUT_DIR, name + suffix)

def progress(message):
    print(message)
    sys.stdout.flush()
    IJ.log(message)

# 1. Load and duplicate
imp = IJ.openImage(IMAGE_PATH)
if imp is None:
    raise IOError("Cannot open image: " + IMAGE_PATH)
imp.show()
if INTERACTIVE_ROI:
    IJ.selectWindow(imp.getTitle())
    IJ.setTool("oval")
    dialog = WaitForUserDialog(
        "Select agar region",
        "Draw an oval just inside the plate rim, then click OK."
    )
    dialog.show()
    if dialog.escPressed():
        raise RuntimeError("ROI selection cancelled.")
    selected = imp.getRoi()
    if selected is None or selected.getType() != Roi.OVAL:
        raise RuntimeError("Please draw an oval ROI and run again.")
    roi = selected.clone()
    imp.deleteRoi()
else:
    roi = OvalRoi(*PLATE_ROI)
work = imp.duplicate()
work.setTitle(name + "_processing")
work.show()
rm = RoiManager.getInstance()
if rm is None:
    rm = RoiManager()
rm.reset()
rt = ResultsTable.getResultsTable()
rt.reset()

# 2. Background subtraction and smoothing
IJ.run(work, "8-bit", "")
IJ.run(work, "Set Scale...", "distance=0 known=0 pixel=1 unit=pixel")
if DARK_COLONIES:
    IJ.run(work, "Invert", "")
IJ.run(work, "Subtract Background...", "rolling=%s" % ROLLING_RADIUS)
IJ.run(work, "Gaussian Blur...", "sigma=%s" % GAUSSIAN_SIGMA)
IJ.saveAs(work, "Tiff", output_path("_background_corrected.tif"))

# 3. Threshold using only the agar ROI
work.setRoi(roi)
IJ.setAutoThreshold(work, THRESHOLD_METHOD + " dark")
old_black = Prefs.blackBackground
Prefs.blackBackground = True
try:
    progress("1. Converting threshold to binary mask")
    # Apply threshold directly to avoid the Convert to Mask dialog.
    ip = work.getProcessor()
    lower = ip.getMinThreshold()
    upper = ip.getMaxThreshold()
    if lower == ImageProcessor.NO_THRESHOLD:
        raise RuntimeError("Automatic threshold was not set")
    ip.resetThreshold()
    work.deleteRoi()
    ip.resetRoi()
    lut = zeros(256, "i")
    for i in range(256):
        if i >= lower and i <= upper:
            lut[i] = 255
        else:
            lut[i] = 0
    ip.applyTable(lut)
    if ip.isInvertedLut():
        ip.invertLut()
    work.setRoi(roi)
    # Set all pixels outside the circular ROI to zero directly
    ip = work.getProcessor()
    ip.setValue(0)
    ip.fillOutside(roi)
    work.deleteRoi()
    progress("2. Filling holes")
    IJ.run(work, "Fill Holes", "")
    if USE_WATERSHED:
        progress("3. Applying watershed")
        EDM().toWatershed(work.getProcessor())
    work.updateAndDraw()
    progress("4. Segmentation finished")
finally:
    Prefs.blackBackground = old_black
progress("Saving watershed mask")
IJ.saveAs(work, "Tiff", output_path("_watershed_mask.tif"))

# 4. Analyze particles and collect accepted ROIs
progress("5. Counting particles")
measurements = (Measurements.AREA | Measurements.PERIMETER |
                Measurements.SHAPE_DESCRIPTORS | Measurements.CENTROID |
                Measurements.FERET)
rt = ResultsTable()
ParticleAnalyzer.setRoiManager(rm)
pa = ParticleAnalyzer(ParticleAnalyzer.ADD_TO_MANAGER, measurements,
                      rt, MIN_AREA, MAX_AREA, MIN_CIRCULARITY, 1.0)
# Explicitly identify white pixels as foreground.
work.getProcessor().setThreshold(255, 255, ImageProcessor.NO_LUT_UPDATE)
if not pa.analyze(work):
    raise RuntimeError("Particle analysis failed; inspect ImageJ Log")
work.getProcessor().resetThreshold()
n = rm.getCount()
progress("Detected colonies: %d" % n)
if n:
    rt.save(output_path("_colony_measurements.csv"))
else:
    print("No colonies accepted; inspect the watershed mask and adjust parameters.")

# 5. Save accepted binary mask, labelled mask and overlay
progress("6. Creating output masks and overlay")
mask_ip = ByteProcessor(work.getWidth(), work.getHeight())
label_ip = ShortProcessor(work.getWidth(), work.getHeight())
if n > 65535:
    raise RuntimeError("Too many colonies for a 16-bit label image")
overlay = Overlay()
overlay.drawLabels(False)
overlay.drawNames(False)
for i in range(n):
    r = rm.getRoi(i).clone()
    rm.rename(i, "Colony_%03d" % (i + 1))
    mask_ip.setValue(255)
    mask_ip.fill(r)
    label_ip.setValue(i + 1)
    label_ip.fill(r)
    r.setStrokeColor(Color.red)
    r.setStrokeWidth(2)
    overlay.add(r)
    bounds = r.getBounds()
    text = str(i + 1)
    tx = min(bounds.x + bounds.width + 3, max(0, work.getWidth() - LABEL_FONT_SIZE * len(text)))
    ty = max(0, min(bounds.y, work.getHeight() - LABEL_FONT_SIZE - 4))
    label = TextRoi(tx, ty, text, Font("SansSerif", Font.BOLD, LABEL_FONT_SIZE))
    label.setStrokeColor(Color.red)
    overlay.add(label)
mask = ImagePlus(name + "_binary_mask", mask_ip)
labels = ImagePlus(name + "_label_mask", label_ip)
result = imp.duplicate()
result.setTitle("%s - %d colonies" % (name, n))
result.setOverlay(overlay)
IJ.saveAs(mask, "Tiff", output_path("_binary_mask.tif"))
IJ.saveAs(labels, "Tiff", output_path("_label_mask.tif"))
IJ.saveAs(result, "Tiff", output_path("_overlay.tif"))
IJ.saveAs(result.flatten(), "PNG", output_path("_overlay.png"))
if n:
    rm.deselect()
    rm.runCommand("Save", output_path("_segmented_colonies.zip"))
rm.runCommand("Show None")
# Close intermediate windows, then show only the numbered overlay.
if CLOSE_OTHER_IMAGES:
    for image_id in (WindowManager.getIDList() or []):
        image = WindowManager.getImage(image_id)
        if image is not None:
            image.changes = False if image == imp or image == work else image.changes
            image.close()
else:
    for image in (imp, work):
        image.changes = False
        image.close()
rm.close()
result.show()
progress("Processing complete. Outputs saved in: " + OUTPUT_DIR)
