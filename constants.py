# constants.py

VERSION_TEXT = "Version 0.241201-01"

# Application settings
INITIAL_WIDTH = 965
GOLDEN_RATIO = (1 + 5 ** 0.5) / 2
INITIAL_HEIGHT = INITIAL_WIDTH / GOLDEN_RATIO
CANVAS_WIDTH = INITIAL_WIDTH - 30
CANVAS_HEIGHT = INITIAL_HEIGHT - 135
INITIAL_X_POSITION = 100
INITIAL_Y_POSITION = 100
CURRENT_ZOOM = 2.0

BUTTON_FONT = "Verdana"

SCROLL_MARGIN = 20  # Distance from the canvas edge to start scrolling
SCROLL_INCREMENT_THRESHOLD = 3  # Adjust this for slower/faster auto-scroll
scroll_counter = 0  # This will be updated in your main code
RESIZE_DELAY = 700  # milliseconds delay


FONT_MAPPING = {
    "Courier": "Courier",
    "Courier-Oblique": "Courier",
    "Courier-Bold": "Courier New",
    "Courier-BoldOblique": "Courier New",
    "Helvetica": "Helvetica",
    "Helvetica-Oblique": "Helvetica",
    "Helvetica-Bold": "Helvetica",
    "Helvetica-BoldOblique": "Helvetica",
    "Times-Roman": "Times New Roman",
    "Times-Italic": "Times New Roman",
    "Times-Bold": "Times New Roman",
    "Times-BoldItalic": "Times New Roman",
    "Symbol": "Symbol",
    "ZapfDingbats": "ZapfDingbats",
}



