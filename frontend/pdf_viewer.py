# pdf_viewer.py

import fitz  # PyMuPDF
import customtkinter as ctk
import tkinter as tk
from tkinter import Menu
from backend.constants import *
from tkinter.simpledialog import askstring  # For custom title input
import tkinter.font as tkfont
scroll_counter = 0

class PDFViewer:
    def __init__(self, parent, master):
        self.parent = parent

        self.canvas = ctk.CTkCanvas(master, width=CANVAS_WIDTH, height=CANVAS_HEIGHT)
        self.canvas.place(x=10, y=100)



        # Detect and store the system DPI
        self.system_dpi = self.detect_system_dpi()
        print(f"Detected System DPI: {self.system_dpi}")

        self.v_scrollbar = ctk.CTkScrollbar(master, orientation="vertical", command=self.canvas.yview,
                                            height=CANVAS_HEIGHT)
        self.v_scrollbar.place(x=CANVAS_WIDTH + 14, y=100)

        self.h_scrollbar = ctk.CTkScrollbar(master, orientation="horizontal", command=self.canvas.xview,
                                            width=CANVAS_WIDTH)
        self.h_scrollbar.place(x=10, y=CANVAS_HEIGHT + 105)

        self.pdf_document = None
        self.page = None
        self.current_zoom = CURRENT_ZOOM
        self.areas = []
        self.rectangle_list = []

        self.original_coordinates = None
        self.canvas_image = None  # Holds the current PDF page image to prevent garbage collection
        self.resize_job = None  # Track the delayed update job

        self._last_pixmap_zoom = None  # cache for throttling redraw

        # Initialize selected rectangle ID and title dictionary
        self.selected_rectangle = None
        self.selected_rectangle_id = None
        self.rectangle_titles = {}  # Dictionary to store {rectangle_id: title}

        self.mode = None
        self.table_coordinates = None
        self.rev_coordinates = None
        self.current_rectangle = None

        self.insertion_points = []  # List to store insertion points and texts

        # Create main context menu
        self.context_menu = Menu(self.canvas, tearoff=0)

        # Set Title submenu for title options
        self.set_title_menu = Menu(self.context_menu, tearoff=0)
        self.set_title_menu.add_command(label="Drawing No", command=lambda: self.set_rectangle_title("Drawing No"))
        self.set_title_menu.add_command(label="Drawing Title",
                                        command=lambda: self.set_rectangle_title("Drawing Title"))
        self.set_title_menu.add_command(label="Revision Description",
                                        command=lambda: self.set_rectangle_title("Revision Description"))
        self.set_title_menu.add_command(label="Custom...", command=self.set_custom_title)

        # Add Set Title submenu to context menu
        self.context_menu.add_cascade(label="Set Title", menu=self.set_title_menu)

        # Add Delete Rectangle option to the context menu
        self.context_menu.add_command(label="Delete Rectangle", command=self.delete_selected_rectangle)

        # Bind canvas resize and mouse events
        self.canvas.master.bind("<Configure>", lambda event: self.resize_canvas())
        self.canvas.bind("<ButtonPress-1>", self.start_rectangle)
        self.canvas.bind("<B1-Motion>", self.draw_rectangle)
        self.canvas.bind("<ButtonRelease-1>", self.end_rectangle)

        # Right-click context menu events
        self.canvas.bind("<Button-3>", self.show_context_menu)
        self.canvas.bind("<ButtonRelease-3>", self.show_context_menu)  # Alternative right-click event

        # Initialize selection state
        self.selected_rectangle_id = None
        self.selected_rectangle_index = None
        self.selected_rectangle_original_color = "red"  # Default color for rectangles

        self._prev_canvas_w = CANVAS_WIDTH
        self._prev_canvas_h = CANVAS_HEIGHT

        # Scroll and zoom events
        self.canvas.bind("<MouseWheel>", self.handle_mousewheel)
        self.canvas.bind("<Shift-MouseWheel>", self.handle_mousewheel)  # Shift for horizontal scroll
        self.canvas.bind("<Control-MouseWheel>", self.handle_mousewheel)  # Ctrl for zoom

    # ------------------------------------------------------------
    # Convert a PDF Base-14 face like 'Helvetica-BoldOblique'
    # into a Tk font object with correct weight / slant
    # ------------------------------------------------------------
    def _get_tk_font(self, pdf_name: str, pixel_h: int):
        """Return a Tk font whose *pixel* height equals `pixel_h`."""
        base, w, s = "Helvetica", "normal", "roman"
        p = pdf_name.split("-")
        if p:
            base = p[0]
        if len(p) > 1:
            mod = p[1].lower()
            if "bold" in mod:
                w = "bold"
            if "italic" in mod or "oblique" in mod:
                s = "italic"
        # negative size → Tk interprets it as pixels not points
        return tkfont.Font(family=base, size=-pixel_h, weight=w, slant=s)

    def detect_system_dpi(self):
        """Detects the system's DPI using the canvas widget."""
        try:
            dpi = self.canvas.winfo_fpixels('1i')  # '1i' represents one inch
            return dpi
        except Exception as e:
            print(f"Error detecting DPI: {e}")
            return 96  # Fallback to a common DPI value if detection fails

    def set_deletion_mode(self):
        """Activate deletion mode and bind relevant mouse events."""
        self.mode = 'deletion'
        print("Deletion mode activated.")

        # Unbind text insertion events
        self.canvas.unbind("<Button-1>")
        self.canvas.unbind("<B1-Motion>")
        self.canvas.unbind("<ButtonRelease-1>")

        # Bind rectangle creation events
        self.canvas.bind("<ButtonPress-1>", self.start_rectangle)
        self.canvas.bind("<B1-Motion>", self.draw_rectangle)
        self.canvas.bind("<ButtonRelease-1>", self.end_rectangle)

    def set_text_insertion_mode(self, font_style="Helvetica", font_size=9):
        self.mode = 'insertion'
        self.font_style = font_style
        self.font_size = font_size
        print(f"Text insertion mode activated with font {font_style} and size {font_size}.")

        # Unbind rectangle creation events
        self.canvas.unbind("<ButtonPress-1>")
        self.canvas.unbind("<B1-Motion>")
        self.canvas.unbind("<ButtonRelease-1>")

        # Bind text insertion events
        self.canvas.bind("<Button-1>", self.add_insertion_point)

    def on_mouse_press(self, event):
        if self.mode == 'deletion':
            self.start_rectangle(event)
        elif self.mode == 'insertion':
            self.add_insertion_point(event)

    def on_mouse_drag(self, event):
        if self.mode == 'deletion':
            self.draw_rectangle(event)

    def on_mouse_release(self, event):
        if self.mode == 'deletion':
            self.end_rectangle(event)

    def add_insertion_point(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)


        # Get font style and size
        font_style = self.parent.font_style_menu.get()
        font_size = int(self.parent.font_size_entry.get())

        text = askstring("Insert Text", "Enter text to insert:")
        if text:
            # Save the insertion point with font and size
            self.insertion_points.append({
                'position': (x / self.current_zoom, y / self.current_zoom),
                'text': text,
                'font': font_style,
                'size': font_size  # Store original size for PDF
            })

            # Display the text on the canvas
            self._draw_preview(self.insertion_points[-1])


    def set_custom_title(self):
        """Prompts user for a custom title and assigns it to the selected rectangle."""
        custom_title = askstring("Custom Title", "Enter a custom title:")
        if custom_title:
            self.set_rectangle_title(custom_title)  # Use the input title for the selected rectangle

    def handle_mousewheel(self, event):
        """Handles mouse wheel scrolling with Shift and Control modifiers."""
        if event.state & 0x1:  # Shift pressed for horizontal scrolling
            self.canvas.xview_scroll(-1 * int(event.delta / 120), "units")
        elif event.state & 0x4:  # Ctrl pressed for zoom
            if event.delta > 0:
                self.zoom_in(0.1)  # Zoom in by a small increment
            else:
                self.zoom_out(0.1)  # Zoom out by a small increment
            # Notify the GUI to update the zoom slider
            self.parent.update_zoom_slider(self.current_zoom)
        else:  # Regular vertical scrolling
            self.canvas.yview_scroll(-1 * int(event.delta / 120), "units")

    def zoom_in(self, increment=0.1):
        """Zoom in by increasing the current zoom level and refreshing the display."""
        self.current_zoom += increment
        self.update_display(force_redraw=True)

    def zoom_out(self, decrement=0.1):
        """Zoom out by decreasing the current zoom level and refreshing the display."""
        self.current_zoom = max(0.1, self.current_zoom - decrement)  # Prevent excessive zooming out
        self.update_display(force_redraw=True)

    def close_pdf(self):
        """Closes the displayed PDF and clears the canvas."""
        # Remove any displayed image from the canvas
        self.canvas.delete("pdf_image")

        # Close the PDF document if it is open
        if self.pdf_document:
            self.pdf_document.close()
            print("PDF document closed.")

        # Reset the pdf_document attribute to None to indicate no PDF is open
        self.pdf_document = None

    def display_pdf(self, pdf_path):
        """Loads and displays the first page of a PDF document."""
        self.pdf_document = fitz.open(pdf_path)
        if self.pdf_document.page_count > 0:
            self.page = self.pdf_document[0]  # Display the first page by default
            self.pdf_width = int(self.page.rect.width)
            self.pdf_height = int(self.page.rect.height)
            # Update the display
            self.update_display(force_redraw=True)
            # Set the initial view to the top-left corner of the PDF
            self.canvas.xview_moveto(0)  # Horizontal scroll to start
            self.canvas.yview_moveto(0)  # Vertical scroll to start
        else:
            self.pdf_document = None
            print("Error: PDF has no pages.")

    def _draw_preview(self, ins):
        """(Re-)draw a single blue preview string for one entry in self.insertion_points"""
        x, y = [c * self.current_zoom for c in ins["position"]]
        font_style = ins["font"]
        pt_size = ins["size"]

        pixel_h = int(pt_size * self.current_zoom)  # ❶ how high the glyphs must be
        fnt = self._get_tk_font(font_style, pixel_h)  # ❷ get a Tk Font object

        # ❸ the exact distance from baseline → bottom of bbox
        baseline_offset = fnt.metrics("descent")

        return self.canvas.create_text(
            x, y + baseline_offset,
            text=ins["text"],
            fill="blue",
            anchor=tk.SW,
            font=fnt,
            tags=("preview_text",),
        )

    def _update_scrollregion_only(self):
        """Re-compute scrollregion and move preview text; no new pixmap."""
        zoom_w = int(self.pdf_width * self.current_zoom)
        zoom_h = int(self.pdf_height * self.current_zoom)
        self.canvas.config(scrollregion=(0, 0, zoom_w, zoom_h))
        # shift all preview texts to their new positions
        for text_id, ins in zip(self.canvas.find_withtag("preview_text"),
                                self.insertion_points):
            x, y = [c * self.current_zoom for c in ins["position"]]
            pixel_h = int(ins["size"] * self.current_zoom)
            fnt = self._get_tk_font(ins["font"], pixel_h)
            baseoff = fnt.metrics("descent")
            self.canvas.coords(text_id, x, y + baseoff)
            self.canvas.itemconfigure(text_id, font=fnt)  # update size too

    def update_display(self, force_redraw=False):
        """Updates the canvas to display the current PDF page with zoom and scroll configurations."""

        # Do we need a fresh pixmap?
        rebuilding = (force_redraw or self._last_pixmap_zoom != self.current_zoom)

        # ─── NEW LINE ───
        if rebuilding:
            self.canvas.delete("preview_text")

            # Skip expensive pixmap rebuild if only the window size changed
        if self._last_pixmap_zoom == self.current_zoom and not force_redraw:
            self._update_scrollregion_only()  # we’ll add this helper below
            return
        self._last_pixmap_zoom = self.current_zoom
        # Only proceed if a valid page is loaded
        if not self.page:
            print("Error updating display: No valid page loaded.")
            return

        self.canvas.delete("preview_text")  # wipe old layer

        for ins in self.insertion_points:  # rebuild at new zoom
            self._draw_preview(ins)


        # Set canvas dimensions based on the master window size
        canvas_width = self.canvas.master.winfo_width() - 30
        canvas_height = self.canvas.master.winfo_height() - 135

        # Adjust scrollbars to fit the canvas dimensions
        self.v_scrollbar.configure(command=self.canvas.yview, height=canvas_height)
        self.v_scrollbar.place_configure(x=canvas_width + 14, y=100)
        self.h_scrollbar.configure(command=self.canvas.xview, width=canvas_width)
        self.h_scrollbar.place_configure(x=10, y=canvas_height + 107)

        # Resize the canvas to the calculated dimensions
        self.canvas.config(width=canvas_width, height=canvas_height)

        # Check if there is a valid PDF page to display
        if self.page is None:
            print("No valid page to display.")
            return

        try:
            # Generate a pixmap from the PDF page at the current zoom level
            pix = self.page.get_pixmap(matrix=fitz.Matrix(self.current_zoom, self.current_zoom))
            img = pix.tobytes("ppm")
            img_tk = tk.PhotoImage(data=img)

           # Generate pixmap …
            if self.canvas.find_withtag("pdf_image"):
                # reuse the same image item
                self.canvas.itemconfigure("pdf_image", image=img_tk)
            else:
                # first time: create it
                self.canvas.create_image(0, 0, anchor=tk.NW, image=img_tk, tags="pdf_image")

            # Keep a reference to the image to prevent garbage collection
            self.canvas_image = img_tk

            # Calculate the zoomed dimensions
            zoomed_width = int(self.pdf_width * self.current_zoom)
            zoomed_height = int(self.pdf_height * self.current_zoom)

            # Configure the scroll region of the canvas to match the zoomed dimensions
            self.canvas.config(yscrollcommand=self.v_scrollbar.set, xscrollcommand=self.h_scrollbar.set,
                               scrollregion=(0, 0, zoomed_width, zoomed_height))

        except ValueError as e:
            print(f"Error updating display: {e}")

        # Update any rectangle overlays or additional graphics
        self.update_rectangles()

    def set_mode(self, mode):
        """Set the active mode and bind appropriate events."""
        self.canvas.unbind("<ButtonPress-1>")
        self.canvas.unbind("<B1-Motion>")
        self.canvas.unbind("<ButtonRelease-1>")
        self.canvas.unbind("<Button-1>")

        self.mode = mode
        self.current_rectangle = None

        if mode == TEXT_MODE:
            self.canvas.bind("<Button-1>", self.add_insertion_point)
            print("Text mode activated.")
        elif mode == REDACTION_MODE:
            self.canvas.bind("<ButtonPress-1>", self.start_rectangle)
            self.canvas.bind("<B1-Motion>", self.draw_rectangle)
            self.canvas.bind("<ButtonRelease-1>", self.end_rectangle)
            print("Redaction mode activated.")
        elif mode in [TABLE_COORDINATES_MODE, REVISION_COORDINATES_MODE]:
            self.canvas.bind("<ButtonPress-1>", self.start_rectangle)
            self.canvas.bind("<B1-Motion>", self.draw_rectangle)
            self.canvas.bind("<ButtonRelease-1>", self.end_rectangle)
            print(f"{mode.capitalize()} mode activated.")

    def start_rectangle(self, event):
        """Starts drawing a rectangle on the canvas."""
        print(f"Start rectangle called in mode: {self.mode}")
        if self.mode in [TABLE_COORDINATES_MODE, REVISION_COORDINATES_MODE, REDACTION_MODE]:
            self.original_coordinates = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
            self.current_rectangle = self.canvas.create_rectangle(*self.original_coordinates,
                                                                  *self.original_coordinates, outline="purple", width=2)
            print(f"Rectangle started at: {self.original_coordinates}")

    def draw_rectangle(self, event):
        """Adjusts the rectangle dimensions as the mouse is dragged."""
        if self.current_rectangle:
            print(f"Dragging rectangle: Current mode {self.mode}")
            x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
            print(f"Dragging to: {x}, {y}")
            self.canvas.coords(self.current_rectangle, self.original_coordinates[0], self.original_coordinates[1], x, y)

    def end_rectangle(self, event):
        """Finalizes the rectangle and assigns it based on the mode."""
        if self.current_rectangle:
            x0, y0 = self.original_coordinates
            x1, y1 = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
            print(f"End rectangle: {x0}, {y0}, {x1}, {y1}")

            if self.mode == TABLE_COORDINATES_MODE:
                # Adjust table coordinates for PDF units
                self.table_coordinates = [x0 / self.current_zoom, y0 / self.current_zoom,
                                          x1 / self.current_zoom, y1 / self.current_zoom]
                print(f"Table coordinates set: {self.table_coordinates}")
                self.rectangle_list.append(self.current_rectangle)  # Keep the rectangle visible

            elif self.mode == REVISION_COORDINATES_MODE:
                # Adjust revision coordinates for PDF units
                self.rev_coordinates = [x0 / self.current_zoom, y0 / self.current_zoom,
                                        x1 / self.current_zoom, y1 / self.current_zoom]
                print(f"Revision coordinates set: {self.rev_coordinates}")
                self.rectangle_list.append(self.current_rectangle)  # Keep the rectangle visible

            elif self.mode == REDACTION_MODE:
                # Adjust redaction area for PDF units
                adjusted_coords = [x0 / self.current_zoom, y0 / self.current_zoom,
                                   x1 / self.current_zoom, y1 / self.current_zoom]
                self.areas.append({"coordinates": adjusted_coords, "title": "Redaction Area"})
                self.rectangle_list.append(self.current_rectangle)  # Keep the rectangle visible
                print(f"Redaction area added: {adjusted_coords}")

            # Call update_rectangles to refresh the canvas
            self.update_rectangles()

            self.current_rectangle = None


    def auto_scroll_canvas(self, x, y):
        """Auto-scrolls the canvas if the mouse is near the edges during a drag operation."""
        global scroll_counter
        scroll_margin = 20  # Distance from the canvas edge to start scrolling

        # Only scroll every SCROLL_INCREMENT_THRESHOLD calls
        if scroll_counter < SCROLL_INCREMENT_THRESHOLD:
            scroll_counter += 1
            return  # Skip scrolling this call

        scroll_counter = 0  # Reset counter after threshold is reached

        # Check if the mouse is close to the edges and scroll in small increments
        if x >= self.canvas.winfo_width() - scroll_margin:
            self.canvas.xview_scroll(1, "units")
        elif x <= scroll_margin:
            self.canvas.xview_scroll(-1, "units")

        if y >= self.canvas.winfo_height() - scroll_margin:
            self.canvas.yview_scroll(1, "units")
        elif y <= scroll_margin:
            self.canvas.yview_scroll(-1, "units")

    def clear_areas(self):
        """Clears all rectangles, area selections, insertion points, and Treeview entries from the canvas."""

        # Clear all rectangles from the canvas
        for rect_id in self.rectangle_list:
            self.canvas.delete(rect_id)
        self.rectangle_list.clear()

        # remove blue preview texts
        self.canvas.delete("preview_text")

        # Clear the areas list
        self.areas.clear()

        # Clear all text related to insertion points from the canvas
        for insertion in self.insertion_points:
            # Optionally, you can identify and delete text items if needed
            pass
        self.insertion_points.clear()

        # Clear the areas Treeview if it exists
        if hasattr(self, 'areas_tree') and self.areas_tree:
            for item in self.areas_tree.get_children():
                self.areas_tree.delete(item)

        # Update the canvas display to reflect changes
        self.update_display(force_redraw=True)

        # Clear the Treeview in the parent GUI
        self.parent.update_areas_treeview()

        # Optional: Print statement for debugging
        print("Cleared All Areas and Insertion Points")

    def update_rectangles(self):
        """Updates rectangle overlays on the canvas and refreshes the Treeview with adjusted coordinates."""
        # Clear existing rectangles from the canvas
        for rect_id in self.rectangle_list:
            self.canvas.delete(rect_id)
        self.rectangle_list.clear()

        # Redraw rectangles for redaction areas
        for rect_info in self.areas:
            x0, y0, x1, y1 = [coord * self.current_zoom for coord in rect_info["coordinates"]]
            # Draw the rectangle on the canvas
            rect_id = self.canvas.create_rectangle(x0, y0, x1, y1, outline="red", width=2)
            self.rectangle_list.append(rect_id)

        # Draw rectangle for table coordinates
        if self.table_coordinates:
            x0, y0, x1, y1 = [coord * self.current_zoom for coord in self.table_coordinates]
            rect_id = self.canvas.create_rectangle(x0, y0, x1, y1, outline="blue", width=2, dash=(20, 5))
            self.rectangle_list.append(rect_id)
            print(f"Table coordinates rectangle drawn: {self.table_coordinates}")

        # Draw rectangle for revision coordinates
        if self.rev_coordinates:
            x0, y0, x1, y1 = [coord * self.current_zoom for coord in self.rev_coordinates]
            rect_id = self.canvas.create_rectangle(x0, y0, x1, y1, outline="green", width=2, dash=(4, 2))
            self.rectangle_list.append(rect_id)
            print(f"Revision coordinates rectangle drawn: {self.rev_coordinates}")

        # Update the Treeview in the main GUI
        self.parent.update_areas_treeview()

    def set_zoom(self, zoom_level):
        """Updates the zoom level and refreshes the display."""
        self.current_zoom = zoom_level
        self.update_display(force_redraw=True) # Refresh the display with the new zoom level

    def resize_canvas(self):
        """Schedule a lightweight resize without regenerating the pixmap."""
        if self.resize_job:
            self.canvas.after_cancel(self.resize_job)
        self.resize_job = self.canvas.after(RESIZE_DELAY, self._perform_resize)


    def _perform_resize(self):
        """Performs the actual resize operation for the canvas."""
        # Set new canvas dimensions based on master window size
        canvas_width = self.canvas.master.winfo_width() - 30
        canvas_height = self.canvas.master.winfo_height() - 135

        # Update canvas size
        self.canvas.config(width=canvas_width, height=canvas_height)

        # Update scrollbar dimensions and positions
        self.v_scrollbar.configure(height=canvas_height)
        self.v_scrollbar.place_configure(x=canvas_width + 14, y=100)  # Adjust position based on new width

        self.h_scrollbar.configure(width=canvas_width)
        self.h_scrollbar.place_configure(x=10, y=canvas_height + 107)  # Adjust position based on new height

        # Refresh the PDF display to fit the new canvas size
        self._update_scrollregion_only()

    def show_context_menu(self, event):
        """Displays context menu and highlights the rectangle if right-click occurs near the edge."""
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        edge_tolerance = 5  # Set the edge tolerance for detecting clicks near the boundary

        # Clear previous selection if any
        self.clear_selection()

        # Iterate over rectangles to find one that has been clicked near its edge
        for index, rect_id in enumerate(self.rectangle_list):
            bbox = self.canvas.bbox(rect_id)
            if bbox:
                x0, y0, x1, y1 = bbox

                # Check if the click is near the left or right edge within the tolerance
                near_left_edge = abs(x - x0) <= edge_tolerance and y0 <= y <= y1
                near_right_edge = abs(x - x1) <= edge_tolerance and y0 <= y <= y1

                # Check if the click is near the top or bottom edge within the tolerance
                near_top_edge = abs(y - y0) <= edge_tolerance and x0 <= x <= x1
                near_bottom_edge = abs(y - y1) <= edge_tolerance and x0 <= x <= x1

                # If click is near any edge, select this rectangle
                if near_left_edge or near_right_edge or near_top_edge or near_bottom_edge:
                    self.selected_rectangle_id = rect_id
                    self.selected_rectangle_index = index
                    self.selected_rectangle_original_color = self.canvas.itemcget(rect_id, "outline")

                    # Highlight the selected rectangle with a different color
                    self.canvas.itemconfig(rect_id, outline="blue")
                    print(f"Selected Rectangle at Index {index} with ID: {rect_id}")
                    break

        # Show context menu if a rectangle was selected by edge detection
        if self.selected_rectangle_id is not None:
            self.context_menu.post(event.x_root, event.y_root)
        else:
            # Hide menu if no rectangle edge was clicked
            print("No rectangle edge detected, context menu will not be shown.")
            self.context_menu.unpost()

    def clear_selection(self):
        """Clears the selection by resetting the color of the previously selected rectangle."""
        if self.selected_rectangle_id is not None:
            # Reset the previously selected rectangle's color
            self.canvas.itemconfig(self.selected_rectangle_id, outline=self.selected_rectangle_original_color)
            self.selected_rectangle_id = None
            self.selected_rectangle_index = None

    def set_rectangle_title(self, title):
        """Assigns a selected title to the currently selected rectangle and updates the Treeview."""
        if self.selected_rectangle_index is not None:
            # Update the title directly in `self.areas` based on the rectangle index
            self.areas[self.selected_rectangle_index]["title"] = title  # Update title in `self.areas`
            print(f"Title '{title}' set for rectangle at Index: {self.selected_rectangle_index}")

            # Update the Treeview to reflect the new title
            self.parent.update_areas_treeview()
        else:
            print("No rectangle selected. Title not set.")

    def delete_selected_rectangle(self):
        """Deletes the selected rectangle from the canvas and updates the list of areas."""
        if self.selected_rectangle_id:
            try:
                # Find the index of the selected rectangle in rectangle_list
                index = self.rectangle_list.index(self.selected_rectangle_id)

                # Delete the rectangle from canvas and remove from lists
                self.canvas.delete(self.selected_rectangle_id)
                del self.rectangle_list[index]
                del self.areas[index]

                # Update the Treeview and clear selection
                self.parent.update_areas_treeview()
                self.selected_rectangle_id = None
                print("Rectangle deleted.")

                # Reassign titles to reflect the new order
                for index, area in enumerate(self.areas):
                    area["title"] = f"Rectangle {index + 1}"  # Update titles in `areas`
                self.parent.update_areas_treeview()  # Refresh Treeview to reflect updated titles


            except ValueError:
                print("Selected rectangle ID not found in the rectangle list.")
        else:
            print("No rectangle selected for deletion.")
